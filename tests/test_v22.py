"""v1.12: the request budget of multi-agent mode, /multiagent test, faster sound synthesis for big battles.
Run: python -m unittest discover -s tests -v"""
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

import test_v21 as T21  # noqa: E402  (the fake OpenRouter and the helpers)
from test_v21 import fake_reply, make_ctx  # noqa: E402
from lumo import multiagent, state  # noqa: E402
from lumo.commands import handle_command  # noqa: E402


def free_ctx(left, **cfg):
    """A free smart model with `left` of 50 daily requests remaining."""
    base = dict(model="big/smart-model:free", multiagent=True, free_daily=50)
    base.update(cfg)
    ctx = make_ctx(**base)
    ctx.cfg["req_day"] = {"d": state.today_utc(), "n": 50 - left}
    return ctx


class RequestBudget(unittest.TestCase):
    def test_the_worker_pauses_when_the_daily_quota_is_nearly_gone(self):
        ctx = free_ctx(5)
        self.assertEqual(multiagent.quota_left(ctx), 5)
        self.assertIn("5 free requests", multiagent.paused_reason(ctx))
        self.assertEqual(multiagent.hidden_tools(ctx), {"delegate"})              # the tool disappears
        self.assertEqual(multiagent.server_tools(ctx, {"id": "openrouter"}, "big/smart-model:free"), [])
        self.assertEqual(multiagent.prompt_block(ctx, "build"), "")
        res = multiagent.run_worker(ctx, "extract", "Read a.txt and tell me what it says, exactly.")
        self.assertTrue(res.startswith("SKIPPED") and "paused" in res)
        with mock.patch("lumo.multiagent.call_light", return_value="x") as m:
            long = "line\n" * 2000
            self.assertEqual(multiagent.digest_failure(ctx, "run_shell", {}, long), long)
        self.assertFalse(m.called)

    def test_plenty_of_quota_or_a_paid_model_keeps_the_worker(self):
        self.assertEqual(multiagent.paused_reason(free_ctx(40)), "")
        paid = free_ctx(1, model="paid/strong-model")
        self.assertIsNone(multiagent.quota_left(paid))
        self.assertEqual(multiagent.paused_reason(paid), "")
        self.assertEqual(multiagent.hidden_tools(paid), set())

    def test_the_pause_is_announced_once_and_resets(self):
        ctx = free_ctx(3)
        with mock.patch("lumo.multiagent.out") as o:
            multiagent.flush_notice(ctx)
            multiagent.flush_notice(ctx)
        self.assertEqual(o.call_count, 1)
        ctx.cfg["req_day"] = {"d": state.today_utc(), "n": 5}
        with mock.patch("lumo.multiagent.out") as o:
            multiagent.flush_notice(ctx)
        self.assertFalse(o.called)
        self.assertFalse(ctx.ma_paused_told)

    def test_jobs_and_requests_per_task_are_capped(self):
        ctx = make_ctx(multiagent=True)
        ctx.turn["ma_jobs"] = 3
        res = multiagent.run_worker(ctx, "extract", "Read a.txt and tell me what it says, exactly.")
        self.assertTrue(res.startswith("SKIPPED") and "3 worker jobs" in res)
        ctx = make_ctx(multiagent=True)
        ctx.turn["ma_reqs"] = 8
        self.assertIn("8 worker requests", multiagent.run_worker(ctx, "test", "Run the checks of this project and report the failures."))
        ctx = make_ctx(multiagent=True, ma_max_jobs=1)
        ctx.turn["ma_jobs"] = 1
        self.assertIn("1 worker jobs", multiagent.run_worker(ctx, "extract", "Read a.txt and tell me what it says, exactly."))

    def test_a_worker_that_keeps_asking_for_tools_is_stopped_by_the_request_cap(self):
        ctx = make_ctx(multiagent=True, ma_max_worker_reqs=3)
        (ctx.ws / "a.txt").write_text("x\n")
        calls = [{"id": "c%d" % i, "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": "a.txt"})}} for i in range(1)]
        seen = []

        def fake(ctx_, model, msgs, tools, *a, **k):
            seen.append(bool(tools))
            return fake_reply(None, [dict(c, id="c%d" % len(seen)) for c in calls]) if tools else fake_reply("report: a.txt holds x")
        with mock.patch("lumo.client.stream_chat", fake):
            res = multiagent.run_worker(ctx, "extract", "Read a.txt again and again and tell me what it says.")
        self.assertIn("report: a.txt holds x", res)
        self.assertEqual(len(seen), 4)                                              # 3 requests with tools, then the forced final report without
        self.assertFalse(seen[-1])
        self.assertEqual(ctx.turn["ma_reqs"], 4)

    def test_the_same_extract_job_is_answered_from_the_cache(self):
        ctx = make_ctx(multiagent=True, ma_max_jobs=10)
        (ctx.ws / "a.txt").write_text("hello\n")
        n = {"calls": 0}

        def fake(*a, **k):
            n["calls"] += 1
            return fake_reply("a.txt says hello")
        with mock.patch("lumo.client.stream_chat", fake):
            first = multiagent.run_worker(ctx, "extract", "Read a.txt and tell me what it says.")
            second = multiagent.run_worker(ctx, "extract", "  read A.TXT and tell me what it says. ")
            self.assertEqual(n["calls"], 1)
            self.assertIn("session cache", second)
            self.assertIn("a.txt says hello", second)
            self.assertEqual(ctx.ma_stats["jobs"], 1)
            ctx.changes.append(("~", str(ctx.ws / "a.txt"), ""))                      # a file changed: the old reading is stale
            multiagent.run_worker(ctx, "extract", "Read a.txt and tell me what it says.")
            self.assertEqual(n["calls"], 2)
            multiagent.run_worker(ctx, "test", "Run the checks of this project and report the failures.")
            multiagent.run_worker(ctx, "test", "Run the checks of this project and report the failures.")
            self.assertEqual(n["calls"], 4)                                             # tests are never cached: the code may have changed

    def test_only_really_long_failures_are_condensed_and_each_error_once(self):
        ctx = make_ctx(multiagent=True)
        medium = "Traceback (most recent call last):\n" + "  File \"app.py\", line 3, in f\n" * 60 + "ValueError: bad value\n[exit code 1]"      # ~1.7 KB
        wide = "x" * 4000 + "\nValueError: one line\n[exit code 1]"                                                                    # long but only 2 lines
        big = "Traceback (most recent call last):\n" + "  File \"app.py\", line 3, in f\n" * 200 + "ValueError: bad value\n[exit code 1]"      # ~5.5 KB
        other = "Traceback (most recent call last):\n" + "  File \"app.py\", line 9, in g\n" * 200 + "KeyError: 'k'\n[exit code 1]"
        third = "Traceback (most recent call last):\n" + "  File \"app.py\", line 5, in h\n" * 200 + "TypeError: t\n[exit code 1]"
        with mock.patch("lumo.multiagent.call_light", return_value="FAIL app.py:3 ValueError") as m:
            self.assertEqual(multiagent.digest_failure(ctx, "run_shell", {}, medium), medium)
            self.assertEqual(multiagent.digest_failure(ctx, "run_shell", {}, wide), wide)
            self.assertFalse(m.called)
            self.assertIn("light-model digest", multiagent.digest_failure(ctx, "run_shell", {}, big))
            self.assertEqual(multiagent.digest_failure(ctx, "run_shell", {}, big), big)       # the same failure again: no second request
            self.assertEqual(m.call_count, 1)
            self.assertIn("light-model digest", multiagent.digest_failure(ctx, "run_shell", {}, other))
            self.assertEqual(multiagent.digest_failure(ctx, "run_shell", {}, third), third)   # the cap of two digests per task
            self.assertEqual(m.call_count, 2)

    def test_budget_command_shows_sets_and_resets(self):
        ctx = make_ctx()
        with mock.patch("lumo.multiagent.save_config"):
            handle_command(ctx, "/multiagent budget jobs 5")
            handle_command(ctx, "/multiagent budget reqs 12")
            handle_command(ctx, "/multiagent budget digest 2500")
            self.assertEqual(multiagent.budget(ctx), {"jobs": 5, "reqs": 12, "digest_min": 2500, "digests": 2})
            handle_command(ctx, "/multiagent budget reset")
            self.assertEqual(multiagent.budget(ctx), {"jobs": 3, "reqs": 8, "digest_min": 3500, "digests": 2})

    def test_status_shows_the_budget_and_the_quota(self):
        ctx = free_ctx(30)
        with mock.patch("lumo.multiagent.out") as o:
            multiagent.show_status(ctx)
        text = " ".join(str(c.args[0]) for c in o.call_args_list)
        self.assertIn("3 jobs and 8 worker requests per task", text)
        self.assertIn("free requests left today: 30", text)


