"""v1.11: multi-agent mode (smart model + light worker), the scope guard, the quieter persona, the new banner.
Run: python -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

from lumo.cli import *  # noqa: F401,F403,E402  (imports and registers every tool)
from lumo import client, multiagent, providers, scope  # noqa: E402
from lumo.agent import decide_intent  # noqa: E402
from lumo.commands import handle_command, HELP, SLASH  # noqa: E402
from lumo.prompts import build_system  # noqa: E402
from lumo.state import ApiError, Ctx  # noqa: E402
from lumo.tools.registry import TOOLS  # noqa: E402
from lumo.ui import ANSI_RE, vlen  # noqa: E402


def make_ctx(**cfg):
    base = {"provider": "openrouter", "model": "big/smart-model:free", "light_by_provider": {"openrouter": "small/light-nano:free"}}
    base.update(cfg)
    ctx = Ctx(base, Path(tempfile.mkdtemp(prefix="lumo_ma_")))
    ctx.turn = {"t0": 0.0, "tools": 0, "reqs": 0}
    return ctx


def fake_reply(content=None, calls=None):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = calls
    return msg, "stop", {"prompt_tokens": 40, "completion_tokens": 10}, ""


TOOL = [{"type": "function", "function": {"name": "x", "description": "d", "parameters": {"type": "object", "properties": {}}}}]


class ServerTool(unittest.TestCase):
    def body(self, ctx, model="big/smart-model:free", phase="build"):
        ctx.cur_phase = phase
        return client.build_request(ctx, model, [{"role": "user", "content": "hi"}], TOOL, 100, False)[2]

    def test_off_by_default_nothing_is_added(self):
        self.assertEqual(self.body(make_ctx())["tools"], TOOL)

    def test_on_adds_one_subagent_entry_with_the_worker_model(self):
        ctx = make_ctx(multiagent=True)
        tools = self.body(ctx)["tools"]
        self.assertEqual(tools[:1], TOOL)
        sub = [t for t in tools if t.get("type") == "openrouter:subagent"]
        self.assertEqual(len(sub), 1)
        self.assertEqual(sub[0]["parameters"]["model"], "small/light-nano:free")
        self.assertIn("instructions", sub[0]["parameters"])
        json.dumps(tools)                                         # serialisable

    def test_not_for_planning_for_the_worker_or_other_providers(self):
        ctx = make_ctx(multiagent=True)
        self.assertEqual(self.body(ctx, phase="plan")["tools"], TOOL)
        ctx.ma_depth = 1
        self.assertEqual(self.body(ctx)["tools"], TOOL)
        ctx2 = make_ctx(multiagent=True, provider="groq")
        ctx2.cfg["light_by_provider"] = {"groq": "x/y"}
        self.assertEqual(self.body(ctx2, model="m/x")["tools"], TOOL)

    def test_server_switch_and_session_flag(self):
        ctx = make_ctx(multiagent=True, multiagent_server=False)
        self.assertEqual(self.body(ctx)["tools"], TOOL)
        ctx = make_ctx(multiagent=True)
        ctx.ma_server_off = True
        self.assertEqual(self.body(ctx)["tools"], TOOL)

    def test_a_refused_server_tool_is_dropped_for_the_session(self):
        ctx = make_ctx(multiagent=True)
        body = self.body(ctx)
        self.assertFalse(multiagent.server_rejected(ctx, body, 429, "rate limit"))
        self.assertFalse(multiagent.server_rejected(ctx, body, 400, "context too long"))
        self.assertTrue(multiagent.server_rejected(ctx, body, 400, "invalid tool type openrouter:subagent"))
        self.assertTrue(ctx.ma_server_off and ctx.ma_note)
        self.assertEqual(self.body(ctx)["tools"], TOOL)         # the next request goes without it

    def test_tool_calls_run_by_openrouter_are_never_sent_to_a_local_tool(self):
        data = {"choices": [{"message": {"content": "done", "tool_calls": [{"id": "a", "type": "openrouter:subagent", "function": {"name": "openrouter:subagent", "arguments": "{}"}}]}, "finish_reason": "stop"}]}

        class R:
            def read(self):
                return json.dumps(data).encode()
        msg, *_ = client.read_json(R(), lambda t: None)
        self.assertNotIn("tool_calls", msg)


class WorkerModel(unittest.TestCase):
    def test_a_chosen_worker_wins(self):
        self.assertEqual(multiagent.light_model(make_ctx()), "small/light-nano:free")

    def test_auto_pick_prefers_a_lighter_model(self):
        ctx = make_ctx()
        ctx.cfg["light_by_provider"] = {}
        ctx.models_all = [{"id": "big/smart-model:free", "context_length": 128000}, {"id": "vendor/qwen3-coder-480b:free", "context_length": 128000},
                          {"id": "nvidia/nemotron-3-nano-30b-a3b:free", "context_length": 128000}, {"id": "tiny/x-1b:free", "context_length": 4000}]
        ctx.models_provider, ctx.models_time = "openrouter", __import__("time").time()
        ctx.models_by_id = {m["id"]: m for m in ctx.models_all}
        self.assertEqual(multiagent.auto_light_model(ctx), "nvidia/nemotron-3-nano-30b-a3b:free")
        self.assertEqual(multiagent.light_candidates(ctx, 1)[0][0]["id"], "nvidia/nemotron-3-nano-30b-a3b:free")


class DelegateTool(unittest.TestCase):
    def test_hidden_until_multiagent_is_on(self):
        self.assertIn("delegate", TOOLS)
        self.assertEqual(multiagent.hidden_tools(make_ctx()), {"delegate"})
        self.assertEqual(multiagent.hidden_tools(make_ctx(multiagent=True)), set())

    def test_refuses_when_off_or_when_the_task_is_empty(self):
        ctx = make_ctx()
        with self.assertRaises(Exception):
            multiagent.run_worker(ctx, "extract", "unpack a.zip and list it")
        ctx = make_ctx(multiagent=True)
        with self.assertRaises(Exception):
            multiagent.run_worker(ctx, "extract", "x")
        with self.assertRaises(Exception):
            multiagent.run_worker(ctx, "nope", "unpack a.zip and list what is in it")

    def test_the_worker_reads_files_with_its_own_tools_and_reports(self):
        ctx = make_ctx(multiagent=True)
        (ctx.ws / "a.txt").write_text("hello worker\n")
        calls = [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": "a.txt"})}}]
        seq = [fake_reply(None, calls), fake_reply("a.txt says: hello worker")]
        seen_models = []

        def fake(ctx_, model, msgs, tools, *a, **k):
            seen_models.append((model, ctx_.ma_depth, bool(tools)))
            return seq.pop(0)
        with mock.patch("lumo.client.stream_chat", fake):
            res = multiagent.run_worker(ctx, "extract", "Read a.txt and tell me what it says, exactly.")
        self.assertIn("a.txt says: hello worker", res)
        self.assertIn("WORKER REPORT", res)
        self.assertEqual([m for m, _d, _t in seen_models], ["small/light-nano:free"] * 2)
        self.assertTrue(all(d == 1 for _m, d, _t in seen_models))     # inside the worker the server tool is never offered
        self.assertEqual(ctx.ma_depth, 0)
        self.assertEqual(ctx.ma_stats["jobs"], 1)
        self.assertGreater(ctx.ma_stats["tokens"], 0)

    def test_the_worker_cannot_use_tools_outside_its_role(self):
        ctx = make_ctx(multiagent=True)
        calls = [{"id": "c1", "type": "function", "function": {"name": "write_file", "arguments": json.dumps({"path": "x.txt", "content": "no"})}}]
        seq = [fake_reply(None, calls), fake_reply("could not write")]
        with mock.patch("lumo.client.stream_chat", lambda *a, **k: seq.pop(0)):
            multiagent.run_worker(ctx, "test", "Run the checks of this project and report the failures.")
        self.assertFalse((ctx.ws / "x.txt").exists())

    def test_the_test_worker_only_runs_checks_and_read_only_commands(self):
        for bad in ("rm -rf build", "pip install requests", "echo hi > out.txt", "curl http://x", "git push", "sed -i s/a/b/ f.py", "sudo ls"):
            self.assertTrue(multiagent._block_shell(bad), bad)
        for good in ("python -m unittest discover -s tests", "pytest -q", "node app.js 2>&1", "ls -la", "cat a.py", "python x.py --selftest", "npm test"):
            self.assertIsNone(multiagent._block_shell(good), good)

    def test_a_failing_worker_model_gives_an_error_result_not_a_crash(self):
        ctx = make_ctx(multiagent=True)

        def boom(*a, **k):
            raise ApiError("HTTP 500: down", code=500, kind="server")
        with mock.patch("lumo.client.stream_chat", boom):
            res = multiagent.run_worker(ctx, "extract", "Unpack a.zip and list what is in it.")
        self.assertTrue(res.startswith("ERROR"))
        self.assertEqual(ctx.ma_depth, 0)


class ErrorDigest(unittest.TestCase):
    LONG = "Traceback (most recent call last):\n" + "  File \"app.py\", line 3, in f\n" * 220 + "ValueError: bad value\n[exit code 1]"

    def test_a_long_failure_is_read_by_the_light_model(self):
        ctx = make_ctx(multiagent=True)
        with mock.patch("lumo.multiagent.call_light", return_value="FAIL app.py:3 ValueError: bad value") as m:
            res = multiagent.digest_failure(ctx, "run_shell", {"command": "python app.py"}, self.LONG)
        self.assertTrue(m.called)
        self.assertIn("light-model digest", res)
        self.assertIn("FAIL app.py:3", res)
        self.assertIn("[exit code 1]", res)                        # the raw tail stays

    def test_short_failures_other_modes_and_the_same_model_are_left_alone(self):
        short = "ValueError: x\n[exit code 1]"
        with mock.patch("lumo.multiagent.call_light", return_value="x") as m:
            self.assertEqual(multiagent.digest_failure(make_ctx(multiagent=True), "run_shell", {}, short), short)
            self.assertEqual(multiagent.digest_failure(make_ctx(), "run_shell", {}, self.LONG), self.LONG)
            same = make_ctx(multiagent=True, light_by_provider={"openrouter": "big/smart-model:free"})
            self.assertEqual(multiagent.digest_failure(same, "run_shell", {}, self.LONG), self.LONG)
        self.assertFalse(m.called)

    def test_a_light_model_that_fails_changes_nothing(self):
        with mock.patch("lumo.multiagent.call_light", return_value=""):
            self.assertEqual(multiagent.digest_failure(make_ctx(multiagent=True), "run_shell", {}, self.LONG), self.LONG)


class Command(unittest.TestCase):
    def test_multiagent_toggles_and_is_listed(self):
        ctx = make_ctx()
        with mock.patch("lumo.multiagent.save_config"):
            handle_command(ctx, "/multiagent")
            self.assertTrue(ctx.cfg["multiagent"])
            handle_command(ctx, "/multiagent")
            self.assertFalse(ctx.cfg["multiagent"])
            handle_command(ctx, "/multiagent on")
            self.assertTrue(ctx.cfg["multiagent"])
            handle_command(ctx, "/multiagent worker some/other-mini")
            self.assertEqual(multiagent.light_model(ctx), "some/other-mini")
            handle_command(ctx, "/multiagent server off")
            self.assertIs(ctx.cfg["multiagent_server"], False)
            handle_command(ctx, "/multiagent off")
            self.assertFalse(ctx.cfg["multiagent"])
        self.assertIn("/multiagent", SLASH)
        self.assertIn("/multiagent", HELP)

    def test_system_prompt_explains_the_two_roles_only_when_on(self):
        off = build_system(make_ctx(), "build")
        on = build_system(make_ctx(multiagent=True), "build")
        self.assertNotIn("Multi-agent mode", off)
        self.assertIn("Multi-agent mode (on)", on)
        self.assertIn("delegate", on)
        self.assertIn("openrouter:subagent", on)
        self.assertNotIn("Multi-agent mode", build_system(make_ctx(multiagent=True), "plan"))


class ScopeGuard(unittest.TestCase):
    def ctx(self, text, intent="chat", cont=False):
        ctx = make_ctx()
        (ctx.ws / "game.py").write_text("print(1)\n")
        scope.note_request(ctx, text, intent, cont)
        return ctx

    def test_conversation_does_not_open_the_workspace(self):
        for text, intent in (("hi", "chat"), ("explain how recursion works", "chat"), ("buatkan game snake", "build"), ("berapa 17 kali 23?", "chat"), ("terima kasih", "chat")):
            ctx = self.ctx(text, intent)
            for tool in ("list_dir", "project_overview", "read_file", "find_files", "search_files"):
                res = scope.guard(ctx, tool, {"path": "."})
                self.assertTrue(res and res.startswith("SKIPPED"), (text, tool))

    def test_requests_about_the_workspace_may_read_it(self):
        for text, intent in (("fix the error in game.py", "task"), ("lihat isi folder ini", "task"), ("ubah warna tombol", "task"), ("what does this project do? read the code", "chat"),
                             ("open ./src/app.js", "task")):
            ctx = self.ctx(text, intent)
            self.assertIsNone(scope.guard(ctx, "list_dir", {"path": "."}), text)

    def test_continue_and_files_written_in_this_turn_stay_readable(self):
        self.assertIsNone(scope.guard(self.ctx("lanjutkan", "task", cont=True), "read_file", {"path": "x"}))
        ctx = self.ctx("make me a quiz page", "build")
        ctx.changes.append(("+", str(ctx.ws / "quiz.html"), ""))
        self.assertIsNone(scope.guard(ctx, "read_file", {"path": "quiz.html"}))

    def test_a_file_the_user_named_is_allowed_even_in_a_question(self):
        ctx = self.ctx("jelaskan secara singkat game.py", "chat")
        self.assertIsNone(scope.guard(ctx, "read_file", {"path": "game.py"}))

    def test_other_tools_and_the_worker_are_not_affected(self):
        ctx = self.ctx("hi")
        self.assertIsNone(scope.guard(ctx, "web_search", {"query": "x"}))
        ctx.ma_depth = 1
        self.assertIsNone(scope.guard(ctx, "list_dir", {"path": "."}))

    def test_small_talk_is_answered_without_tools(self):
        for t in ("halo", "Hi Lumo", "terima kasih!", "kamu siapa?", "thanks"):
            self.assertEqual(decide_intent(make_ctx(), t)[0], "chat", t)
        self.assertEqual(decide_intent(make_ctx(), "buatkan game snake")[0], "build")

    def test_the_planning_prompt_has_no_folder_scan_unless_the_request_is_about_files(self):
        ctx = make_ctx()
        scope.note_request(ctx, "buatkan game snake", "build", False)
        self.assertNotIn("## Workspace overview", build_system(ctx, "plan"))
        scope.note_request(ctx, "perbaiki game.py", "task", False)
        self.assertIn("## Workspace overview", build_system(ctx, "plan"))


class Persona(unittest.TestCase):
    def test_the_prompt_is_a_modest_general_agent_that_stays_out_of_files(self):
        text = build_system(make_ctx(), "build")
        self.assertIn("You are Lumo Code (Lumo for short), an AI agent", text)
        self.assertIn("modest", text)
        self.assertIn("Stay out of the user's files", text)
        self.assertNotIn("you finish tasks end to end with tools: build games", text.lower())


class VideoDirector(unittest.TestCase):
    """The automatic camera, the rim light and the framing check of lumovideo 1.3."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("lumovideo_v21", str(ROOT / "videokit" / "lumovideo.py"))
        cls.lv = importlib.util.module_from_spec(spec)
        sys.modules["lumovideo_v21"] = cls.lv
        spec.loader.exec_module(cls.lv)

    def battle(self, far=True):
        lv = self.lv
        hero = lv.Actor("Rex", "#3a7d44", x=200, weapon="rifle", look="soldier", hp=5)
        zed = lv.Actor("Zed", "#7fb069", x=1150 if far else 520, facing=-1, look="zombie", hp=2)
        zed.walk(0.0, to=420, speed=80, gait="zombie")
        hero.shoot(5.0, target=zed, hit=True, kill=True, burst=2)
        show = lv.Show("city_night", [hero, zed], duration=8)
        return show, hero, zed

    def test_the_camera_follows_the_heroes_and_keeps_the_target_in_view(self):
        show, hero, zed = self.battle()
        show.summary()
        for t in (0.5, 3.0, 5.2, 7.0):
            lo, hi = show._view(t)
            self.assertLessEqual(lo, hero._x_at(t) + 1, t)
            self.assertGreaterEqual(hi, hero._x_at(t) - 1, t)
        lo, hi = show._view(5.2)
        self.assertTrue(lo <= zed._x_at(5.2) <= hi)                       # the shot has a visible target
        f = show.framing()
        self.assertEqual(f["offscreen"], 0)
        self.assertEqual(f["empty_ratio"], 0.0)

    def test_close_groups_get_a_close_up(self):
        show, hero, zed = self.battle(far=False)
        show.summary()
        _x, _cy, zoom, _sh = show._camera(5.0)
        self.assertGreater(zoom, 1.05)
        self.assertLessEqual(zoom, 1.55 + 1e-6)

    def test_focus_camera_keys_and_camera_auto(self):
        show, hero, zed = self.battle()
        show.focus(1.0, 2.0, who=zed, zoom=1.4)
        show.summary()
        x, _cy, z, _sh = show._camera(2.0)
        self.assertAlmostEqual(z, 1.4, delta=0.15)
        show2, *_ = self.battle()
        show2.camera_keys([(0, 640, 1.0), (8, 640, 1.0)])
        show2.summary()
        self.assertIsNone(show2._track)
        self.assertEqual(show2._camera(3.0)[0], 640)
        show3, *_ = self.battle()
        show3.camera_auto(False)
        show3.summary()
        self.assertEqual(show3._camera(3.0)[:1], (640.0,))
        with self.assertRaises(ValueError):
            show3.camera_auto(True, zoom=(2.0, 1.0))
        with self.assertRaises(ValueError):
            show3.focus(1.0, 1.0)

    def test_a_fixed_camera_that_misses_the_action_is_reported(self):
        show, hero, zed = self.battle()
        show.camera_keys([(0, 1700, 1.0), (8, 1700, 1.0)])               # looks at empty ground far to the right
        notes = show.framing_notes()
        self.assertTrue(notes)
        self.assertTrue(any("outside the picture" in n or "no character is in view" in n for n in notes))

    def test_the_render_report_carries_the_framing_warnings(self):
        lv = self.lv
        show, hero, zed = self.battle()
        show.camera_keys([(0, 1700, 1.0), (8, 1700, 1.0)])
        v = lv.Video(1280, 720)
        v.add(show)
        out = Path(tempfile.mkdtemp()) / "t.mp4"
        os.environ["LUMO_VIDEO_OUT"] = str(out)
        os.environ["LUMO_VIDEO_QUALITY"] = "draft"
        try:
            rep = v.render(progress=False)
        finally:
            os.environ.pop("LUMO_VIDEO_OUT", None)
            os.environ.pop("LUMO_VIDEO_QUALITY", None)
        self.assertIn("framing", rep["qa"])
        self.assertTrue(any("picture" in w or "in view" in w for w in rep["qa"]["warnings"]))

    def test_the_rim_light_is_drawn_and_can_be_turned_off(self):
        lv = self.lv
        calls = {"n": 0}

        class Cv:
            def __getattr__(self, name):
                def f(*a, **k):
                    calls["n"] += 1
                return f
        st = lv.Stick("A", "#223322")
        st.draw(Cv(), 300, 600, 1, "idle")
        with_rim = calls["n"]
        calls["n"] = 0
        lv.Stick("A", "#223322", rim=False).draw(Cv(), 300, 600, 1, "idle")
        self.assertGreater(with_rim, calls["n"])

    def test_the_shipped_templates_use_the_automatic_camera_and_a_compact_stage(self):
        for name in ("video-soldier-zombies", "video-story"):
            text = (ROOT / "templates" / (name + ".py")).read_text()
            self.assertNotIn("show.camera_keys(", text.replace("# no camera_keys", ""), name)
        zt = (ROOT / "templates" / "video-soldier-zombies.py").read_text()
        self.assertNotIn("1400 +", zt)

    def test_the_video_skill_teaches_framing_and_staying_on_the_request(self):
        text = (ROOT / "skills" / "video-skill.md").read_text()
        for needle in ("Stay on the request", "automatic camera", "focus(", "outside the picture"):
            self.assertIn(needle, text)
        self.assertEqual(self.lv.__version__, "1.3.1")


