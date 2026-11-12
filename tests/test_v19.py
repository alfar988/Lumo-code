"""Version 1.9: smoother video (60 fps, motion blur, several cores), better fights, over 80 sound effects, sounds from the internet,
how to play, and the daily free-model limit."""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import wave
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
POSIX = sys.platform not in ("darwin", "win32")


def wav_bytes(freq=440.0, secs=0.3, rate=22050):
    import math
    import struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(int(rate * secs))))
    return buf.getvalue()


def raw_frames(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return hashlib.md5(r.stdout).hexdigest(), len(r.stdout)


def tiny_video(quality="draft", fps=None, blur=None):
    v = lv.Video(1280, 720, fps=fps, quality=quality, blur=blur)

    def scene(c, t):
        c.background("#101626", "#243b6b")
        c.circle(100 + 1000 * lv.ease(t / 2.0, "in_out_cubic"), 360, 50, fill="#ffd166")
    v.scene(2.0, scene)
    v.sfx("ding", 0.2)
    return v


class TestSmoothRendering(unittest.TestCase):
    def test_quality_presets_choose_the_frame_rate(self):
        v = lv.Video(1280, 720)
        self.assertEqual([v._geometry(q)[3] for q in ("draft", "standard", "hd", "fhd")], [24, 60, 60, 60])
        self.assertEqual(lv.Video(1280, 720, fps=30)._geometry("standard")[3], 30)
        self.assertEqual(lv.Video(1280, 720, fps=60)._geometry("draft")[3], 24)          # a number is an upper limit

    def test_motion_blur_is_automatic_for_low_frame_rates_only(self):
        v30, v60 = lv.Video(1280, 720, fps=30), lv.Video(1280, 720)
        self.assertEqual(v30._blur_samples("standard", 30), 3)
        self.assertEqual(v60._blur_samples("standard", 60), 1)
        self.assertEqual(v30._blur_samples("draft", 24), 1)
        self.assertEqual(lv.Video(1280, 720, blur=4)._blur_samples("standard", 60), 4)
        self.assertEqual(lv.Video(1280, 720, blur=False)._blur_samples("standard", 30), 1)
        with mock.patch.dict(os.environ, {"LUMO_VIDEO_BLUR": "2"}):
            self.assertEqual(v30._blur_samples("standard", 30), 2)

    def test_blur_samples_stay_inside_the_scene_so_a_cut_stays_a_cut(self):
        v = lv.Video(1280, 720)
        v.scene(1.0, lambda c, t: c.clear("#ff0000"))
        v.scene(1.0, lambda c, t: c.clear("#0000ff"))
        ts = v._sample_times(1.0, 30, 3)                      # the first frame of scene two
        self.assertTrue(all(x >= 1.0 for x in ts), ts)
        ts = v._sample_times(0.0, 30, 3)
        self.assertTrue(all(x >= 0.0 for x in ts), ts)
        self.assertEqual(v._sample_times(0.5, 60, 1), [0.5])

    @unittest.skipUnless(HAVE_PIL, "Pillow missing")
    def test_a_blurred_frame_is_the_mean_of_its_samples(self):
        v = lv.Video(1280, 720, fps=30, quality="draft")
        v.scene(2.0, lambda c, t: c.clear(lv.mix("#000000", "#ffffff", t / 2.0)))
        one = lv.ImageStat.Stat(v.render_frame(1.0, "draft", 30, 1).convert("L")).mean[0]
        three = lv.ImageStat.Stat(v.render_frame(1.0, "draft", 30, 3).convert("L")).mean[0]
        self.assertAlmostEqual(one, three, delta=1.5)                       # a linear ramp averages to its middle
        self.assertEqual(v.render_frame(1.0, "draft", 30, 1).tobytes(), v.frame_at(1.0, "draft", 30).tobytes())

    @unittest.skipUnless(HAVE_PIL and HAVE_FFMPEG, "Pillow and ffmpeg needed")
    def test_several_cores_give_exactly_the_same_video_as_one(self):
        tmp = Path(tempfile.mkdtemp(prefix="vid_par_"))
        hashes = []
        for workers in ("1", "2"):
            with mock.patch.dict(os.environ, {"LUMO_VIDEO_WORKERS": workers, "LUMO_VIDEO_OUT": str(tmp / ("w%s.mp4" % workers)), "LUMO_VIDEO_TOOL": "1"}):
                rep = tiny_video().render(progress=False)
            self.assertEqual(rep["workers"], int(workers))
            self.assertEqual(rep["fps"], 24)
            hashes.append(raw_frames(tmp / ("w%s.mp4" % workers)))
        self.assertEqual(hashes[0], hashes[1])
        self.assertGreater(hashes[0][1], 1000)
        shutil.rmtree(tmp)

    @unittest.skipUnless(HAVE_PIL, "Pillow missing")
    def test_a_script_with_hidden_state_is_drawn_on_one_core(self):
        state = {"n": 0}
        v = lv.Video(1280, 720, quality="draft")

        def scene(c, t):
            state["n"] += 1                                       # state that survives between frames: not safe to share
            c.clear(lv.mix("#000000", "#ffffff", (state["n"] % 50) / 50.0))
        v.scene(2.0, scene)
        self.assertFalse(v._stable("draft", 24))
        self.assertTrue(tiny_video()._stable("draft", 24))
        self.assertEqual(v._workers(200, 4, "draft", 24), 4)               # the check, not the worker count, decides

    @unittest.skipUnless(HAVE_PIL and HAVE_FFMPEG, "Pillow and ffmpeg needed")
    def test_an_error_inside_a_parallel_render_shows_the_real_traceback(self):
        v = lv.Video(1280, 720, quality="draft")

        def scene(c, t):
            if t > 1.5:
                raise ValueError("boom at the end")
            c.clear("#222222")
        v.scene(2.0, scene)
        tmp = Path(tempfile.mkdtemp(prefix="vid_err_"))
        with mock.patch.dict(os.environ, {"LUMO_VIDEO_WORKERS": "2", "LUMO_VIDEO_OUT": str(tmp / "x.mp4")}):
            with self.assertRaises(ValueError) as cm:
                v.render(progress=False)
        self.assertIn("boom at the end", str(cm.exception))
        shutil.rmtree(tmp)


class TestSoundEffects(unittest.TestCase):
    def test_about_seventy_effects_all_make_clean_audio(self):
        names = lv.sfx.names()
        self.assertGreaterEqual(len(names), 75)
        for needed in ("gunshot", "rifle", "reload", "groan", "zombie_death"):
            self.assertIn(needed, names)
        self.assertEqual(len(names), len(set(names)))
        for n in names:
            b = lv.sfx.get(n)
            self.assertGreater(len(b), 400, n)
            pk = max(abs(x) for x in b)
            self.assertTrue(0.02 < pk < 2.0, (n, pk))
            self.assertTrue(all(x == x for x in b[::97]), n)
        with self.assertRaises(ValueError) as cm:
            lv.sfx.get("not_a_sound")
        self.assertIn("punch", str(cm.exception))

    def test_every_take_is_different_but_a_variant_is_repeatable(self):
        a, b = lv.sfx.punch(), lv.sfx.punch()
        self.assertNotEqual(list(a), list(b))
        self.assertEqual(list(lv.sfx.kick(variant=2)), list(lv.sfx.kick(variant=2)))
        self.assertNotEqual(list(lv.sfx.kick(variant=2)), list(lv.sfx.kick(variant=3)))
        self.assertEqual(len({len(lv.sfx.step(0.4, s, variant=1)) for s in ("wood", "dirt", "grass", "gravel", "metal", "sand", "concrete")}) > 1, True)

    def test_harder_hits_are_louder_and_the_video_helper_adds_them(self):
        soft, hard = lv.sfx.punch(0.5, variant=1), lv.sfx.punch(1.4, variant=1)
        self.assertLess(max(map(abs, soft)), max(map(abs, hard)))
        v = lv.Video(1280, 720)
        buf = v.sfx("whoosh", 0.5, vol=0.6, dur=0.4)
        self.assertEqual(len(v.sounds), 1)
        self.assertAlmostEqual(len(buf) / float(lv.SR), 0.4, delta=0.02)

    def test_every_category_lists_real_effects(self):
        for cat, names in lv.SFX_CATEGORIES.items():
            for n in names:
                self.assertTrue(callable(getattr(lv.sfx, n)), (cat, n))

    def test_the_mixer_is_still_exact_and_never_clips(self):
        m = lv.Mixer(1.0)
        m.add(lv.sfx.explosion(), 0.1, 1.0)
        m.add(lv.sfx.boom(), 0.1, 1.0, pan=-0.5)
        path = Path(tempfile.mkdtemp()) / "m.wav"
        m.save(str(path))
        with wave.open(str(path)) as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (2, lv.SR))
            self.assertAlmostEqual(w.getnframes() / float(lv.SR), m.duration, delta=0.01)


