"""Version 1.10: custom poses and moves, more attacks, Actor and Show (any 2D scene, guns, zombies), real 3D (Scene3D), the video_api catalog that
stops guessing, templates for other kinds of video, and a conversation that survives restarts."""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "videokit"))
os.environ.setdefault("LUMO_HOME", tempfile.mkdtemp(prefix="lumo_test_home_"))

from lumo.cli import *  # noqa: F401,F403,E402  (registers every tool)
from lumo.state import Ctx  # noqa: E402
from lumo.toolrun import exec_tool  # noqa: E402
from lumo.tools import video as video_tools  # noqa: E402
import lumovideo as lv  # noqa: E402

HAVE_PIL = lv.Image is not None
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(HAVE_PIL, "Pillow missing")
class TestCustomMovesAndPoses(unittest.TestCase):
    def tearDown(self):
        for n in [n for n in lv.MOVES if n not in lv._BUILTIN_MOVES]:
            del lv.MOVES[n]
        for n in [n for n in lv.POSES if n not in lv._BUILTIN_POSES]:
            del lv.POSES[n]

    def test_there_are_many_more_built_in_attacks_and_gestures(self):
        attacks = lv.moves(True)
        self.assertGreaterEqual(len(attacks), 20)
        for n in ("hook", "elbow", "knee", "axe_kick", "superman_punch", "palm_strike", "side_kick", "low_kick", "headbutt", "shoulder_charge", "dropkick", "hammer_fist", "flying_knee"):
            self.assertIn(n, attacks)
        for n in ("shoot", "reload", "throw", "wave", "cheer", "point", "salute", "surrender", "zombie_bite"):
            self.assertIn(n, lv.moves(False))
        self.assertGreaterEqual(len(lv.poses()), 70)

    def test_you_can_define_a_pose_and_a_move_and_a_fight_can_use_it(self):
        lv.define_pose("hands_up2", "guard", rua=165, rfa=175, lua=165, lfa=175)
        self.assertEqual(lv.resolve_pose("hands_up2")["rua"], 165)
        m = lv.define_move("spin_punch", [(0, "guard"), (0.15, "jab_wind"), (0.3, "cross", "out_quad"), (0.6, "guard")], hit=0.3, reach=80, dmg=11)
        self.assertEqual((m.name, m.dur, m.hit), ("spin_punch", 0.6, 0.3))
        self.assertIn("spin_punch", lv.moves(True))
        f = lv.Fight(lv.Stick("A", "#4aa3ff"), lv.Stick("B", "#ff5a5a"), seed=2)
        f.gap(0.2, 88, 0.4)
        f.attack("a", "spin_punch", at=1.0)
        f.attack("a", "round_kick", at=2.5, finisher=True)
        f.victory("a", at=4.5)
        self.assertGreaterEqual(sum(f.summary()["hits"]), 2)
        a = lv.Actor("X", x=300)
        a.play(0.5, "spin_punch")                                           # an attack is also an animation
        self.assertTrue(lv.Show("plain", [a], duration=2).summary())

    def test_bad_definitions_explain_what_is_wrong(self):
        cases = [(lambda: lv.define_move("jab", [(0, "guard"), (1, "jab")]), "built-in"),
                 (lambda: lv.define_move("x_move", [(0, "guard"), (1, "nopose")]), "Valid pose names"),
                 (lambda: lv.define_move("x_move", [(0, "guard"), (1, "jab")], hit=5.0), "inside the move"),
                 (lambda: lv.define_move("x_move", [(0, "guard"), (0.5, "jab"), (0.4, "guard")]), "must increase"),
                 (lambda: lv.define_move("Bad Name", [(0, "guard"), (1, "jab")]), "lowercase"),
                 (lambda: lv.define_pose("p_one", "guard", elbow=3), "pose angle"),
                 (lambda: lv.define_pose("guard", "guard", lean=3), "built-in"),
                 (lambda: lv.define_pose("p_two", "guard", lean="x"), "number")]
        for fn, needle in cases:
            with self.assertRaises(ValueError) as cm:
                fn()
            self.assertIn(needle, str(cm.exception))

    def test_unknown_names_come_with_the_closest_real_ones_and_the_full_list(self):
        for fn, near, kind in ((lambda: lv.resolve_pose("zombiee_stand"), "zombie_stand", "pose"), (lambda: lv.Stage("dojoo"), "dojo", "stage"),
                               (lambda: lv.sfx.get("punsh"), "punch", "sound effect"), (lambda: lv.ease(0.5, "in_out_cubc"), "in_out_cubic", "easing"),
                               (lambda: lv.Actor("x", look="zombi"), "zombie", "look")):
            with self.assertRaises(ValueError) as cm:
                fn()
            msg = str(cm.exception)
            self.assertIn("Did you mean", msg)
            self.assertIn(near, msg)
            self.assertIn("unknown " + kind, msg)
        f = lv.Fight(lv.Stick("A", "#4aa3ff"), lv.Stick("B", "#ff5a5a"))
        with self.assertRaises(ValueError) as cm:
            f.attack("a", "shamble", at=1.0)
        self.assertIn("define_move", str(cm.exception))
        self.assertIn("round_kick", str(cm.exception))

    def test_a_wrong_attribute_lists_the_real_ones(self):
        st = lv.Stick("A", "#4aa3ff")
        with self.assertRaises(AttributeError) as cm:
            st.attack("a", "jab")
        self.assertIn("Stick has no attribute 'attack'", str(cm.exception))
        self.assertIn("draw", str(cm.exception))
        with self.assertRaises(AttributeError) as cm:
            lv.Video(1280, 720).rendr()
        self.assertIn("Did you mean: render", str(cm.exception))
        v = lv.Video(1280, 720)
        self.assertFalse(hasattr(v, "nothing_here"))
        self.assertEqual(v.duration, 0.0)                                    # a property still works

    def test_every_gait_and_new_pose_draws_a_figure(self):
        c = lv.Canvas(1280, 720, 320, 180, ss=1, bg="#222222")
        st = lv.Stick("A", "#4aa3ff")
        for g in lv.GAITS:
            p = lv._gait_pose(g, 0.3)
            self.assertGreater(p["y"], 0, g)
            st.draw(c, 640, 500, 1, p, 0.0)
        for n in lv.poses():
            lv.resolve_pose(n)
        with self.assertRaises(ValueError):
            lv._gait_pose("moonwalk", 0.1)