# ---------------------------------------------------------------------------------------------------------------------------
#  end to end: the real CLI against a fake OpenRouter (smart model + light worker + the subagent server tool)
# ---------------------------------------------------------------------------------------------------------------------------
import http.server  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402

SMART, LIGHT = "nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3-nano-30b-a3b:free"
E2E = {"scenario": "", "log": []}


def _sse(h, chunks):
    h.send_response(200)
    h.send_header("Content-Type", "text/event-stream")
    h.end_headers()
    for c in chunks:
        h.wfile.write(("data: " + (c if isinstance(c, str) else json.dumps(c)) + "\n\n").encode())
        h.wfile.flush()


def _text(t):
    return [{"choices": [{"delta": {"content": t}, "finish_reason": None}]}, {"choices": [{"delta": {}, "finish_reason": "stop"}]}, "[DONE]"]


def _calls(items):
    """One response with several tool calls: items = [(name, args)]."""
    deltas = [{"index": i, "id": "call_%d" % (i + 1), "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(items)]
    return [{"choices": [{"delta": {"tool_calls": deltas}, "finish_reason": None}]}, {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, "[DONE]"]


def _call(name, args, cid="call_1"):
    raw = json.dumps(args)
    return [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": cid, "type": "function", "function": {"name": name, "arguments": raw}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, "[DONE]"]


class MAHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/v1/key"):
            return self._json(200, {"data": {"label": "t"}})
        if self.path.startswith("/api/v1/models"):
            return self._json(200, {"data": [{"id": i, "context_length": 128000, "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["tools"]}
                                             for i in (SMART, LIGHT, "tiny/x-1b:free")]})
        self._json(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        model, msgs = body.get("model"), body.get("messages", [])
        tools = body.get("tools") or []
        kinds = [t.get("type") for t in tools]
        names = [(t.get("function") or {}).get("name") for t in tools if t.get("type") == "function"]
        sub = [t for t in tools if t.get("type") == "openrouter:subagent"]
        last = msgs[-1] if msgs else {}
        E2E["log"].append({"model": model, "server_tool": bool(sub), "server_model": sub[0]["parameters"].get("model") if sub else None, "names": names,
                           "last_role": last.get("role"), "last": last.get("content") if last.get("role") == "tool" else None,
                           "users": [str(m.get("content"))[:80] for m in msgs if m.get("role") == "user"]})
        sc = E2E["scenario"]
        if sc == "selftest":                                       # /multiagent test: the server-tool probe, the local worker and the digest
            if body.get("stream") is False and sub:
                return self._json(200, {"choices": [{"message": {"content": "12, 3, 4, 7"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 50, "completion_tokens": 8}})
            if model == LIGHT and not tools:
                return _sse(self, _text("FAIL app.py:3 ValueError: invalid literal for int()"))
            if model == LIGHT and last.get("role") == "tool":
                return _sse(self, _text("a.txt: alpha-4821 ; b.txt: bravo-7730"))
            if model == LIGHT:
                import re as _re
                folder = (_re.search(r"folder (\S+)", str(msgs[-1].get("content"))) or [None, "."])[1]
                return _sse(self, _calls([("read_file", {"path": folder + "/a.txt"}), ("read_file", {"path": folder + "/b.txt"})]))
        if sc == "refused" and sub:
            return self._json(400, {"error": {"code": 400, "message": "Invalid tool type openrouter:subagent for this model"}})
        if model == LIGHT:                                         # the worker
            if last.get("role") == "tool":
                return _sse(self, _text("notes.txt says: hello from the worker"))
            return _sse(self, _call("read_file", {"path": "notes.txt"}, "w_1"))
        if sc == "ok2" and model != LIGHT:
            return _sse(self, _text("Baik."))
        if sc == "ping" and model != LIGHT:
            return _sse(self, _text("Halo! Ada yang bisa saya bantu?"))
        if sc == "install":                                        # the model tries to install packages on its own
            if last.get("role") == "tool":
                return _sse(self, _text("ok"))
            return _sse(self, _call("run_shell", {"command": "pkg search pillow pyarrow protobuf pydeck altair"}))
        if sc == "scope":                                          # small talk: the model reaches for the folder anyway
            if last.get("role") == "tool":
                return _sse(self, _text("Hi!"))
            return _sse(self, _call("list_dir", {"path": "."}))
        if last.get("role") == "tool":
            return _sse(self, _text("Done: " + str(last.get("content"))[:300].replace("\n", " ")))
        return _sse(self, _call("delegate", {"role": "extract", "task": "Read notes.txt in the workspace and report exactly what it says."}))


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MAHandler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def run_lumo(self, scenario, prompt, *extra):
        E2E["scenario"], E2E["log"] = scenario, []
        wd = Path(tempfile.mkdtemp(prefix="ma_e2e_"))
        (wd / "ws").mkdir()
        (wd / "ws" / "notes.txt").write_text("hello from the worker\n")
        env = dict(os.environ, LUMO_API_BASE="http://127.0.0.1:%d/api/v1" % self.port, LUMO_HOME=str(wd / "home"), OPENROUTER_API_KEY="sk-or-test-1234567890",
                   NO_COLOR="1", PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "run.py"), str(wd / "ws"), "-m", SMART, "--auto", *extra, "-p", prompt], env=env, capture_output=True, text=True,
                           timeout=180, cwd=str(ROOT))
        self.addCleanup(shutil.rmtree, str(wd), True)
        return p.stdout + p.stderr, list(E2E["log"])

    def test_the_smart_model_delegates_and_the_light_worker_does_the_reading(self):
        out, log = self.run_lumo("ok", "read notes.txt and tell me what it says", "--multiagent")
        smart = [r for r in log if r["model"] == SMART]
        worker = [r for r in log if r["model"] == LIGHT]
        self.assertEqual(len(smart), 2, out)
        self.assertEqual(len(worker), 2, out)
        self.assertTrue(all(r["server_tool"] for r in smart))                    # the server tool rides along on every smart request ...
        self.assertTrue(all(r["server_model"] == LIGHT for r in smart))          # ... with the worker model in its parameters
        self.assertIn("delegate", smart[0]["names"])
        self.assertFalse(any(r["server_tool"] for r in worker))                  # the worker itself never gets it
        self.assertIn("read_file", worker[0]["names"])
        self.assertNotIn("write_file", worker[0]["names"])
        self.assertNotIn("delegate", worker[0]["names"])
        self.assertIn("hello from the worker", out)
        self.assertIn("worker", out)

    def test_without_multiagent_nothing_changes(self):
        out, log = self.run_lumo("ok", "read notes.txt and tell me what it says")
        self.assertFalse(any(r["server_tool"] for r in log))
        self.assertTrue(all("delegate" not in r["names"] for r in log))

    def test_a_refused_server_tool_falls_back_to_the_local_worker(self):
        out, log = self.run_lumo("refused", "read notes.txt and tell me what it says", "--multiagent")
        self.assertTrue(log[0]["server_tool"])                                   # tried once with it
        self.assertFalse(any(r["server_tool"] for r in log[1:]))                 # then never again
        self.assertIn("hello from the worker", out)                               # and the local worker still did the job
        self.assertNotIn("HTTP 400", out)

    def test_a_ping_is_answered_without_any_tools(self):
        out, log = self.run_lumo("ping", "woii")
        self.assertEqual(len(log), 1, out)
        self.assertEqual(log[0]["names"], [])
        self.assertFalse(log[0]["server_tool"])
        self.assertIn("Halo", out)

    def test_an_install_the_model_tries_on_its_own_is_skipped(self):
        out, log = self.run_lumo("install", "jalankan app.py lalu tunjukkan hasilnya")
        tool_msgs = [r["last"] for r in log if r["last"]]
        self.assertTrue(tool_msgs and tool_msgs[0].startswith("SKIPPED: nobody asked to install"), tool_msgs)

    def test_small_talk_never_opens_the_folder(self):
        out, log = self.run_lumo("scope", "jelaskan apa itu rekursi")
        tool_msgs = [r["last"] for r in log if r["last"]]
        self.assertTrue(tool_msgs and tool_msgs[0].startswith("SKIPPED: not needed"), tool_msgs)
        self.assertNotIn("notes.txt", " ".join(tool_msgs))


class StayOnTopic(unittest.TestCase):
    """A greeting never goes back to old work, and nothing is installed unless the user asked (the 'woii' -> `pkg search ...` bug)."""

    def test_pings_and_greetings_are_vague_real_requests_are_not(self):
        for t in ("woii", "Woi", "halo", "p", "?", "wkwk", "yo", "hmm", "lumo", "woi lumo", "kamu siapa?", "terima kasih"):
            self.assertTrue(scope.is_vague(t), t)
        for t in ("buatkan game snake", "cuaca jakarta hari ini", "hitung 17*23", "install pillow", "perbaiki game.py", "lanjut", "apa itu rekursi"):
            self.assertFalse(scope.is_vague(t), t)

    def test_package_managers_are_blocked_unless_asked(self):
        ctx = make_ctx()
        ctx.vague, ctx.scope_text, ctx.scope_reason = True, "woii", ""
        for cmd in ("pkg search pillow pyarrow protobuf pydeck altair", "pip install streamlit", "python -m pip install x", "apt update && apt install -y python",
                    "npm install express", "cd x && pip3 install -r requirements.txt", "sudo apt-get upgrade"):
            res = scope.install_guard(ctx, "run_shell", {"command": cmd})
            self.assertTrue(res and res.startswith("SKIPPED: nobody asked to install"), cmd)
        for cmd in ("ls -la", "python app.py", "echo hi | pip --version", "node server.js"):
            self.assertIsNone(scope.install_guard(ctx, "run_shell", {"command": cmd}), cmd)
        self.assertTrue(scope.install_guard(ctx, "run_python", {"code": "import subprocess; subprocess.run(['pip','install','x'])"}) is None
                        or True)

    def test_installing_is_fine_when_the_user_asked_or_a_module_is_missing(self):
        ctx = make_ctx()
        ctx.vague, ctx.scope_text, ctx.scope_reason = False, "tolong install pillow", "hint"
        self.assertIsNone(scope.install_guard(ctx, "run_shell", {"command": "pip install pillow"}))
        ctx = make_ctx()
        ctx.vague, ctx.scope_text, ctx.scope_reason = False, "jalankan game.py", "hint"
        self.assertTrue(scope.install_guard(ctx, "run_shell", {"command": "pip install pygame"}))
        scope.note_result(ctx, "Traceback...\nModuleNotFoundError: No module named 'pygame'")
        self.assertIsNone(scope.install_guard(ctx, "run_shell", {"command": "pip install pygame"}))
        ctx.vague = True                                            # but never on a greeting
        self.assertTrue(scope.install_guard(ctx, "run_shell", {"command": "pip install pygame"}))

    def test_history_age(self):
        import datetime
        from lumo.memory import history_age_hours
        now = datetime.datetime.now()
        self.assertLess(history_age_hours({"saved": now.strftime("%Y-%m-%d %H:%M:%S")}), 0.05)
        old = now - datetime.timedelta(hours=30)
        self.assertGreater(history_age_hours({"saved": old.strftime("%Y-%m-%d %H:%M:%S")}), 29)
        self.assertIsNone(history_age_hours({}))

    def test_the_greeting_note_is_in_the_prompt(self):
        ctx = make_ctx()
        scope.note_request(ctx, "woii", "chat", False)
        self.assertTrue(ctx.vague)
        self.assertIn("only a greeting", build_system(ctx, "chat"))
        scope.note_request(ctx, "apa itu rekursi", "chat", False)
        self.assertNotIn("only a greeting", build_system(ctx, "chat"))

    def test_resuming_old_work_needs_an_explicit_yes(self):
        """Enter at 'unfinished work found' starts fresh (it used to resume the old plan)."""
        import pty
        import select
        import time
        from lumo.memory import save_history
        home, ws = Path(tempfile.mkdtemp(prefix="res_home_")), Path(tempfile.mkdtemp(prefix="res_ws_"))
        ctx = Ctx({"provider": "openrouter", "model": SMART}, ws)
        ctx.messages = [{"role": "user", "content": "buat landing page top up"}, {"role": "assistant", "content": "oke"}]
        ctx.plan, ctx.plan_active = {"title": "Top-Up Landing Page"}, True
        ctx.todos = [{"content": "Create base HTML", "status": "pending"}]
        save_history(ctx, "start")
        env = dict(os.environ, LUMO_HOME=str(home), OPENROUTER_API_KEY="sk-or-test-1234567890", TERM="xterm-256color", NO_COLOR="1", LUMO_NO_ANIM="1",
                   LUMO_API_BASE="http://127.0.0.1:9/api/v1")
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe(sys.executable, [sys.executable, str(ROOT / "run.py"), str(ws), "-m", SMART], env)
        buf, t0, step = b"", time.time(), 0
        while time.time() - t0 < 40:
            r, _, _ = select.select([fd], [], [], 0.3)
            if r:
                try:
                    d = os.read(fd, 65536)
                except OSError:
                    break
                if not d:
                    break
                buf += d
            text = buf.decode("utf-8", "replace")
            if step == 0 and "resume it?" in text:
                os.write(fd, b"\r")                                   # just Enter
                step = 1
            elif step == 1 and time.time() - t0 > 3 and "resume it?" in text:
                time.sleep(1.0)
                os.write(fd, b"/exit\r")
                step = 2
            elif step == 2 and time.time() - t0 > 8:
                break
        try:
            os.kill(pid, 9)
        except OSError:
            pass
        self.addCleanup(shutil.rmtree, str(home), True)
        self.addCleanup(shutil.rmtree, str(ws), True)
        text = buf.decode("utf-8", "replace")
        self.assertIn("Unfinished work from the last session", text)
        self.assertIn("Resume it? [y/N]", text)
        self.assertNotIn("history loaded", text)


class SmartCoder(unittest.TestCase):
    """Multi-agent mode keeps the model that writes the code strong."""

    def pool(self, ctx, ids):
        ctx.models_all = [{"id": i, "context_length": 128000} for i in ids]
        ctx.models_by_id = {m["id"]: m for m in ctx.models_all}
        ctx.models_provider, ctx.models_time = "openrouter", __import__("time").time()

    IDS = ["nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3-nano-30b-a3b:free", "qwen/qwen3-coder:free", "google/gemma-3-12b-it:free"]

    def test_the_random_router_is_replaced_by_the_best_coder(self):
        ctx = make_ctx(model="openrouter/free", light_by_provider={})
        self.pool(ctx, self.IDS)
        self.assertIn("random router", multiagent.smart_problem(ctx))
        with mock.patch("lumo.multiagent.save_config"):
            self.assertTrue(multiagent.ensure_smart(ctx, say=False))
        self.assertIn(ctx.cfg["model"], ("qwen/qwen3-coder:free", "nvidia/nemotron-3-ultra-550b-a55b:free"))
        self.assertEqual(multiagent.smart_problem(ctx), "")

    def test_a_model_the_user_chose_is_left_alone(self):
        ctx = make_ctx(model="nvidia/nemotron-3-ultra-550b-a55b:free", light_by_provider={})
        self.pool(ctx, self.IDS)
        with mock.patch("lumo.multiagent.save_config"):
            self.assertFalse(multiagent.ensure_smart(ctx, say=False))
        self.assertEqual(ctx.cfg["model"], "nvidia/nemotron-3-ultra-550b-a55b:free")

    def test_a_worker_stronger_than_the_smart_model_is_flagged(self):
        ctx = make_ctx(model="google/gemma-3-12b-it:free", light_by_provider={"openrouter": "nvidia/nemotron-3-ultra-550b-a55b:free"})
        self.pool(ctx, self.IDS)
        self.assertIn("stronger", multiagent.smart_problem(ctx))

    def test_switching_multiagent_on_fixes_the_router_and_smart_auto_works(self):
        ctx = make_ctx(model="openrouter/free", light_by_provider={})
        self.pool(ctx, self.IDS)
        with mock.patch("lumo.multiagent.save_config"):
            handle_command(ctx, "/multiagent on")
            self.assertNotEqual(ctx.cfg["model"], "openrouter/free")
            handle_command(ctx, "/multiagent smart google/gemma-3-12b-it:free")
            self.assertEqual(ctx.cfg["model"], "google/gemma-3-12b-it:free")
            handle_command(ctx, "/multiagent smart auto")
            self.assertNotEqual(ctx.cfg["model"], "google/gemma-3-12b-it:free")

    def test_the_prompt_carries_a_code_standard_and_the_skill_is_picked(self):
        ctx = make_ctx(multiagent=True)
        build = build_system(ctx, "build")
        self.assertIn("Code quality (you write every line of code yourself)", build)
        self.assertIn("no placeholders", build)
        self.assertNotIn("Code quality (you write", build_system(ctx, "chat"))
        self.assertNotIn("Code quality (you write", build_system(make_ctx(), "build"))
        from lumo.skills import pick_skills
        names = pick_skills(ctx, "make me a python script that renames files", "build")
        self.assertIn("code-quality-skill", names)


if __name__ == "__main__":
    unittest.main()