class TestSoundFilesAndInternet(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="snd_"))
        self.env = mock.patch.dict(os.environ, {"LUMO_SOUNDS_DIR": str(self.dir / "sounds")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_wav_file_is_loaded_resampled_trimmed_and_normalised(self):
        p = self.dir / "tone.wav"
        p.write_bytes(wav_bytes(440, 0.3, 22050))
        b = lv.load_sound(str(p))
        self.assertAlmostEqual(len(b) / float(lv.SR), 0.3, delta=0.08)
        self.assertAlmostEqual(max(map(abs, b)), 0.9, delta=0.02)
        quiet = lv.load_sound(str(p), vol=0.5)
        self.assertAlmostEqual(max(map(abs, quiet)), 0.45, delta=0.02)
        part = lv.load_sound(str(p), start=0.1, dur=0.1)
        self.assertLess(len(part), len(b))
        with self.assertRaises(lv.SoundError):
            lv.load_sound(str(self.dir / "missing.wav"))
        self.assertEqual(len(lv.sfx.file(str(p))), len(b))

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
    def test_other_formats_go_through_ffmpeg(self):
        p = self.dir / "clip.bin"                                  # ffmpeg recognises the content, not the name
        p.write_bytes(wav_bytes(660, 0.25, 22050))
        b = lv.load_sound(str(p))
        self.assertAlmostEqual(len(b) / float(lv.SR), 0.25, delta=0.08)

    def test_downloads_only_https_and_never_private_addresses(self):
        for bad in ("http://example.org/a.wav", "ftp://example.org/a.wav", "https://127.0.0.1/a.wav", "https://localhost/a.wav", "https://10.0.0.5/a.wav",
                    "https://169.254.169.254/latest/meta-data"):
            with self.assertRaises(lv.SoundError, msg=bad):
                lv._safe_url(bad)

    def test_openverse_results_are_parsed_and_filtered(self):
        seen = {}

        def fake(url, headers=None):
            seen["url"] = url
            return {"results": [
                {"title": "Punch", "creator": "Ann", "license": "cc0", "license_version": "1.0", "url": "https://cdn.example.org/punch.wav", "duration": 1500,
                 "foreign_landing_url": "https://example.org/p", "source": "freesound"},
                {"title": "Way too long", "creator": "Bob", "license": "by", "url": "https://cdn.example.org/long.wav", "duration": 90000},
                {"title": "Insecure", "creator": "Cy", "license": "by", "url": "http://cdn.example.org/x.wav", "duration": 1000}]}
        with mock.patch.object(lv, "_json_get", fake):
            found = lv.find_sounds("punch impact", limit=5)
        self.assertEqual([f["title"] for f in found], ["Punch"])
        self.assertEqual(found[0]["license_code"], "cc0")
        self.assertIn("license=cc0%2Cpdm%2Cby", seen["url"])
        self.assertIn("q=punch+impact", seen["url"])
        with self.assertRaises(lv.SoundError):
            lv.find_sounds("   ")

    def test_freesound_is_used_when_a_key_is_set_and_the_key_stays_out_of_the_url(self):
        seen = {}

        def fake(url, headers=None):
            seen.update(url=url, headers=headers or {})
            return {"results": [{"id": 1, "name": "Kick", "duration": 0.8, "license": "https://creativecommons.org/publicdomain/zero/1.0/", "username": "dj",
                                 "previews": {"preview-hq-mp3": "https://cdn.freesound.org/previews/1/1_1-hq.mp3"}, "url": "https://freesound.org/people/dj/sounds/1/"},
                                {"id": 2, "name": "NC", "duration": 0.8, "license": "https://creativecommons.org/licenses/by-nc/4.0/", "username": "x",
                                 "previews": {"preview-hq-mp3": "https://cdn.freesound.org/previews/2/2_2-hq.mp3"}}]}
        with mock.patch.dict(os.environ, {"FREESOUND_API_KEY": "SECRETKEY123"}), mock.patch.object(lv, "_json_get", fake):
            found = lv.find_sounds("kick", limit=3)
        self.assertEqual([f["title"] for f in found], ["Kick"])
        self.assertEqual(found[0]["license"], "CC0")
        self.assertTrue(found[0]["url"].endswith(".mp3"))
        self.assertIn("freesound.org/apiv2/search/text", seen["url"])
        self.assertNotIn("SECRETKEY123", seen["url"])
        self.assertEqual(seen["headers"].get("Authorization"), "Token SECRETKEY123")

    def test_fetch_saves_a_wav_and_the_credit_and_reuses_it(self):
        item = {"title": "Punch", "creator": "Ann", "license": "CC0", "url": "https://cdn.example.org/punch.wav", "page": "https://example.org/p"}
        calls = []

        def fake(url, headers=None, **kw):
            calls.append(url)
            return wav_bytes(300, 0.4), "audio/wav"
        with mock.patch.object(lv, "_http_get", fake):
            p = lv.fetch_sound(item, name="punch impact", max_seconds=1.0)
            again = lv.fetch_sound(item, name="punch impact", max_seconds=1.0)
        self.assertTrue(os.path.isfile(p) and p.endswith(".wav"))
        self.assertEqual((p, len(calls)), (again, 1))
        self.assertIn("Ann", lv.sound_credits())
        self.assertIn("CC0", lv.sound_credits())
        self.assertFalse([f for f in os.listdir(os.path.dirname(p)) if f.startswith(".download")])

    def test_net_caches_and_falls_back_to_a_synthesised_effect_offline(self):
        item = {"title": "Whoosh", "creator": "Dee", "license": "CC0", "url": "https://cdn.example.org/w.wav", "duration": 0.5, "page": "https://example.org/w"}
        with mock.patch.object(lv, "find_sounds", lambda *a, **k: [item]), mock.patch.object(lv, "_http_get", lambda *a, **k: (wav_bytes(500, 0.3), "audio/wav")):
            first = lv.sfx.net("whoosh swing", n=1)
        self.assertGreater(len(first), 1000)
        self.assertTrue((self.dir / "sounds" / "index.json").is_file())

        def offline(*a, **k):
            raise lv.SoundError("no internet connection")
        with mock.patch.object(lv, "find_sounds", offline):
            cached = lv.sfx.net("whoosh swing", n=1)                      # served from the cache: no network needed
            self.assertEqual(len(cached), len(first))
            with contextlib.redirect_stdout(io.StringIO()) as log:
                synth = lv.sfx.net("kick impact")                          # not cached: a synthesised kick instead
        self.assertGreater(len(synth), 1000)
        self.assertIn("synthesised", log.getvalue())
        with mock.patch.object(lv, "find_sounds", offline), contextlib.redirect_stdout(io.StringIO()):
            self.assertGreater(len(lv.sfx.net("zombie growl", fallback="groan")), 1000)


class TestHowToPlay(unittest.TestCase):
    def test_the_hints_name_the_commands_for_termux(self):
        with mock.patch.dict(os.environ, {"TERMUX_VERSION": "0.118"}):
            text = lv.play_hints("/data/data/com.termux/files/home/ws/videos/fight.mp4")
        for needed in ("termux-open", "termux-setup-storage", "storage/movies", "/play", "VLC"):
            self.assertIn(needed, text)

    @unittest.skipUnless(POSIX, "POSIX launchers only")
    def test_open_video_starts_the_launcher_and_can_copy_to_the_movies_folder(self):
        tmp = Path(tempfile.mkdtemp(prefix="play_"))
        video = tmp / "fight.mp4"
        video.write_bytes(b"x" * 100)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        marker = tmp / "opened.txt"
        launcher = bin_dir / "termux-open"
        launcher.write_text("#!/bin/sh\necho \"$1\" > %s\n" % marker)
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        movies = tmp / "Movies"
        movies.mkdir()
        with mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}), mock.patch.object(lv, "_movies_dir", return_value=str(movies)):
            res = lv.open_video(str(video), gallery=True)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["via"], "termux-open")
        self.assertTrue((movies / "Lumo" / "fight.mp4").is_file())
        self.assertIn("Lumo", marker.read_text())                              # it opens the copy that the Gallery can see
        missing = lv.open_video(str(tmp / "nope.mp4"))
        self.assertFalse(missing["ok"])
        self.assertIn("no such file", missing["message"])
        shutil.rmtree(tmp)

    def test_the_play_command_is_in_help_and_completion(self):
        from lumo.commands import HELP, SLASH
        self.assertIn("/play", SLASH)
        self.assertIn("/play [video]", HELP)

    @unittest.skipUnless(POSIX, "POSIX launchers only")
    def test_play_opens_the_newest_video(self):
        from lumo.commands import cmd_play
        ws = Path(tempfile.mkdtemp(prefix="play_ws_"))
        (ws / "videos").mkdir()
        old, new = ws / "videos" / "old.mp4", ws / "videos" / "new.mp4"
        old.write_bytes(b"x" * 50)
        new.write_bytes(b"y" * 50)
        os.utime(str(old), (1000, 1000))
        bin_dir = ws / "bin"
        bin_dir.mkdir()
        marker = ws / "opened.txt"
        launcher = bin_dir / "termux-open"
        launcher.write_text("#!/bin/sh\necho \"$1\" > %s\n" % marker)
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        ctx = Ctx({"model": "x/y"}, ws)
        with mock.patch.dict(os.environ, {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}), contextlib.redirect_stdout(io.StringIO()) as log:
            cmd_play(ctx, "")
        self.assertIn("new.mp4", marker.read_text())
        self.assertIn("opened in the player", log.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as log2:
            cmd_play(Ctx({"model": "x/y"}, Path(tempfile.mkdtemp())), "")
        self.assertIn("no video found", log2.getvalue())
        shutil.rmtree(ws)

    @unittest.skipUnless(HAVE_PIL and HAVE_FFMPEG, "Pillow and ffmpeg needed")
    def test_the_render_result_tells_the_user_how_to_play_it(self):
        ws = Path(tempfile.mkdtemp(prefix="vid_play_"))
        (ws / "videos").mkdir()
        (ws / "videos" / "demo.py").write_text("from lumovideo import *\nv = Video(1280, 720)\nv.scene(1.0, lambda c, t: c.background('#123456', '#654321'))\nv.render()\n")
        ctx = Ctx({"model": "x/y"}, ws)
        ctx.auto = True
        res = exec_tool(ctx, "render_video", {"script": "videos/demo.py", "quality": "draft"})
        self.assertTrue(res.startswith("OK: video saved to videos/demo.mp4"), res)
        self.assertIn("HOW TO PLAY", res)
        self.assertIn("termux-open videos/demo.mp4", res)
        self.assertIn("/play", res)
        self.assertNotIn("How to play:", res)                                  # the script's own hint is not repeated in the tool output
        shutil.rmtree(ws)


class TestFindSoundTool(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="find_snd_"))
        self.ctx = Ctx({"model": "x/y"}, self.ws)
        self.ctx.auto = True
        video_tools._VK.clear()

    def tearDown(self):
        video_tools._VK.clear()
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_the_tool_is_registered_labelled_and_comes_back_with_video_requests(self):
        from lumo import safelimit
        from lumo.toolrun import TOOL_META, tool_label
        from lumo.tools.registry import TOOLS
        self.assertIn("find_sound", TOOLS)
        self.assertIn("find_sound", TOOL_META)
        self.assertIn("punch", tool_label("find_sound", {"query": "punch impact"}, 80))
        rx = [r for names, r in safelimit.HIDDEN_UNLESS_ASKED if "find_sound" in names][0]
        for text in ("make a stickman fight video", "tambah efek suara", "find a sound effect for the video"):
            self.assertTrue(re.search(rx, text, re.I), text)
        self.assertFalse(re.search(rx, "fix the login bug", re.I))

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
    def test_it_saves_the_sounds_and_explains_how_to_use_and_credit_them(self):
        vk = video_tools.load_videokit()
        items = [{"title": "Punch %d" % i, "creator": "Ann", "license": "CC0", "license_code": "cc0", "duration": 1.0 + i, "url": "https://cdn.example.org/p%d.wav" % i,
                  "page": "https://example.org/%d" % i} for i in range(2)]

        def fake_fetch(item, name=None, max_seconds=6.0, folder=None):
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "punch-%s.wav" % item["title"][-1])
            with open(path, "wb") as fh:
                fh.write(wav_bytes())
            return path
        with mock.patch.object(vk, "find_sounds", lambda q, limit=6, max_seconds=6.0, **k: items), mock.patch.object(vk, "fetch_sound", fake_fetch):
            res = exec_tool(self.ctx, "find_sound", {"query": "punch impact", "count": 2})
        self.assertTrue(res.startswith("OK: saved 2 sound(s) for 'punch impact' in sounds/"), res)
        self.assertIn("sounds/punch-0.wav", res)
        self.assertIn("sfx.file(", res)
        self.assertIn("CREDITS.txt", res)
        self.assertIn("CC-BY", res)

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg needed")
    def test_no_internet_gives_a_clear_fallback_not_a_crash(self):
        vk = video_tools.load_videokit()

        def offline(*a, **k):
            raise vk.SoundError("no internet connection or the server is down")
        with mock.patch.object(vk, "find_sounds", offline):
            res = exec_tool(self.ctx, "find_sound", {"query": "zombie growl"})
        self.assertTrue(res.startswith("ERROR: no sound found"), res)
        self.assertIn("sfx.get('zombie_growl')", res)
        self.assertIn("url", res)
        self.assertTrue(exec_tool(self.ctx, "find_sound", {"query": ""}).startswith("ERROR"))


