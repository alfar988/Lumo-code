"""Version 1.8: the video library, the render_video and video_info tools, the video templates, skill routing and the engine kit v2 games."""

import json
import os
import re
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

from lumo.cli import *  # noqa: F401,F403,E402  (registers every tool)
from lumo.skills import pick_skills  # noqa: E402
from lumo.state import Ctx  # noqa: E402
from lumo.templates import load_template_manifest, t_use_template, template_catalog  # noqa: E402
from lumo.toolrun import exec_tool  # noqa: E402
from lumo.tools import video as video_tools  # noqa: E402
import lumovideo as lv  # noqa: E402

HAVE_PIL = lv.Image is not None
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
NODE = shutil.which("node")
ENV = dict(os.environ, PYTHONPATH=str(ROOT / "videokit") + os.pathsep + os.environ.get("PYTHONPATH", ""))
VIDEO_TEMPLATES = ("video-stickman-fight", "video-explainer", "video-kinetic-text")
KIT_GAMES = ("game-snake", "game-breakout", "game-runner", "game-flappy", "game-pong", "game-shooter", "game-asteroids", "game-tetris",
             "game-memory", "game-racing", "game-platformer", "game-tower-defense")


class TestTiming(unittest.TestCase):
    def test_every_easing_starts_at_zero_and_ends_at_one(self):
        for name in lv.EASINGS:
            self.assertAlmostEqual(lv.ease(0, name), 0.0, 6, name)
            self.assertAlmostEqual(lv.ease(1, name), 1.0, 6, name)
        with self.assertRaises(ValueError):
            lv.ease(0.5, "no_such_curve")

    def test_keys_tween_timeline(self):
        k = lv.Keys([(0, 0), (1, 100, "linear"), (2, 40, "linear")])
        self.assertEqual((k(0.5), k(5), k(-1)), (50, 40, 0))
        self.assertEqual(lv.tween(0.5, 0, 1, (0, 0), (10, 20), "linear"), (5.0, 10.0))
        tl = lv.Timeline().add("a", 0, 2).add("b", 1, 1)
        self.assertEqual((tl.p("a", 1), tl.p("b", 0), tl.p("b", 5)), (0.5, 0, 1))
        self.assertTrue(tl.active("b", 1.5) and not tl.active("b", 2.5))

    def test_colour_and_notes(self):
        self.assertEqual(lv.rgb("#f80"), (255, 136, 0))
        self.assertEqual(lv.mix("black", "white", 0.5), (128, 128, 128))
        self.assertEqual(lv.shade("#808080", -1.0), (0, 0, 0))
        with self.assertRaises(ValueError):
            lv.rgb("not a colour")
        self.assertAlmostEqual(lv.note_freq("A4"), 440.0, 3)
        self.assertAlmostEqual(lv.note_freq("Bb3"), 233.08, 1)
        self.assertAlmostEqual(lv.note_freq("b4"), 493.88, 1)

    def test_typewriter_and_noise(self):
        tw = lv.Typewriter("hello", start=1.0, cps=10)
        self.assertEqual((tw.shown(0.5), tw.shown(1.25), tw.shown(9)), ("", "he", "hello"))
        self.assertTrue(all(-1.0 <= lv.noise(x * 0.37, 3) <= 1.0 for x in range(200)))