@unittest.skipUnless(HAVE_PIL, "Pillow missing")
class TestActorAndShow(unittest.TestCase):
    @staticmethod
    def battle():
        hero = lv.Actor("Rex", "#3a7d44", x=220, weapon="rifle", look="soldier")
        zs = [lv.Actor("Z%d" % i, "#7fb069", x=1300 + 70 * i, facing=-1, look="zombie", hp=2) for i in range(3)]
        for i, z in enumerate(zs):
            z.walk(0.3 + 0.4 * i, to=330, speed=95, gait="zombie")
        t = 1.4
        for z in zs:
            hero.shoot(t, target=z, hit=True, burst=2)
            t += 0.9
        show = lv.Show("city_night", [hero] + zs, title="Test", duration=8)
        show.explode(6.5, x=600, radius=150)
        return show, hero, zs

    def test_shots_take_hp_and_zombies_fall_and_freeze_where_they_fell(self):
        show, hero, zs = self.battle()
        s = show.summary()
        self.assertEqual((s["shots"], s["kills"], s["fallen"]), (6, 3, ["Z0", "Z1", "Z2"]))
        self.assertEqual(s["alive"], ["Rex"])
        z = zs[0]
        x_dead = z._x_at(z._dead + 1.0)
        self.assertAlmostEqual(x_dead, z._x_at(z._dead + 3.0), places=3)
        self.assertGreater(x_dead, 331)
        self.assertEqual(z.pose_at(z._dead + 1.5)[1], "knockdown")

    def test_a_miss_does_not_hurt_and_an_actor_without_a_gun_cannot_shoot(self):
        hero = lv.Actor("R", x=200, weapon="rifle")
        z = lv.Actor("Z", x=700, facing=-1, look="zombie", hp=2)
        hero.shoot(1.0, target=z, hit=False, burst=3)
        s = lv.Show("plain", [hero, z], duration=4).summary()
        self.assertEqual((s["shots"], s["hits"], s["kills"]), (3, 0, 0))
        with self.assertRaises(ValueError) as cm:
            lv.Actor("U", x=100).shoot(1.0)
        self.assertIn("weapon='rifle'", str(cm.exception))

    def test_explosions_knock_down_everything_near(self):
        a, b, far = lv.Actor("A", x=500), lv.Actor("B", x=560), lv.Actor("C", x=1100)
        show = lv.Show("plain", [a, b, far], duration=4)
        show.explode(1.0, x=520, radius=120)
        s = show.summary()
        self.assertEqual(sorted(s["fallen"]), ["A", "B"])
        self.assertEqual(s["alive"], ["C"])

    def test_the_timeline_moves_turns_and_blends_poses(self):
        a = lv.Actor("A", x=100)
        a.walk(0.5, to=600, speed=100)
        a.pose(6.0, "salute", dur=1.0)
        a.say(1.0, "hi", dur=1.0)
        show = lv.Show("plain", [a], duration=8)
        show.summary()
        self.assertAlmostEqual(a._x_at(0.2), 100, places=3)
        self.assertAlmostEqual(a._x_at(3.0), 350, delta=1)
        self.assertAlmostEqual(a._x_at(7.0), 600, places=3)
        self.assertEqual((a._facing_at(0.1), a._facing_at(2.0)), (1, 1))
        self.assertEqual(a.pose_at(2.0)[1], "walk")
        self.assertEqual(a.pose_at(6.5)[1], "salute")
        keys = [k for k in a._tracks[0] if k not in ("y", "lift", "hx")]
        for n in range(len(a._tracks) - 1):
            self.assertLess(max(abs(a._tracks[n][k] - a._tracks[n + 1][k]) for k in keys), 16.0, n / 120.0)    # no snapping

    def test_the_scene_draws_every_few_frames_and_has_sound(self):
        show, hero, zs = self.battle()
        v = lv.Video(1280, 720, quality="draft")
        v.add(show)
        self.assertEqual(v.duration, 8.0)
        for n in range(0, int(v.duration * 60), 7):
            img = v.frame_at(n / 60.0, "draft", 60)
            self.assertEqual(img.size, (480, 270))
        self.assertGreater(len(v.sounds), 14)
        self.assertGreater(lv.ImageStat.Stat(v.frame_at(1.5, "draft").convert("L")).stddev[0], 8)

    def test_bad_actor_arguments_explain_themselves(self):
        for fn, needle in ((lambda: lv.Actor("a", weapon="laser"), "unknown weapon"), (lambda: lv.Actor("a").walk(1.0), "to="), (lambda: lv.Actor("a").walk(1.0, to=5, gait="moon"), "unknown gait"),
                           (lambda: lv.Actor("a").play(1.0, "shamble"), "define_move"), (lambda: lv.Actor("a").pose(1.0, "nope"), "unknown pose"), (lambda: lv.Actor("a").wave(-1), "0 or more")):
            with self.assertRaises(ValueError) as cm:
                fn()
            self.assertIn(needle, str(cm.exception))