@unittest.skipUnless(HAVE_PIL, "Pillow missing")
class TestSmootherFights(unittest.TestCase):
    @staticmethod
    def fight(duration=14, seed=3, **kw):
        a, b = lv.Stick("Aro", "#4aa3ff", headband="#ffffff", gloves="#ff4d4d"), lv.Stick("Bima", "#ff5a5a", headband="#ffd166", gloves="#222222")
        f = lv.Fight(a, b, stage="dojo", seed=seed, **kw)
        f.auto(duration=duration, winner="a", seed=seed)
        return f

    def test_the_fight_fits_the_requested_length_and_is_full_of_action(self):
        for dur in (10, 14, 20):
            f = self.fight(dur)
            s = f.summary()
            self.assertTrue(dur + 1.5 < f.duration < dur + 6.0, (dur, f.duration))
            self.assertGreaterEqual(sum(s["hits"]), dur * 0.5, (dur, s))
            self.assertEqual((s["ko"], s["hp"][1]), ("Bima", 0.0))
            self.assertGreater(s["hp"][0], 0)

    def test_pace_changes_how_much_happens(self):
        slow = lv.Fight(lv.Stick("A", "#4aa3ff"), lv.Stick("B", "#ff5a5a"), seed=2)
        slow.auto(duration=16, seed=2, pace=0.6)
        fast = lv.Fight(lv.Stick("A", "#4aa3ff"), lv.Stick("B", "#ff5a5a"), seed=2)
        fast.auto(duration=16, seed=2, pace=1.8)
        self.assertGreaterEqual(sum(fast.summary()["hits"]), sum(slow.summary()["hits"]))

    def test_the_same_seed_gives_the_same_fight_with_the_new_director(self):
        a, b = self.fight(12, 5), self.fight(12, 5)
        self.assertEqual(a.frame_bytes if hasattr(a, "frame_bytes") else a.summary(), b.frame_bytes if hasattr(b, "frame_bytes") else b.summary())
        v1, v2 = lv.Video(1280, 720, quality="draft"), lv.Video(1280, 720, quality="draft")
        v1.add(a)
        v2.add(b)
        self.assertEqual(v1.frame_at(6.0, "draft").tobytes(), v2.frame_at(6.0, "draft").tobytes())

    def test_poses_are_blended_so_nothing_snaps(self):
        f = self.fight(14)
        f.summary()
        keys = [k for k in f._tracks[0][0] if k not in ("y", "lift", "hx")]
        for i in (0, 1):
            tr, lb = f._tracks[i], f._labels[i]
            for n in range(len(tr) - 1):
                if lb[n] in ("idle", "walk", "run") or lb[n + 1] in ("idle", "walk", "run"):
                    jump = max(abs(tr[n][k] - tr[n + 1][k]) for k in keys)
                    self.assertLess(jump, 14.0, (i, n / 120.0, lb[n], lb[n + 1]))        # one 1/120 s step between locomotion and anything else
        self.assertEqual(len(f._tracks[0]), len(f._labels[0]))

    def test_every_few_frames_of_a_whole_fight_draw_at_sixty_fps(self):
        for seed, dur in ((3, 14), (7, 12), (11, 18)):
            f = self.fight(dur, seed)
            v = lv.Video(1280, 720, quality="draft")
            v.add(f)
            total = int(v.duration * 60)
            for n in range(0, total, 3):
                v.frame_at(n / 60.0, "draft", 60)                    # a crash on any frame (for example an action ending between two samples) fails here
            v.frame_at(v.duration - 0.001, "draft", 60)

    def test_the_new_moves_and_dodges_play_without_errors(self):
        a, b = lv.Stick("A", "#4aa3ff"), lv.Stick("B", "#ff5a5a")
        f = lv.Fight(a, b, seed=4)
        f.gap(0.3, 88, 0.6)
        t = 1.2
        for mv in ("hook", "elbow", "knee", "axe_kick"):
            f.attack("a", mv, at=t)
            t += 1.5
        f.dodge("b", at=t, style="flip")
        f.attack("a", "superman_punch", at=t, hit=False)
        f.step("a", at=t + 1.2, by=-50)
        f.attack("a", "round_kick", at=t + 2.2, finisher=True)
        f.victory("a", at=t + 4.0)
        s = f.summary()
        self.assertGreaterEqual(sum(s["hits"]), 5)
        v = lv.Video(1280, 720, quality="draft")
        v.add(f)
        for T in (1.4, 3.0, t + 0.3, v.duration - 0.2):
            img = v.frame_at(T, "draft")
            self.assertGreater(lv.ImageStat.Stat(img.convert("L")).stddev[0], 8)
        for name in ("hook", "elbow", "knee", "axe_kick", "superman_punch", "knockback", "backflip"):
            self.assertIn(name, lv.MOVES)

    def test_voices_surfaces_and_recorded_sounds_change_the_sound_track(self):
        plain = self.fight(12)
        voiced = self.fight(12, voices=True)
        plain.summary()
        voiced.summary()
        self.assertGreater(len(voiced._sounds), len(plain._sounds))
        marker = lv.sfx.punch(variant=9)
        own = self.fight(12).use_sounds(punch=[marker])
        own.summary()
        self.assertTrue(any(s[1] is marker for s in own._sounds))
        gravel = self.fight(12, surface="gravel")
        gravel.summary()
        self.assertGreater(len(gravel._sounds), 10)

    def test_a_hit_makes_the_struck_fighter_flash_and_the_stage_is_never_still(self):
        f = self.fight(12)
        f.summary()
        te = f._flashes[1][0] if f._flashes[1] else f._flashes[0][0]
        v = lv.Video(1280, 720, quality="draft")
        v.add(f)
        T = f._warp.vid(te) + 0.03
        img = v.frame_at(T, "draft")
        self.assertGreater(lv.ImageStat.Stat(img.convert("L")).mean[0], 20)
        st = lv.Stage("forest", 1280, 720, 560, 3)
        c1, c2 = lv.Canvas(1280, 720, 320, 180, ss=1), lv.Canvas(1280, 720, 320, 180, ss=1)
        st.draw(c1, 1.0)
        st.draw(c2, 3.3)
        self.assertNotEqual(c1.to_image().tobytes(), c2.to_image().tobytes())


