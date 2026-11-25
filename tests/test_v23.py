"""v1.13: /cd is remembered, the model decides about reading files, fix requests, no feature is deleted to dodge an error, genre videos, bigger skills.
Run: python -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "videokit"))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

from lumo.cli import *  # noqa: F401,F403,E402  (imports and registers every tool)
from lumo import fixmode, keepguard, scope, workspace  # noqa: E402
from lumo.agent import decide_intent, note_recovery  # noqa: E402
from lumo.commands import HELP  # noqa: E402
from lumo.prompts import build_system  # noqa: E402
from lumo.state import Ctx  # noqa: E402
from lumo.toolrun import exec_tool  # noqa: E402
from lumo.verify import TRUNCATION_RE, js_quality_issues, py_quality_issues, secret_issues  # noqa: E402


def new_ctx(text="", intent="task"):
    ws = Path(tempfile.mkdtemp(prefix="v23_"))
    (ws / "game.py").write_text("print(1)\n")
    ctx = Ctx({"model": "x/y"}, ws)
    ctx.turn = {"t0": 0.0, "tools": 0, "reqs": 0}
    ctx.auto = True
    if text:
        scope.note_request(ctx, text, intent, False)
    return ctx


def run_cli(stdin, cwd, home, lumo_home, *args):
    """Start the real program (no network: the API address is a closed port) and feed it lines."""
    env = dict(os.environ, HOME=str(home), LUMO_HOME=str(lumo_home), OPENROUTER_API_KEY="sk-or-test-1234567890",
               LUMO_API_BASE="http://127.0.0.1:9/api/v1", NO_COLOR="1", LUMO_NO_ANIM="1", TERM="xterm")
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "-m", "x/y:free"] + list(args), input=stdin, cwd=str(cwd), env=env,
                       capture_output=True, text=True, timeout=90)
    return r.stdout + r.stderr


class WorkspaceIsRemembered(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="ws23_"))
        self.home, self.lh, self.proj = self.t / "home", self.t / "lumohome", self.t / "proj"
        for d in (self.home, self.lh, self.proj):
            d.mkdir()

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def test_a_cd_survives_a_restart(self):
        first = run_cli("/cd %s\n/exit\n" % self.proj, self.home, self.home, self.lh)
        self.assertIn("workspace: %s" % self.proj, first)
        self.assertEqual(json.loads((self.lh / "config.json").read_text())["workspace"], str(self.proj))
        second = run_cli("/cd\n/exit\n", self.home, self.home, self.lh)                  # a restart from the home folder
        self.assertIn("workspace: %s" % self.proj, second)
        self.assertNotIn("workspace: %s" % (self.home / "workspace"), second)

    def test_a_folder_on_the_command_line_wins_and_is_remembered(self):
        other = self.t / "other"
        other.mkdir()
        self.assertIn("workspace: %s" % other, run_cli("/cd\n/exit\n", self.home, self.home, self.lh, str(other)))
        self.assertIn("workspace: %s" % other, run_cli("/cd\n/exit\n", self.home, self.home, self.lh))

    def test_a_missing_saved_folder_falls_back_with_a_note(self):
        run_cli("/cd %s\n/exit\n" % self.proj, self.home, self.home, self.lh)
        shutil.rmtree(self.proj)
        out = run_cli("/exit\n", self.home, self.home, self.lh)
        self.assertIn("is not available", out)
        self.assertIn(str(self.home / "workspace"), out)

    def test_cd_dash_returns_to_the_previous_folder(self):
        a, b = self.t / "a", self.t / "b"
        a.mkdir()
        b.mkdir()
        out = run_cli("/cd %s\n/cd %s\n/cd -\n/exit\n" % (a, b), self.home, self.home, self.lh)
        self.assertEqual(out.count("workspace: %s" % a), 2, out)
        self.assertEqual(out.count("workspace: %s" % b), 1, out)

    def test_the_order_of_choices(self):
        old = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        try:
            from lumo.config import APP_DIR
            self.assertEqual(workspace.resolve(None, {}, cwd=self.home), (self.home / "workspace", ""))
            saved = {"workspace": str(self.proj)}
            self.assertEqual(workspace.resolve(None, saved, cwd=self.home)[0], self.proj)       # started from HOME: the saved one
            self.assertEqual(workspace.resolve(None, saved, cwd=APP_DIR)[0], self.proj)         # started from the Lumo folder: the saved one
            self.assertEqual(workspace.resolve(None, saved, cwd=self.t)[0], self.t.resolve())   # started inside some other folder: that folder
            self.assertEqual(workspace.resolve(str(self.t / "x"), saved, cwd=self.home)[0], self.t / "x")   # a folder given on the command line
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old

    def test_help_mentions_it(self):
        self.assertIn("/cd [folder|-]", HELP)


class ModelDecidesAboutFiles(unittest.TestCase):
    def test_reading_tools_work_for_every_real_request(self):
        for text, intent in (("explain recursion", "chat"), ("buatkan game snake", "build"), ("benerin", "task"), ("kok error?", "task"), ("lihat game.py", "task"),
                             ("coba lagi", "task"), ("udah belum", "task")):
            ctx = new_ctx(text, intent)
            for tool in scope.EXPLORE_TOOLS:
                self.assertIsNone(scope.guard(ctx, tool, {"path": "game.py"}), (text, tool))

    def test_only_a_greeting_or_thanks_gets_no_tools(self):
        for text in ("hi", "halo", "terima kasih"):
            ctx = new_ctx(text, "chat")
            for tool in scope.EXPLORE_TOOLS:
                res = scope.guard(ctx, tool, {"path": "game.py"})
                self.assertTrue(res and res.startswith("SKIPPED"), (text, tool))

    def test_history_files_stay_limited(self):
        ctx = new_ctx("lanjutkan", "task")
        res = scope.guard(ctx, "read_file", {"path": "history/transcript.md"})
        self.assertTrue(res and res.startswith("SKIPPED"), res)
        self.assertIsNone(scope.guard(ctx, "read_file", {"path": "history/transcript.md", "start_line": 1, "end_line": 40}))

    def test_the_prompt_leaves_the_decision_to_the_model(self):
        text = (ROOT / "prompts" / "system-prompt.md").read_text()
        self.assertIn("Decide yourself whether the request needs the user's files", text)
        self.assertNotIn("SKIPPED: not needed", text)


class FixRequests(unittest.TestCase):
    PHRASES = ["benerin", "benerin dong yang error", "betulin file nya", "perbaikin", "kok error?", "ini error nya", "game nya gak jalan", "Fix!", "tolong fix",
               "ada bug", "kenapa crash?", "scriptnya ga jalan", "NameError: name 'x' is not defined", "Traceback (most recent call last):"]
    NOT = ["apa itu error 404?", "what is a syntax error", "explain recursion", "halo", "berapa 17 kali 23?"]

    def test_fix_phrases_are_tasks_not_questions(self):
        for text in self.PHRASES:
            self.assertTrue(fixmode.is_fix_request(text), text)
            self.assertEqual(decide_intent(new_ctx(), text)[0], "task", text)

    def test_knowledge_questions_are_not_fix_requests(self):
        for text in self.NOT:
            self.assertFalse(fixmode.is_fix_request(text), text)

    def test_a_short_message_after_an_error_is_about_that_error(self):
        ctx = new_ctx()
        self.assertFalse(fixmode.is_followup(ctx, "coba lagi"))                              # nothing is open
        ctx.carry_fail = {"run_python": "NameError: name 'score' is not defined (game.py line 42)"}
        self.assertTrue(fixmode.is_followup(ctx, "coba lagi"))
        block = fixmode.block(ctx, "coba lagi")
        for needed in ("FIX MODE", "game.py", "Never skip"):
            self.assertIn(needed, block)
        self.assertEqual(scope.explore_reason(ctx, "coba lagi", "task", False), "follow-up")
        self.assertEqual(fixmode.block(new_ctx(), "halo apa kabar"), "")

    def test_the_open_error_is_found_again_in_a_restored_conversation(self):
        ctx = new_ctx()
        ctx.messages = [{"role": "tool", "content": "Traceback (most recent call last):\n  File \"game.py\", line 3\nNameError: name 'x' is not defined\n[exit code 1 · 0.1s]"}]
        found = fixmode.trouble(ctx)
        self.assertTrue(found and "game.py" in found["files"], found)
        ctx.messages.append({"role": "tool", "content": "fine\n[exit code 0 · 0.1s]"})
        self.assertIsNone(fixmode.trouble(ctx))

    def test_a_later_success_closes_the_open_error(self):
        ctx = new_ctx()
        ctx.carry_fail = {"run_python": "NameError: name 'x' is not defined"}
        note_recovery(ctx, "run_python", "all good", False)
        self.assertEqual(ctx.carry_fail, {})
        note_recovery(ctx, "run_python", "NameError: name 'y' is not defined (game.py line 9)", True)
        self.assertIn("run_python", ctx.turn["pending_fail"])

    def test_the_repair_routine_reaches_the_system_prompt_only_for_fix_requests(self):
        ctx = new_ctx()
        ctx.scope_text = "benerin"
        self.assertIn("FIX MODE", build_system(ctx, "build"))
        ctx.scope_text = "buatkan game snake"
        self.assertNotIn("FIX MODE", build_system(ctx, "build"))


class NothingIsDeletedToDodgeAnError(unittest.TestCase):
    OLD = ("import os\n\n\ndef load(path):\n    return open(path).read()\n\n\ndef draw_hud(c, t):\n    c.text('HUD', 10, 10)\n\n\ndef sound(v):\n    v.sfx('punch', 1.0)\n\n\n"
           "class Game:\n    def update(self):\n        pass\n\n    def render(self):\n        return 1\n\n\ndef main():\n    print(load('x'))\n    draw_hud(None, 0)\n    sound(None)\n")
    NEW = ("import os\n\n\ndef load(path):\n    return open(path).read()\n\n\nclass Game:\n    def update(self):\n        pass\n\n\ndef main():\n    print(load('x'))\n")

    def test_lost_functions_are_listed(self):
        self.assertEqual(keepguard.lost_defs(self.OLD, self.NEW, ".py"), ["Game.render", "draw_hud", "sound"])
        js_old = "function a() {}\nconst b = (x) => x;\nclass C {}\n"
        self.assertEqual(keepguard.lost_defs(js_old, "function a() {}\n", ".js"), ["C", "b"])
        self.assertEqual(keepguard.lost_defs(self.OLD, self.OLD, ".py"), [])
        self.assertEqual(keepguard.lost_defs(self.OLD, "def broken(:\n", ".py"), [])         # a file that does not parse is the verifier's business

    def test_the_note_names_them_and_tells_the_model_to_restore_them(self):
        text = keepguard.note("game.py", ".py", self.OLD, self.NEW, open_failure=True)
        for needed in ("NOTE:", "draw_hud", "sound", "put them back", "An error is still open"):
            self.assertIn(needed, text)
        self.assertEqual(keepguard.note("a.py", ".py", "def a():\n    pass\n", "", False), "")        # tiny files are rewritten freely

    def test_a_big_cut_without_lost_functions_is_noticed(self):
        old = "\n".join("x%d = %d" % (i, i) for i in range(60)) + "\n"
        self.assertIn("went from 60 to", keepguard.note("data.py", ".py", old, "x0 = 0\n"))

    def test_the_file_tools_report_what_was_removed(self):
        ctx = new_ctx()
        exec_tool(ctx, "write_file", {"path": "g.py", "content": self.OLD})
        res = exec_tool(ctx, "write_file", {"path": "g.py", "content": self.NEW})
        self.assertIn("NOTE:", res)
        self.assertIn("draw_hud", res)
        exec_tool(ctx, "write_file", {"path": "g.py", "content": self.OLD})
        res = exec_tool(ctx, "edit_file", {"path": "g.py", "old_string": "def sound(v):\n    v.sfx('punch', 1.0)\n\n\n", "new_string": ""})
        self.assertIn("NOTE:", res)
        self.assertIn("sound", res)
        res = exec_tool(ctx, "edit_file", {"path": "g.py", "old_string": "return 1", "new_string": "return 2"})
        self.assertNotIn("NOTE:", res)

    def test_the_rules_say_repair_the_call_never_the_feature(self):
        prompt = (ROOT / "prompts" / "system-prompt.md").read_text()
        rules = (ROOT / "prompts" / "tool-rules.md").read_text()
        self.assertIn("An error points at one wrong name, value or call, not at the feature", prompt)
        self.assertIn("Repair the call, never the feature", rules)
        self.assertIn("Do not delete the feature that fails", (ROOT / "lumo" / "agent.py").read_text())


class VerifierHabits(unittest.TestCase):
    def text(self, issues):
        return " | ".join(m for _level, m in issues)

    def test_python_habits_are_named(self):
        bad = ("import os, json\nfrom typing import List\n\n\ndef f(x=[]):\n    try:\n        return 1\n    except:\n        pass\n\n\ndef g():\n    try:\n        return 2\n"
               "    except Exception:\n        pass\n\n\ndef h():\n    pass\n")
        found = self.text(py_quality_issues(bad, "a.py"))
        for needed in ("bare 'except:'", "swallows the error", "mutable default", "no implementation", "unused imports"):
            self.assertIn(needed, found)

    def test_clean_python_has_none(self):
        good = ("import json\nimport sys\n\n\ndef load(path):\n    with open(path, encoding='utf-8') as fh:\n        return json.load(fh)\n\n\ndef main(argv):\n    try:\n"
                "        data = load(argv[1])\n    except (OSError, ValueError) as err:\n        print('cannot read: %s' % err, file=sys.stderr)\n        return 1\n    print(len(data))\n    return 0\n")
        self.assertEqual(py_quality_issues(good, "a.py"), [])

    def test_cut_off_code_is_an_error_but_a_spread_is_not(self):
        for bad in ("# ... existing code ...", "// ...", "/* your code here */", "# the rest of the code goes here"):
            self.assertTrue(TRUNCATION_RE.search(bad), bad)
        for fine in ("const f = (first, ...remaining) => remaining", "x = {...existing, a: 1}", "# the rest of the code assumes sorted input", "label = 'Loading...'"):
            self.assertFalse(TRUNCATION_RE.search(fine), fine)

    def test_hard_coded_secrets_are_flagged_but_placeholders_are_not(self):
        self.assertTrue(secret_issues("TOKEN = 'abcdEFGH1234567890abcd'", "a.py"))
        for fine in ("API_KEY = os.environ['API_KEY']", "password = 'must-be-at-least-8-chars'", "token = 'YOUR_TOKEN_HERE_12345678'"):
            self.assertEqual(secret_issues(fine, "a.py"), [], fine)

    def test_javascript_habits(self):
        found = self.text(js_quality_issues("try { run() } catch (e) {}\nconst y = eval(s)", "a.js"))
        self.assertIn("empty catch", found)
        self.assertIn("eval()", found)


class GenreVideos(unittest.TestCase):
    NEW = ("video-promo", "video-data-chart", "video-tutorial", "video-slideshow", "video-science", "video-countdown")

    def test_every_new_template_is_listed_and_documented(self):
        man = json.loads((ROOT / "templates" / "manifest.json").read_text())["templates"]
        skill = (ROOT / "skills" / "video-skill.md").read_text()
        for name in self.NEW:
            self.assertIn(name, man)
            self.assertTrue((ROOT / "templates" / man[name]["file"]).is_file(), name)
            self.assertEqual(man[name]["min_novelty"], 0.0)
            self.assertIn("`%s`" % name, skill, name)

    def test_every_new_template_passes_its_own_selftest(self):
        man = json.loads((ROOT / "templates" / "manifest.json").read_text())["templates"]
        for name in self.NEW:
            with tempfile.TemporaryDirectory() as d:
                text = (ROOT / "templates" / man[name]["file"]).read_text()
                for key, value in man[name]["vars"].items():
                    text = text.replace("__%s__" % key, value)
                self.assertNotIn("__TITLE__", text)
                (Path(d) / "x.py").write_text(text)
                shutil.copy(ROOT / "videokit" / "lumovideo.py", d)
                r = subprocess.run([sys.executable, "x.py", "--selftest"], cwd=d, capture_output=True, text=True, timeout=170)
                self.assertEqual(r.returncode, 0, (name, r.stdout[-300:], r.stderr[-600:]))
                self.assertIn("all checks passed", r.stdout, name)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not installed")
    def test_a_genre_template_renders_a_real_mp4_with_sound(self):
        with tempfile.TemporaryDirectory() as d:
            text = (ROOT / "templates" / "video-countdown.py").read_text().replace("__TITLE__", "Happy New Year").replace("__SUBTITLE__", "See you")
            (Path(d) / "countdown.py").write_text(text)
            shutil.copy(ROOT / "videokit" / "lumovideo.py", d)
            env = dict(os.environ, LUMO_VIDEO_QUALITY="draft")
            r = subprocess.run([sys.executable, "countdown.py"], cwd=d, env=env, capture_output=True, text=True, timeout=170)
            self.assertEqual(r.returncode, 0, r.stderr[-600:])
            mp4 = Path(d) / "videos" / "countdown.mp4"
            self.assertTrue(mp4.is_file() and mp4.stat().st_size > 20000)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True)
            self.assertIn("h264", probe.stdout)
            self.assertIn("aac", probe.stdout)


class BiggerSkills(unittest.TestCase):
    def read(self, name):
        return (ROOT / "skills" / name).read_text()

    def test_the_design_skill_is_complete(self):
        text = self.read("design-skill.md")
        self.assertGreater(len(text), 30000)
        for needed in ("## The process", "## Pick the direction", "## 2. Color", "## 3. Typography", "## 4. Layout and spacing", "## 5. Components", "Game UI and HUD",
                       "Dashboards and data", "Terminal and CLI output", "## 8. Avoid the generic-AI look", "## 10. Writing the words", "## 11. The review loop"):
            self.assertIn(needed, text, needed)

    def test_the_video_skill_starts_from_the_genre_not_from_a_fight(self):
        text = self.read("video-skill.md")
        self.assertLess(text.index("## Pick the genre first"), text.index("## Stickman fights"))
        for genre in ("Explainer", "Promo", "Tutorial", "Data story", "Kinetic text", "Slideshow", "Logo reveal", "Countdown", "Science animation", "Story", "Fight", "Beat visual", "Timeline"):
            self.assertIn(genre, text, genre)
        for needed in ("never default to one", "repair the call, never the feature", "Genre playbooks"):
            self.assertIn(needed, text)

    def test_code_and_debug_skills_have_the_new_parts(self):
        code, debug = self.read("code-quality-skill.md"), self.read("debug-skill.md")
        for needed in ("## Blueprint before you write", "## Shape the code", "## Prove it works", "## Read the verifier", "never the feature"):
            self.assertIn(needed, code, needed)
        for needed in ('## When the user says "fix it"', "never skipped, never deleted and never reported as"):
            self.assertIn(needed, debug, needed)


if __name__ == "__main__":
    unittest.main()