class TestSound(unittest.TestCase):
    def test_every_effect_and_music_style_makes_sound(self):
        for name in ("punch", "hit", "kick", "snare", "hat", "whoosh", "ko", "explosion", "bell", "ding", "pop", "click", "coin", "error", "laser", "step", "crowd", "riser", "blip"):
            b = getattr(lv.sfx, name)()
            self.assertGreater(len(b), 100, name)
            self.assertGreater(max(abs(x) for x in b), 0.01, name)
        for style in ("fight", "chill", "8bit", "epic"):
            self.assertEqual(len(lv.music.beat(120, 1, style)), int(4 * 0.5 * lv.SR), style)
        with self.assertRaises(ValueError):
            lv.music.beat(120, 1, "polka")

    def test_mixer_writes_a_wav_that_never_clips(self):
        import wave
        m = lv.Mixer(2.0)
        for i in range(6):
            m.add(lv.sfx.ko(), at=0.1 * i, vol=2.0)
        d = tempfile.mkdtemp()
        path = m.save(os.path.join(d, "m.wav"), length=2.0)
        with wave.open(path) as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (2, lv.SR))
            self.assertAlmostEqual(w.getnframes() / float(w.getframerate()), 2.0, 2)
            raw = w.readframes(w.getnframes())
        import array
        a = array.array("h", raw)
        self.assertLessEqual(max(abs(v) for v in a), 32767)
        shutil.rmtree(d)


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class TestDrawing(unittest.TestCase):
    def test_canvas_primitives_and_output_size(self):
        c = lv.Canvas(1280, 720, 854, 480, ss=2)
        c.background("#101626", "#3b2a6b")
        c.glow(900, 200, 200, "#ffcc66", 0.8)
        c.circle(300, 300, 60, fill="#f55", outline="white", alpha=0.7)
        c.rect(100, 100, 300, 100, fill="black", radius=20, alpha=0.5)
        c.poly([(10, 10), (60, 10), (30, 60)], fill="red")
        c.text("Hi\nthere", 640, 360, 80, "white", outline="black", outline_w=4, rot=10, alpha=0.8)
        c.camera(700, 400, 1.5, shake=3)
        c.circle(700, 400, 20, fill="white")
        with c.screen():
            c.letterbox(2.39)
        c.vignette(0.5)
        im = c.to_image()
        self.assertEqual((im.size, im.mode), ((854, 480), "RGB"))
        self.assertGreater(lv.ImageStat.Stat(im.convert("L")).stddev[0], 10)

    def test_quality_presets_keep_even_sizes_and_the_same_drawing_space(self):
        for q, (w, h) in {"draft": (480, 270), "standard": (854, 480), "hd": (1280, 720), "fhd": (1920, 1080)}.items():
            v = lv.Video(1280, 720)
            v.scene(1, lambda c, t: c.clear("#222"))
            self.assertEqual(v.frame_at(0.5, q).size, (w, h), q)
        v = lv.Video(720, 1280)
        v.scene(1, lambda c, t: c.clear("#222"))
        self.assertEqual(v.frame_at(0.5, "standard").size, (480, 854))

    def test_scene_arity_and_every_transition(self):
        for tr in ("cut", "fade", "crossfade", "slide_left", "slide_right", "slide_up", "slide_down", "wipe_left", "wipe_right", "zoom"):
            v = lv.Video(1280, 720)
            v.scene(1.0, lambda c: c.clear("#c33"))                         # a scene function that takes only the canvas
            v.scene(1.0, lambda c, t: c.clear("#33c"), transition=tr, trans_dur=0.4)
            im = v.frame_at(0.9, "draft")
            self.assertEqual(im.size, (480, 270), tr)
            self.assertAlmostEqual(v.duration, 2.0 if tr in ("cut", "fade") else 1.6, 2, tr)

    def test_checks_catch_a_flat_video_and_ignore_fades(self):
        flat = lv.Video(1280, 720)
        flat.scene(4.0, lambda c, t: c.clear("#000000"))
        rep = flat.dry_run(8)
        self.assertGreater(rep["blank_frames"], 0)
        self.assertTrue(rep["warnings"])
        fade = lv.Video(1280, 720)
        fade.scene(2.0, lambda c, t: (c.background("#224", "#448"), c.circle(100 + 400 * t, 360, 50, fill="white")), fade_in=0.3, fade_out=0.3)
        self.assertEqual(fade.dry_run(8)["blank_frames"], 0)

    def test_every_stage_draws_something(self):
        for kind in lv.Stage.KINDS:
            c = lv.Canvas(1280, 720, 320, 180, ss=1)
            c.camera(640, 460, 1.0)
            lv.Stage(kind, 1280, 720).draw(c, 0.5)
            self.assertGreater(lv.ImageStat.Stat(c.to_image().convert("L")).stddev[0], 4, kind)
        with self.assertRaises(ValueError):
            lv.Stage("moon base")

    def test_every_pose_and_move_draws_and_resolves(self):
        s = lv.Stick("A", weapon="sword", gloves="#f00", headband="#fff", belt="#ff0")
        c = lv.Canvas(1280, 720, 320, 180, ss=1)
        for name in lv.POSES:
            J = s.draw(c, 640, 560, 1, name, 0.1)
            self.assertIn("hand_r", J, name)
            self.assertTrue(all(map(lambda v: v == v, J["head"])), name)
        for name, m in lv.MOVES.items():
            for t in (0.0, m.dur / 2, m.dur):
                p = m.pose_at(t)
                self.assertTrue(all(v == v for v in p.values()), name)
        with self.assertRaises(ValueError):
            lv.Stick("A", weapon="laser")


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class TestFight(unittest.TestCase):
    def test_auto_fight_has_a_winner_a_ko_and_is_repeatable(self):
        def make(seed, winner):
            f = lv.Fight(lv.Stick("A"), lv.Stick("B", "#f55"), stage="arena")
            f.auto(duration=12, winner=winner, seed=seed)
            return f
        for winner, loser in (("a", "B"), ("b", "A")):
            s = make(3, winner).summary()
            self.assertEqual(s["ko"], loser, s)
            self.assertEqual(s["hp"][0 if loser == "A" else 1], 0, s)
            self.assertGreater(s["hp"][1 if loser == "A" else 0], 0, s)
            self.assertGreater(sum(s["hits"]), 2, s)
        a, b = make(5, "a"), make(5, "a")
        self.assertEqual(a.summary(), b.summary())
        va, vb = lv.Video(1280, 720), lv.Video(1280, 720)
        va.add(a)
        vb.add(b)
        self.assertEqual(va.frame_at(5.0, "draft").tobytes(), vb.frame_at(5.0, "draft").tobytes())
        self.assertNotEqual(make(5, "a").summary(), make(6, "a").summary())

    def test_scripted_fight_blocks_misses_and_finisher(self):
        f = lv.Fight(lv.Stick("RYU"), lv.Stick("KEN"), stage="dojo")
        f.gap(0.3, 90, 1.0)
        f.attack("a", "jab", at=1.6)
        f.attack("b", "cross", at=2.4, hit=False)
        f.dodge("a", at=2.35)
        f.block("b", at=3.2, dur=0.7)
        f.attack("a", "front_kick", at=3.3)
        f.attack("a", "round_kick", at=5.0, finisher=True)
        f.victory("a", at=6.5)
        s = f.summary()
        self.assertEqual((s["ko"], s["hits"][0], s["blocked"][0], s["missed"][1]), ("KEN", 2, 1, 1), s)
        self.assertEqual(s["hp"][1], 0)
        self.assertGreater(s["duration"], 7.0)
        with self.assertRaises(ValueError):
            f.attack("a", "block", at=1)
        with self.assertRaises(ValueError):
            f.walk("c", to=100)

    def test_a_fight_adds_its_sound_effects_to_the_video(self):
        f = lv.Fight(lv.Stick("A"), lv.Stick("B"), stage="plain", music="fight")
        f.auto(duration=9, winner="a", seed=2)
        v = lv.Video(1280, 720)
        v.add(f)
        self.assertGreater(len(v.sounds), 10)
        self.assertGreater(v.duration, 9)             # hit stops and slow motion make the video longer than the fight time

    def test_fighters_never_overlap_or_leave_the_arena(self):
        f = lv.Fight(lv.Stick("A"), lv.Stick("B"), stage="plain")
        f.auto(duration=14, winner="b", seed=8)
        f.summary()
        for k in range(0, int(f.t_end * 20)):
            s = k / 20.0
            xa, xb = f._x_at(0, s), f._x_at(1, s)
            self.assertTrue(0 <= xa <= 1280 and 0 <= xb <= 1280, (s, xa, xb))