class TestDailyFreeModelLimit(unittest.TestCase):
    def test_the_message_says_whose_limit_it_is_and_when_it_resets_on_the_phone_clock(self):
        from lumo.client import daily_quota_message, utc_reset_text
        self.assertRegex(utc_reset_text(), r"^00:00 UTC = \d\d:\d\d your time, in \d+h \d\dm$")
        msg = daily_quota_message()
        for needed in ("50 requests a day", "1000", "not to Lumo Code", "/provider", "/resume", "openrouter.ai/credits", "your time"):
            self.assertIn(needed, msg)

    def _ctx(self, **cfg):
        base = {"model": "x/y:free", "provider": "openrouter", "keys": {"groq": "gsk_abc123"}, "models_by_provider": {"groq": "llama-3.3-70b-versatile"}, "rotate": True}
        base.update(cfg)
        return Ctx(base, Path(tempfile.mkdtemp(prefix="failover_")))

    def test_lumo_continues_on_another_configured_provider_when_the_quota_is_gone(self):
        from lumo import agent, providers
        ctx = self._ctx()
        with contextlib.redirect_stdout(io.StringIO()) as log:
            self.assertTrue(agent.failover_provider(ctx))
            self.assertFalse(agent.failover_provider(ctx))                      # only once per turn: no ping-pong
        self.assertEqual(providers.active(ctx.cfg)["id"], "groq")
        self.assertEqual(ctx.cfg["model"], "llama-3.3-70b-versatile")
        self.assertIn("Continuing on Groq", log.getvalue())
        self.assertIn("/provider openrouter", log.getvalue())

    def test_it_never_switches_to_a_provider_that_was_not_set_up_or_when_fallbacks_are_off(self):
        from lumo import agent, providers
        for ctx in (self._ctx(keys={}), self._ctx(models_by_provider={}), self._ctx(rotate=False)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(agent.failover_provider(ctx))
            self.assertEqual(providers.active(ctx.cfg)["id"], "openrouter")


class TestDocsAndSkill(unittest.TestCase):
    def test_the_skill_and_docs_describe_the_new_features(self):
        skill = (ROOT / "skills" / "video-skill.md").read_text()
        for needed in ("60 fps", "find_sound", "/play", "sfx.names()", "HOW TO PLAY", "termux-setup-storage", "more than numbers", "pace"):
            self.assertIn(needed.lower(), skill.lower(), needed)
        self.assertIn("Make a video only when the user asked for one", skill)
        self.assertNotIn("Do not download media", skill)
        readme = (ROOT / "README.md").read_text()
        for needed in ("/play", "find_sound", "60 fps", "CREDITS.txt"):
            self.assertIn(needed, readme)
        self.assertIn("## [1.9.0]", (ROOT / "CHANGELOG.md").read_text())
        from lumo.config import VERSION
        self.assertEqual(VERSION, "1.10.0")
        self.assertEqual(lv.__version__, "1.2.0")


if __name__ == "__main__":
    unittest.main()