class SelfTest(unittest.TestCase):
    """/multiagent test against the fake OpenRouter: the server-tool probe, the local worker on real files, the error digest."""

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), T21.MAHandler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_the_self_test_passes_end_to_end_and_writes_a_report(self):
        import shutil
        T21.E2E["scenario"], T21.E2E["log"] = "selftest", []
        wd = Path(tempfile.mkdtemp(prefix="ma_selftest_"))
        (wd / "ws").mkdir()
        env = dict(os.environ, LUMO_API_BASE="http://127.0.0.1:%d/api/v1" % self.port, LUMO_HOME=str(wd / "home"), OPENROUTER_API_KEY="sk-or-test-1234567890",
                   NO_COLOR="1", PYTHONIOENCODING="utf-8", LUMO_NO_ANIM="1")
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", T21.SMART, "--auto"], input="/multiagent test\n/exit\n", env=env,
                           capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        self.addCleanup(shutil.rmtree, str(wd), True)
        out = p.stdout + p.stderr
        self.assertIn("multi-agent self-test", out)
        self.assertIn("3/3 passed", out, out)
        self.assertIn("accepted (HTTP 200", out)
        self.assertIn("read both files correctly", out)
        self.assertIn("condensed", out)
        report = (wd / "ws" / "history" / "multiagent-test.txt").read_text()
        self.assertIn("PASS server tool openrouter:subagent", report)
        self.assertIn("3/3 passed", report)
        log = T21.E2E["log"]
        probe = [r for r in log if r["server_tool"]]
        self.assertEqual(len(probe), 1)                                                  # exactly one request carried the server tool
        self.assertEqual(probe[0]["server_model"], T21.LIGHT)
        self.assertEqual(len(log), 4, log)                                               # probe + 2 worker steps + digest
        self.assertFalse((wd / "ws" / "history").glob("selftest-*") and any((wd / "ws" / "history").glob("selftest-*")))    # the test folder is removed

    def test_the_self_test_reports_a_refused_server_tool_and_the_rest(self):
        import shutil
        T21.E2E["scenario"], T21.E2E["log"] = "selftest_refused", []
        wd = Path(tempfile.mkdtemp(prefix="ma_selftest2_"))
        (wd / "ws").mkdir()
        old = T21.MAHandler.do_POST

        def patched(h):
            length = int(h.headers.get("Content-Length", 0))
            raw = h.rfile.read(length)
            body = json.loads(raw or b"{}")
            if any(t.get("type") == "openrouter:subagent" for t in (body.get("tools") or [])):
                return h._json(400, {"error": {"code": 400, "message": "Invalid tool type openrouter:subagent for this model"}})
            import io
            h.rfile = io.BytesIO(raw)
            h.headers.replace_header("Content-Length", str(length)) if "Content-Length" in h.headers else None
            T21.E2E["scenario"] = "selftest"
            return old(h)
        with mock.patch.object(T21.MAHandler, "do_POST", patched):
            env = dict(os.environ, LUMO_API_BASE="http://127.0.0.1:%d/api/v1" % self.port, LUMO_HOME=str(wd / "home"), OPENROUTER_API_KEY="sk-or-test-1234567890",
                       NO_COLOR="1", PYTHONIOENCODING="utf-8", LUMO_NO_ANIM="1")
            p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", T21.SMART, "--auto"], input="/multiagent test\n/exit\n", env=env,
                               capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        self.addCleanup(shutil.rmtree, str(wd), True)
        out = p.stdout + p.stderr
        self.assertIn("refused (HTTP 400)", out, out)
        self.assertIn("Invalid tool type openrouter:subagent", out)
        self.assertIn("2/3 passed", out)                                                 # the local worker and the digest still pass