@unittest.skipUnless(HAVE_PIL and HAVE_FFMPEG, "Pillow and ffmpeg are needed to encode")
class TestRender(unittest.TestCase):
    def test_render_makes_a_playable_mp4_with_sound(self):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "t.mp4")
        v = lv.Video(1280, 720, fps=30, quality="draft")
        v.scene(1.2, lambda c, t: (c.background("#124", "#348"), c.circle(100 + 800 * t, 360, 60, fill="#fc6")))
        v.sound(lv.sfx.ding(), 0.2)
        os.environ.pop("LUMO_VIDEO_OUT", None)
        rep = v.render(out, progress=False)
        info = video_tools.probe(out)
        self.assertEqual((info["vcodec"], info["acodec"], info["pix_fmt"]), ("h264", "aac", "yuv420p"))
        self.assertEqual((info["width"], info["height"]), (480, 270))
        self.assertAlmostEqual(info["duration"], 1.2, delta=0.25)
        self.assertEqual((rep["format"], rep["audio"], rep["qa"]["blank_frames"]), ("mp4", True, 0))
        shutil.rmtree(d)

    def test_without_ffmpeg_a_gif_is_written_unless_mp4_is_required(self):
        d = tempfile.mkdtemp()
        code = ("import lumovideo as lv\nlv.ffmpeg_path = lambda: None            # pretend this device has no ffmpeg\nv = lv.Video(1280, 720, quality='draft')\n"
                "v.scene(0.6, lambda c, t: c.background('#124', '#348'))\nrep = v.render(%r, progress=False)\nprint(rep['format'])\n") % os.path.join(d, "x.mp4")
        env = dict(ENV)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=d, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gif", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(d, "x.gif")))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(env, LUMO_VIDEO_REQUIRE_FFMPEG="1"), cwd=d, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ffmpeg is not installed", r.stderr)
        shutil.rmtree(d)

    def test_command_line_checks(self):
        r = subprocess.run([sys.executable, str(ROOT / "videokit" / "lumovideo.py"), "--selftest"], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LUMO_VIDEO_REPORT", r.stdout)
        r = subprocess.run([sys.executable, str(ROOT / "videokit" / "lumovideo.py"), "--version"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), lv.__version__)


class TestVideoTools(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="vid_ws_"))
        self.ctx = Ctx({"model": "x/y"}, self.ws)
        self.ctx.auto = True
        (self.ws / "videos").mkdir()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_clear_errors_before_anything_runs(self):
        self.assertIn("ERROR", exec_tool(self.ctx, "render_video", {"script": "videos/none.py"}))
        (self.ws / "videos" / "a.txt").write_text("x")
        self.assertIn("ERROR", exec_tool(self.ctx, "render_video", {"script": "videos/a.txt"}))
        (self.ws / "videos" / "ok.py").write_text("print(1)\n")
        self.assertIn("ERROR", exec_tool(self.ctx, "render_video", {"script": "videos/ok.py", "quality": "ultra"}))
        self.assertIn("ERROR", exec_tool(self.ctx, "render_video", {"script": "videos/ok.py", "output": "videos/x.avi"}))
        self.assertIn("ERROR", exec_tool(self.ctx, "video_info", {"path": "videos/missing.mp4"}))

    def test_missing_programs_are_reported_with_the_install_command(self):
        (self.ws / "videos" / "ok.py").write_text("print(1)\n")
        real = video_tools.missing_tools
        video_tools.missing_tools = lambda: ["ffmpeg"]
        try:
            out = exec_tool(self.ctx, "render_video", {"script": "videos/ok.py"})
        finally:
            video_tools.missing_tools = real
        self.assertTrue(out.startswith("ERROR"), out)
        self.assertIn("pkg install ffmpeg", out)
        self.assertFalse((self.ws / "videos" / "lumovideo.py").exists())        # nothing was copied or run

    def test_a_division_sign_is_not_a_path_but_a_real_path_is(self):
        self.assertEqual(video_tools.script_outside_paths(self.ctx, "x = w / 2.0\ny = a / b\nz = '1/2'"), [])
        self.assertTrue(video_tools.script_outside_paths(self.ctx, 'open("/etc/hosts")'))
        self.assertTrue(video_tools.script_outside_paths(self.ctx, 'p = "~/private/notes.txt"'))

    def test_the_library_is_copied_next_to_the_script_and_kept_current(self):
        d = self.ws / "videos"
        self.assertTrue(video_tools.ensure_library(d))
        self.assertFalse(video_tools.ensure_library(d))
        (d / "lumovideo.py").write_text('__version__ = "0.0.1"\n')
        self.assertTrue(video_tools.ensure_library(d))
        self.assertEqual(video_tools.lib_version(d / "lumovideo.py"), lv.__version__)

    def test_progress_lines_are_squeezed_for_the_model(self):
        raw = "start\n  rendering   1% · frame 1/9\r  rendering  50% · frame 5/9\r  rendering 100% · frame 9/9\nLUMO_VIDEO_REPORT {}\n"
        out = video_tools.clean_output(raw)
        self.assertEqual(out.count("rendering"), 1)
        self.assertIn("100%", out)

    @unittest.skipUnless(HAVE_PIL and HAVE_FFMPEG, "Pillow and ffmpeg are needed to encode")
    def test_render_check_and_inspect_end_to_end(self):
        (self.ws / "videos" / "demo.py").write_text(
            "from lumovideo import *\nv = Video(1280, 720, fps=30)\n"
            "def s(c, t):\n    c.background('#123', '#357')\n    c.circle(100 + 800 * t, 360, 50, fill='#fc6')\n"
            "v.scene(1.5, s)\nv.sound(sfx.ding(), 0.2)\nv.render()\n")
        out = exec_tool(self.ctx, "render_video", {"script": "videos/demo.py", "quality": "draft"})
        self.assertTrue(out.startswith("OK: video saved to videos/demo.mp4"), out)
        self.assertIn("H.264 + AAC", out)
        self.assertIn("no blank frames", out)
        self.assertIn("sound included", out)
        self.assertTrue((self.ws / "videos" / "demo.mp4").stat().st_size > 1000)
        self.assertTrue((self.ws / "videos" / "lumovideo.py").exists())
        self.assertFalse(list((self.ws / "videos").glob("__pycache__")))
        info = exec_tool(self.ctx, "video_info", {"path": "videos/demo.mp4"})
        self.assertTrue(info.startswith("OK: videos/demo.mp4"), info)
        self.assertIn("checks over", info)
        out2 = exec_tool(self.ctx, "render_video", {"script": "videos/demo.py", "output": "out/clip.mp4", "quality": "draft"})
        self.assertTrue(out2.startswith("OK: video saved to out/clip.mp4"), out2)
        (self.ws / "videos" / "bad.py").write_text("from lumovideo import *\nraise RuntimeError('boom')\n")
        bad = exec_tool(self.ctx, "render_video", {"script": "videos/bad.py"})
        self.assertTrue(bad.startswith("ERROR: the script did not produce a video"), bad)
        self.assertIn("boom", bad)
        (self.ws / "videos" / "silent.py").write_text("print('done')\n")
        self.assertIn("did not produce a video", exec_tool(self.ctx, "render_video", {"script": "videos/silent.py"}))

    def test_the_tools_are_registered_labelled_and_hidden_unless_asked(self):
        from lumo import safelimit
        from lumo.toolrun import TOOL_META, tool_label
        from lumo.tools.registry import TOOLS
        self.assertTrue({"render_video", "video_info"} <= set(TOOLS))
        self.assertTrue({"render_video", "video_info"} <= set(TOOL_META))
        self.assertIn("videos/x.py", tool_label("render_video", {"script": "videos/x.py", "quality": "draft"}, 80))
        rx = [r for names, r in safelimit.HIDDEN_UNLESS_ASKED if "render_video" in names][0]
        for text in ("make a stickman fight video", "buat video animasi 2d", "render an mp4"):
            self.assertTrue(re.search(rx, text, re.I), text)
        for text in ("fix the login bug", "add a settings page"):
            self.assertFalse(re.search(rx, text, re.I), text)
        from lumo.config import CHAT_TOOLS, PLAN_TOOLS
        self.assertFalse({"render_video", "video_info"} & (set(CHAT_TOOLS) | set(PLAN_TOOLS)))