@unittest.skipUnless(HAVE_PIL, "Pillow missing")
class TestScene3D(unittest.TestCase):
    @staticmethod
    def world():
        w = lv.Scene3D(duration=3)
        cube = w.box(1.5, 1.5, 1.5, color="#ff6b6b", pos=(-2, 0.75, 4))
        hero = w.person(color="#4aa3ff", pos=(0, 0, 4), yaw=-90)

        def animate(wd, t):
            cube.rot = (0, t * 50, 0)
            hero.play("wave", t % 1.4)
            wd.camera.orbit((0, 1, 4), 8, 3, t * 25)
        w.animate = animate
        return w

    def test_a_3d_scene_renders_shapes_a_figure_and_a_moving_camera(self):
        w = self.world()
        v = lv.Video(1280, 720, fps=30, quality="draft")
        v.add(w)
        a, b = v.frame_at(0.2, "draft", 30), v.frame_at(2.0, "draft", 30)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        self.assertGreater(lv.ImageStat.Stat(a.convert("RGB")).stddev[0], 12)
        self.assertEqual(v.frame_at(0.2, "draft", 30).tobytes(), a.tobytes())          # deterministic: a pure function of t

    def test_projection_puts_things_where_a_camera_would(self):
        w = lv.Scene3D(duration=1)
        w.camera.look((0, 1, -8), (0, 1, 0), 60)
        c = lv.Canvas(1280, 720, 320, 180, ss=1)
        w.draw(c, 0.0)
        centre = w.project((0, 1, 0))
        right = w.project((2, 1, 0))
        up = w.project((0, 3, 0))
        self.assertAlmostEqual(centre[0], 640, delta=1)
        self.assertAlmostEqual(centre[1], 360, delta=1)
        self.assertGreater(right[0], centre[0])
        self.assertLess(up[1], centre[1])
        self.assertIsNone(w.project((0, 1, -20)))                                      # behind the camera
        self.assertGreater(w.project((0, 1, 8))[2], centre[2])

    def test_a_figure_uses_any_pose_move_or_gait_including_your_own(self):
        lv.define_pose("test_pose_3d", "guard", rua=160)
        try:
            fig = lv.Figure3D()
            fig.set_pose("test_pose_3d")
            self.assertEqual(fig.pose["rua"], 160)
            fig.play("jab", 0.2).gait("zombie", 0.4)
            self.assertEqual(len(fig._parts()), 14)
            with self.assertRaises(ValueError):
                fig.play("shamble", 0.1)
        finally:
            del lv.POSES["test_pose_3d"]

    def test_a_2d_fight_can_be_shown_in_3d_with_the_same_choreography(self):
        a, b = lv.Stick("Aro", "#4aa3ff", gloves="#ff4d4d"), lv.Stick("Bima", "#ff5a5a")
        for stage in ("dojo", "city_night", "arena", "forest"):
            f = lv.Fight(a, b, stage=stage, seed=3)
            f.auto(duration=8, winner="a", seed=3)
            w = lv.Scene3D.from_fight(f)
            v = lv.Video(1280, 720, fps=30, quality="draft")
            v.add(w)
            self.assertAlmostEqual(v.duration, f.duration, places=2)
            self.assertGreater(len(v.sounds), 10)
            for T in (0.5, 3.0, 5.0, v.duration - 0.3):
                self.assertGreater(lv.ImageStat.Stat(v.frame_at(T, "draft", 30).convert("L")).stddev[0], 6, (stage, T))

    def test_painter_order_hides_what_is_behind(self):
        w = lv.Scene3D(duration=1, grid=None, outline=False)
        w.box(4, 4, 0.2, color="#ff0000", pos=(0, 2, 6))
        w.box(1, 1, 0.2, color="#0000ff", pos=(0, 2, 3))
        w.camera.look((0, 2, -4), (0, 2, 6), 60)
        v = lv.Video(1280, 720, quality="draft")
        v.add(w)
        img = v.frame_at(0.0, "draft").convert("RGB")
        px = img.getpixel((img.width // 2, img.height // 2))
        self.assertGreater(px[2], px[0])                                                # the near blue box covers the far red wall


class TestCatalogAndVideoApiTool(unittest.TestCase):
    def test_every_topic_lists_real_names(self):
        self.assertIn("overview", lv.catalog())
        for topic in lv.API_TOPICS:
            txt = lv.catalog(topic)
            self.assertGreater(len(txt), 100, topic)
        self.assertIn("round_kick", lv.catalog("moves"))
        self.assertIn("define_move", lv.catalog("moves"))
        self.assertIn("shoot(", lv.catalog("actor"))
        self.assertIn("explode(", lv.catalog("show"))
        self.assertIn("orbit(", lv.catalog("scene3d"))
        self.assertIn("poly(", lv.catalog("canvas"))
        self.assertIn("gunshot", lv.catalog("sound"))
        self.assertIn("city_night", lv.catalog("stages"))
        with self.assertRaises(ValueError) as cm:
            lv.catalog("moev")
        self.assertIn("moves", str(cm.exception))

    def test_the_command_line_prints_it_too(self):
        r = subprocess.run([sys.executable, str(ROOT / "videokit" / "lumovideo.py"), "--api", "moves"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("hook", r.stdout)

    @unittest.skipUnless(HAVE_PIL and HAVE_FFMPEG, "Pillow and ffmpeg needed")
    def test_every_recipe_in_the_catalog_runs(self):
        tmp = Path(tempfile.mkdtemp(prefix="recipes_"))
        for name, code in lv._RECIPES.items():
            p = tmp / (name + ".py")
            p.write_text(code)
            env = dict(os.environ, PYTHONPATH=str(ROOT / "videokit"), LUMO_VIDEO_QUALITY="draft", LUMO_VIDEO_OUT=str(tmp / (name + ".mp4")), LUMO_VIDEO_TOOL="1")
            r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, env=env, timeout=300)
            self.assertEqual(r.returncode, 0, (name, r.stderr[-400:]))
            self.assertTrue((tmp / (name + ".mp4")).is_file(), name)
        shutil.rmtree(tmp)

    def test_the_tool_answers_and_an_error_points_to_it(self):
        from lumo.tools.registry import TOOLS
        self.assertIn("video_api", TOOLS)
        ctx = Ctx({"model": "x/y"}, Path(tempfile.mkdtemp()))
        self.assertIn("Topics", exec_tool(ctx, "video_api", {}))
        self.assertIn("hook", exec_tool(ctx, "video_api", {"topic": "moves"}))
        self.assertTrue(exec_tool(ctx, "video_api", {"topic": "nope"}).startswith("ERROR: unknown api topic"))
        from lumo import safelimit
        rx = [r for names, r in safelimit.HIDDEN_UNLESS_ASKED if "video_api" in names][0]
        self.assertTrue(re.search(rx, "make a zombie video", re.I))

    @unittest.skipUnless(HAVE_PIL and HAVE_FFMPEG, "Pillow and ffmpeg needed")
    def test_a_script_with_an_invented_move_fails_with_help_not_with_a_guess(self):
        ws = Path(tempfile.mkdtemp(prefix="invented_"))
        (ws / "videos").mkdir()
        (ws / "videos" / "bad.py").write_text("from lumovideo import *\nf = Fight(Stick('a','#44f'), Stick('b','#f44'))\nf.attack('a', 'shamble', at=1.0)\nv = Video(1280, 720)\nv.add(f)\nv.render()\n")
        ctx = Ctx({"model": "x/y"}, ws)
        ctx.auto = True
        res = exec_tool(ctx, "render_video", {"script": "videos/bad.py", "quality": "draft"})
        self.assertTrue(res.startswith("ERROR: the script did not produce a video"), res)
        self.assertIn("unknown attack 'shamble'", res)
        self.assertIn("video_api", res)
        self.assertIn("define_move", res)
        shutil.rmtree(ws)


class TestTemplatesForOtherKindsOfVideo(unittest.TestCase):
    NEW = {"video-soldier-zombies": "zombies.py", "video-3d-fight": "fight3d.py", "video-3d-scene": "world3d.py", "video-story": "story.py"}

    def test_the_manifest_lists_them_and_the_skill_knows_them(self):
        m = json.loads((ROOT / "templates" / "manifest.json").read_text())["templates"]
        skill = (ROOT / "skills" / "video-skill.md").read_text()
        for name in self.NEW:
            self.assertIn(name, m)
            self.assertTrue((ROOT / "templates" / m[name]["file"]).is_file())
            self.assertIn(name, skill)
            ph = set(re.findall(r"__([A-Z_]+)__", (ROOT / "templates" / m[name]["file"]).read_text()))
            self.assertLessEqual(ph, set(m[name]["vars"]), name)                       # every placeholder has a default

    @unittest.skipUnless(HAVE_PIL, "Pillow missing")
    def test_each_template_passes_its_own_selftest(self):
        m = json.loads((ROOT / "templates" / "manifest.json").read_text())["templates"]
        tmp = Path(tempfile.mkdtemp(prefix="tpl_"))
        shutil.copy(str(ROOT / "videokit" / "lumovideo.py"), str(tmp / "lumovideo.py"))
        for name in self.NEW:
            text = (ROOT / "templates" / m[name]["file"]).read_text()
            for k, v in m[name]["vars"].items():
                text = text.replace("__%s__" % k, v)
            p = tmp / (name + ".py")
            p.write_text(text)
            r = subprocess.run([sys.executable, str(p), "--selftest"], capture_output=True, text=True, timeout=300, cwd=str(tmp))
            self.assertEqual(r.returncode, 0, (name, r.stdout[-300:], r.stderr[-500:]))
            self.assertIn("all checks passed", r.stdout)
        shutil.rmtree(tmp)

    def test_the_skill_says_any_video_can_be_made_and_never_to_invent_names(self):
        skill = (ROOT / "skills" / "video-skill.md").read_text()
        for needed in ("ANY video", "Never invent a name", "video_api", "never force a request into the nearest template", "define_move", "Scene3D", "Actor", "toolbox"):
            self.assertIn(needed, skill, needed)
        rules = (ROOT / "prompts" / "tool-rules.md").read_text()
        self.assertIn("video_api", rules)
        self.assertIn("## Memory", rules)


class TestTheConversationSurvivesARestart(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="mem_ws_"))
        self.ctx = Ctx({"model": "x/y"}, self.ws)

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_every_real_request_is_indexed_and_the_index_is_in_the_prompt(self):
        from lumo.memory import earlier_requests_block, note_request, requests_lines
        for t in ("buatkan video tentara lawan zombie", "y", "lanjut", "Continue the previous work from the last point", "tambah jurus baru", "   "):
            note_request(self.ctx, t)
        lines = requests_lines(self.ctx)
        self.assertEqual(len(lines), 2)
        self.assertIn("tentara lawan zombie", lines[0])
        block = earlier_requests_block(self.ctx)
        self.assertIn("Earlier conversations in this workspace", block)
        self.assertIn("tambah jurus baru", block)
        self.assertIn("history/transcript.md", block)
        for i in range(30):
            note_request(self.ctx, "request %d" % i)
        self.assertEqual(len(requests_lines(self.ctx)), 14)
        self.assertEqual(earlier_requests_block(Ctx({"model": "x/y"}, Path(tempfile.mkdtemp()))), "")

    def test_a_finished_conversation_is_restored_without_the_interrupted_work_framing(self):
        from lumo.memory import auto_restore, save_history
        self.ctx.messages = [{"role": "user", "content": "halo, namaku Budi"}, {"role": "assistant", "content": "Halo Budi!"}]
        self.ctx.task = "contoh"
        save_history(self.ctx, "exit")
        fresh = Ctx({"model": "x/y"}, self.ws)                                              # a restart: a new Ctx on the same workspace
        self.assertEqual(fresh.messages, [])
        st = auto_restore(fresh)
        self.assertEqual(st["reason"], "exit")
        self.assertEqual([m["content"] for m in fresh.messages], ["halo, namaku Budi", "Halo Budi!"])
        self.assertFalse(fresh.handoff)
        self.assertIsNone(auto_restore(Ctx({"model": "x/y"}, Path(tempfile.mkdtemp()))))

    def test_the_prompt_for_a_new_turn_carries_the_earlier_requests(self):
        from lumo.memory import note_request
        from lumo.prompts import build_system
        note_request(self.ctx, "buat video 3d kota")
        text = build_system(self.ctx, "build") if "phase" in build_system.__code__.co_varnames or True else ""
        self.assertIn("buat video 3d kota", text if isinstance(text, str) else json.dumps(text))

    def test_remember_command_switches_it_and_start_restores_by_default(self):
        from lumo.commands import handle_command
        with contextlib.redirect_stdout(io.StringIO()) as log:
            handle_command(self.ctx, "/remember off")
        self.assertFalse(self.ctx.cfg.get("auto_resume", True))
        self.assertIn("empty chat", log.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as log:
            handle_command(self.ctx, "/remember on")
        self.assertTrue(self.ctx.cfg.get("auto_resume", True))
        self.assertIn("keeps your conversation", log.getvalue())
        from lumo.commands import HELP, SLASH
        self.assertIn("/remember", SLASH)
        self.assertIn("/remember [on|off]", HELP)
        src = (ROOT / "lumo" / "cli.py").read_text()
        self.assertIn('ctx.cfg.get("auto_resume", True)', src)                          # on by default
        self.assertIn("auto_restore(ctx)", src)


class TestVersionAndDocs(unittest.TestCase):
    def test_versions_and_docs(self):
        from lumo.config import VERSION
        self.assertEqual(VERSION, "1.10.0")
        self.assertEqual(lv.__version__, "1.2.0")
        self.assertIn("## [1.10.0]", (ROOT / "CHANGELOG.md").read_text())
        readme = (ROOT / "README.md").read_text()
        for needed in ("video_api", "define_move", "Scene3D", "/remember", "Actor"):
            self.assertIn(needed, readme, needed)


if __name__ == "__main__":
    unittest.main()