class BigBattles(unittest.TestCase):
    """lumovideo 1.3.1: a sound is synthesised once per variant, not once per shot (a 360-shot battle took 54 s, now about 5)."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("lumovideo_v22", str(ROOT / "videokit" / "lumovideo.py"))
        cls.lv = importlib.util.module_from_spec(spec)
        sys.modules["lumovideo_v22"] = cls.lv
        spec.loader.exec_module(cls.lv)

    def battle(self, zombies=40, soldiers=4, shots=40):
        lv, rnd = self.lv, random.Random(3)
        sol = [lv.Actor("S%d" % i, "#3a7d44", x=150 + 60 * i, weapon="rifle", look="soldier", hp=50) for i in range(soldiers)]
        zs = []
        for i in range(zombies):
            z = lv.Actor("Z%d" % i, "#7fb069", x=900 + rnd.uniform(0, 600), facing=-1, look="zombie", hp=2)
            z.walk(0.5 + i * 0.3, to=420 + rnd.uniform(0, 80), speed=70, gait="zombie")
            zs.append(z)
        for s in sol:
            for k in range(shots):
                s.shoot(1.0 + k * 0.45 + rnd.uniform(0, 0.2), target=rnd.choice(zs), hit=True, kill=(k % 3 == 0), burst=2)
        return lv.Show("city_night", sol + zs, duration=25)

    def test_a_big_battle_compiles_quickly(self):
        show = self.battle()
        t0 = time.time()
        show.summary()
        took = time.time() - t0
        self.assertLess(took, 10.0, "%.1fs (it took ~25 s before the sound cache)" % took)
        self.assertEqual(show.framing()["offscreen"] <= show.framing()["events"], True)

    def test_each_gunshot_is_synthesised_once_per_variant(self):
        lv = self.lv
        count = {"n": 0}
        orig = lv.sfx.gunshot

        def counting(*a, **k):
            count["n"] += 1
            return orig(*a, **k)
        lv.sfx.gunshot = counting
        try:
            show = self.battle(zombies=10, soldiers=3, shots=30)
            show.summary()
        finally:
            lv.sfx.gunshot = orig
        self.assertLessEqual(count["n"], 12, count)                                      # 180 shots, a handful of distinct sounds

    def test_the_cache_does_not_change_the_sound(self):
        lv = self.lv
        a, b = self.battle(zombies=6, soldiers=2, shots=8), self.battle(zombies=6, soldiers=2, shots=8)
        a.summary()
        b.summary()
        self.assertEqual(len(a._snd), len(b._snd))
        self.assertEqual([round(x[0], 3) for x in a._snd], [round(x[0], 3) for x in b._snd])


class QuietStartup(unittest.TestCase):
    """No info table under the banner; the details live in /status; plain wording."""

    def run_cli(self, stdin, **cfg_env):
        import shutil
        wd = Path(tempfile.mkdtemp(prefix="quiet_"))
        (wd / "ws").mkdir()
        env = dict(os.environ, LUMO_HOME=str(wd / "home"), OPENROUTER_API_KEY="sk-or-test-1234567890", NO_COLOR="1", PYTHONIOENCODING="utf-8", LUMO_NO_ANIM="1",
                   LUMO_API_BASE="http://127.0.0.1:9/api/v1")
        env.update(cfg_env)
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", T21.SMART], input=stdin, env=env, capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        self.addCleanup(shutil.rmtree, str(wd), True)
        return p.stdout + p.stderr

    def test_the_startup_has_the_logo_and_no_table(self):
        out = self.run_cli("/exit\n")
        self.assertIn("C O D E", out)
        self.assertIn("/help for commands", out)
        for gone in ("provider ", "fallback", "history/ (automatic)", "outside: ask", "Ask anything", "╭─ session", "switches model on errors"):
            self.assertNotIn(gone, out, gone)

    def test_status_still_has_the_details(self):
        out = self.run_cli("/status\n/exit\n")
        for needle in ("provider", "workspace", "permissions", "history"):
            self.assertIn(needle, out)

    def test_the_prompt_line_says_multi_in_words(self):
        from lumo.cli import status_line
        from lumo.ui import ANSI_RE
        on = ANSI_RE.sub("", status_line(make_ctx(multiagent=True)))
        off = ANSI_RE.sub("", status_line(make_ctx()))
        self.assertIn("multi", on)
        self.assertNotIn("multi", off)
        self.assertNotIn("◈", on)

    def test_the_router_warning_is_one_plain_sentence(self):
        import shutil
        wd = Path(tempfile.mkdtemp(prefix="quiet2_"))
        (wd / "ws").mkdir()
        env = dict(os.environ, LUMO_HOME=str(wd / "home"), OPENROUTER_API_KEY="sk-or-test-1234567890", NO_COLOR="1", LUMO_NO_ANIM="1", LUMO_API_BASE="http://127.0.0.1:9/api/v1")
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", "openrouter/free"], input="/exit\n", env=env, capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        self.addCleanup(shutil.rmtree, str(wd), True)
        self.assertIn("openrouter/free picks a different model on every request. Choose one with /models.", p.stdout + p.stderr)

    def test_the_prompt_tells_the_model_how_to_write(self):
        from lumo.prompts import build_system
        text = build_system(make_ctx(), "build")
        self.assertIn("Write like a person who knows the subject", text)
        for phrase in ("Great question", "Dengan senang hati", "Semoga membantu"):
            self.assertIn(phrase, text)                                 # named as things NOT to say
        self.assertIn("no exclamation marks, no emojis", text)

    def test_no_user_facing_text_of_multi_agent_uses_decorative_symbols(self):
        src = (ROOT / "lumo" / "multiagent.py").read_text()
        for sym in ("◈", "✦ ", "↺", "↻"):
            self.assertNotIn(sym, src.replace('"✦"', ""), sym)          # the beam's spark in banner.py is a drawing; here only words


if __name__ == "__main__":
    unittest.main()