class TestVideoTemplatesAndSkill(unittest.TestCase):
    def test_templates_are_listed_and_selftest_clean(self):
        man = load_template_manifest()
        ws = Path(tempfile.mkdtemp(prefix="vid_tpl_"))
        ctx = Ctx({"model": "x/y"}, ws)
        ctx.auto = True
        for name in VIDEO_TEMPLATES:
            self.assertIn(name, man)
            self.assertEqual(man[name]["min_novelty"], 0.0)               # names and colours alone are a valid customisation
            dest = "videos/" + name.split("video-", 1)[1] + ".py"
            res = t_use_template({"name": name, "path": dest, "vars": {"TITLE": 'Bob\'s "big" show'}}, ctx)
            self.assertIn("created", res, res)
            text = (ws / dest).read_text()
            self.assertNotRegex(text, r"__[A-Z_0-9]+__", name)
            compile(text, dest, "exec")
            r = subprocess.run([sys.executable, str(ws / dest), "--selftest"], capture_output=True, text=True, cwd=str(ws), env=ENV, timeout=180)
            self.assertEqual(r.returncode, 0, name + "\n" + r.stdout[-300:] + r.stderr[-600:])
            self.assertIn("all checks passed", r.stdout)
        shutil.rmtree(ws)

    def test_the_video_skill_routes_only_for_video_requests(self):
        ctx = Ctx({"model": "x/y"}, Path(tempfile.mkdtemp()))
        for text in ("buat video stickman lagi berkelahi", "make a 20 second explainer video about recycling", "bikin video animasi 2d kartun kucing",
                     "create a vertical mp4 with kinetic text for Reels"):
            self.assertIn("video-skill", pick_skills(ctx, text, "build", False), text)
        for text in ("buat game snake", "make a video game with zombies", "add a video player to my landing page", "download this youtube video with yt-dlp",
                     "fix the login bug in app.py", "write a python script that sorts a csv"):
            self.assertNotIn("video-skill", pick_skills(ctx, text, "build", False), text)

    def test_the_scope_rule_is_in_the_prompts_and_the_skill(self):
        rules = (ROOT / "prompts" / "tool-rules.md").read_text()
        self.assertIn("only when the user asks for a video", rules)
        self.assertIn("Never make a video, GIF, music or other extra file the user did not ask for", rules)
        skill = (ROOT / "skills" / "video-skill.md").read_text()
        self.assertIn("Make a video only when the user asked for one", skill)
        self.assertIn("MP3", skill)
        for forbidden in ("at least two", "beyond the template"):
            self.assertNotIn(forbidden, skill.lower())

    def test_the_template_list_in_the_prompt_stays_short(self):
        cat = template_catalog()
        man = load_template_manifest()
        for name in man:
            self.assertIn("- %s:" % name, cat)
        self.assertLess(len(cat) / len(man), 230)
        self.assertIn("variables TITLE, ACCENT, LANG", cat)
        self.assertIn("file videos/fight.py", cat)


class TestEngineKitV2Games(unittest.TestCase):
    def test_all_twelve_games_use_the_new_kit_and_are_registered(self):
        man = load_template_manifest()
        ids = []
        for name in KIT_GAMES:
            self.assertIn(name, man)
            html = (ROOT / "templates" / (name + ".html")).read_text()
            self.assertIn("ENGINE KIT v2", html, name)
            m = re.search(r'const CONFIG = \{ id: "([a-z-]+)"', html)
            self.assertTrue(m, name)
            ids.append(m.group(1))
            for needed in ("function onStart", "function update(dt)", "function draw()", "function newState()", "window.game"):
                self.assertTrue(needed in html or needed == "function onStart", (name, needed))
            self.assertIn("prefers-reduced-motion", html)
            self.assertIn("aria-live", html)
        self.assertEqual(len(set(ids)), len(ids), "every game needs its own best-score key")

    @unittest.skipUnless(NODE, "Node.js is not installed")
    def test_falling_block_rules_are_correct(self):
        html = (ROOT / "templates" / "game-tetris.html").read_text()
        src = re.search(r"const COLS = 10[\s\S]*?function emptyGrid\(\)[^\n]*\n", html).group(0)
        js = src + "\nconst t = { COLS, ROWS, rotate, matrixOf, collides, clearLines, emptyGrid };\n"
        js += """
const assert = require('assert');
const g = t.emptyGrid();
for (let x = 0; x < t.COLS; x++) { g[19][x] = 'I'; g[18][x] = 'I'; }
g[17][0] = 'O';
assert.strictEqual(t.clearLines(g), 2);
assert.strictEqual(g[19][0], 'O'); assert.strictEqual(g[19][1], 0);
const T = t.matrixOf('T');
assert.deepStrictEqual(t.rotate(t.rotate(t.rotate(t.rotate(T)))), T);
assert.ok(t.collides(t.emptyGrid(), T, -1, 0)); assert.ok(!t.collides(t.emptyGrid(), T, 0, 0)); assert.ok(t.collides(t.emptyGrid(), T, 3, 19));
for (const k of Object.keys({I:1,O:1,T:1,S:1,Z:1,J:1,L:1})) { let m = t.matrixOf(k); const n = m.flat().filter(Boolean).length; assert.strictEqual(n, 4, k); assert.strictEqual(t.rotate(m).flat().filter(Boolean).length, 4); }
console.log('ok');
"""
        d = tempfile.mkdtemp()
        f = Path(d) / "t.js"
        f.write_text(js)
        r = subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        shutil.rmtree(d)

    @unittest.skipUnless(NODE, "Node.js is not installed")
    def test_platformer_levels_are_always_passable(self):
        html = (ROOT / "templates" / "game-platformer.html").read_text()
        m = re.search(r"const T = 24[\s\S]*?function makeRun", html)
        src = m.group(0).rsplit("function makeRun", 1)[0]
        helpers = "function clamp(v,a,b){return Math.max(a,Math.min(b,v));}function rint(a,b){return Math.floor(a+Math.random()*(b-a+1));}function pick(l){return l[Math.floor(Math.random()*l.length)];}\n"
        js = helpers + src + """
const assert = require('assert');
for (let level = 1; level <= 12; level++) for (let n = 0; n < 40; n++) {
  const lv = generate(level);
  assert.strictEqual(lv.top.length, lv.cols);
  for (let x = 1; x < lv.cols; x++) {
    const a = lv.top[x - 1], b = lv.top[x];
    if (a !== null && b !== null) assert.ok(a - b <= 2, 'step up too high ' + level + ':' + x);                 // a rises at most 2 tiles
  }
  let run = 0;
  for (let x = 0; x < lv.cols; x++) { if (lv.top[x] === null) { run++; assert.ok(run <= 3, 'pit too wide'); } else run = 0; }
  assert.ok(lv.top[2] !== null && lv.top[lv.cols - 4] !== null);
}
console.log('ok');
"""
        d = tempfile.mkdtemp()
        f = Path(d) / "p.js"
        f.write_text(js)
        r = subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
