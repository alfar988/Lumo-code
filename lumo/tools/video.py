"""Video tools: render a Python animation script into a playable MP4 in the workspace, and inspect a video file."""

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

from lumo.config import APP_DIR
from lumo.security import ask_outside, fs_path, inside, outside_paths
from lumo.state import ask, secret_values, ToolError
from lumo.tools.registry import B, I, S, tool
from lumo.tools.shell import run_status_line, shell_run
from lumo.ui import clip, tw
from lumo.util import cap, denied, human_size, rel, to_int

VIDEOKIT = APP_DIR / "videokit"          # the animation library that scripts import: from lumovideo import *
LIB = "lumovideo.py"
REPORT_RX = re.compile(r"^LUMO_VIDEO_REPORT (\{.*\})\s*$", re.M)
VERSION_RX = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", re.M)
INSTALL_HINT = "Termux: pkg install ffmpeg python-pillow -y   |   Debian/Ubuntu: sudo apt install ffmpeg python3-pil   |   pip install pillow"


LITERAL_PATH_RX = re.compile(r"""["'](~/[^"'\n]*|/[A-Za-z0-9_.~$][^"'\n]*|\$HOME[^"'\n]*)["']""")


def script_outside_paths(ctx, code):
    """Absolute paths written as string literals in a script that point outside the workspace. A division sign (a / b) is not a path."""
    lits = [m.group(1).replace(" ", "") for m in LITERAL_PATH_RX.finditer(code)]
    return outside_paths(ctx, " ".join(lits)) if lits else []


def lib_version(path):
    try:
        m = VERSION_RX.search(path.read_text(encoding="utf-8", errors="replace")[:4000])
    except OSError:
        return None
    return m.group(1) if m else None


def ensure_library(script_dir):
    """Put lumovideo.py next to the script so the whole folder runs on its own (python script.py). Returns True when it was copied."""
    src = VIDEOKIT / LIB
    if not src.exists():
        raise ToolError("the animation library is missing from this install (%s). Reinstall or update Lumo Code." % src)
    dst = script_dir / LIB
    if dst.exists() and lib_version(dst) == lib_version(src):
        return False
    script_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(src), str(dst))
    return True


_VK = {}


def load_videokit():
    """The bundled lumovideo module (players, sound search), loaded once. It is a standalone file, so Lumo uses its helpers without copying it anywhere."""
    if "m" not in _VK:
        src = VIDEOKIT / LIB
        if not src.exists():
            raise ToolError("the animation library is missing from this install (%s). Reinstall or update Lumo Code." % src)
        spec = importlib.util.spec_from_file_location("lumovideo_kit", str(src))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["lumovideo_kit"] = mod
        spec.loader.exec_module(mod)
        _VK["m"] = mod
    return _VK["m"]


def how_to_play(rp):
    """One short paragraph the model passes on to the user."""
    q = shlex.quote(rp)
    return ("termux-open %s  |  in Lumo: /play  |  to see it in Gallery: run termux-setup-storage once (tap Allow), then cp %s ~/storage/movies/ "
            "and open Gallery, Files, VLC or MX Player" % (q, q))


def python_exe():
    return shutil.which("python3") or sys.executable


def missing_tools():
    """What the render needs and this device does not have yet (an empty list means ready)."""
    miss = []
    try:
        r = subprocess.run([python_exe(), "-c", "import PIL"], capture_output=True, timeout=30)
        if r.returncode != 0:
            miss.append("Pillow (Python imaging library)")
    except Exception:
        miss.append("Pillow (Python imaging library)")
    if not shutil.which("ffmpeg"):
        miss.append("ffmpeg")
    return miss


def clean_output(text):
    """Progress lines redraw themselves with carriage returns; keep only the last one so the log stays short."""
    lines = []
    for raw in text.splitlines():
        seg = raw.rsplit("\r", 1)[-1].rstrip()
        if seg.strip().startswith("rendering") and lines and lines[-1].strip().startswith("rendering"):
            lines[-1] = seg
        elif seg.strip():
            lines.append(seg)
    return "\n".join(lines)


def probe(path):
    """ffprobe summary of a media file: dict with duration, size, width, height, fps, vcodec, acodec."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                           capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout or "{}")
    except Exception:
        return None
    info = {"duration": float((data.get("format") or {}).get("duration") or 0), "size": int((data.get("format") or {}).get("size") or 0)}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and "vcodec" not in info:
            fr = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            try:
                a, b = fr.split("/")
                fps = float(a) / float(b) if float(b) else 0.0
            except ValueError:
                fps = 0.0
            info.update(vcodec=s.get("codec_name"), width=s.get("width"), height=s.get("height"), fps=round(fps, 2), pix_fmt=s.get("pix_fmt"))
            if not info["duration"]:
                info["duration"] = float(s.get("duration") or 0)
        elif s.get("codec_type") == "audio" and "acodec" not in info:
            info["acodec"] = s.get("codec_name")
    return info


def sample_frames(path, duration, count=40):
    """Brightness, contrast and motion of a video from small gray frames (needs ffmpeg only). Returns a dict or None."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    w, h = 48, 27
    rate = max(0.2, min(2.0, count / max(duration, 1.0)))
    try:
        r = subprocess.run([exe, "-v", "error", "-i", str(path), "-vf", "fps=%.3f,scale=%d:%d,format=gray" % (rate, w, h), "-frames:v", str(count),
                            "-f", "rawvideo", "-"], capture_output=True, timeout=180)
    except Exception:
        return None
    data, n = r.stdout, w * h
    frames = [data[i:i + n] for i in range(0, len(data) - n + 1, n)]
    if not frames:
        return None
    means, stds, diffs = [], [], []
    for k, f in enumerate(frames):
        m = sum(f) / float(n)
        means.append(m)
        stds.append((sum((v - m) ** 2 for v in f) / float(n)) ** 0.5)
        if k:
            diffs.append(sum(abs(a - b) for a, b in zip(f, frames[k - 1])) / float(n))
    return {"frames": len(frames), "brightness": round(sum(means) / len(means), 1), "blank": sum(1 for s in stds if s < 1.5),
            "motion": round(sum(diffs) / len(diffs), 2) if diffs else 0.0, "frozen": round(sum(1 for d in diffs if d < 0.05) / float(len(diffs)), 2) if diffs else 0.0}


def describe(info):
    bits = []
    if info.get("duration"):
        bits.append("%.1fs" % info["duration"])
    if info.get("width"):
        bits.append("%dx%d" % (info["width"], info["height"]))
    if info.get("fps"):
        bits.append("%g fps" % info["fps"])
    codecs = {"h264": "H.264", "aac": "AAC", "mpeg4": "MPEG-4", "gif": "GIF"}
    names = [codecs.get(info.get("vcodec"), info.get("vcodec") or "")]
    names.append(codecs.get(info.get("acodec"), info.get("acodec")) if info.get("acodec") else "no audio")
    bits.append(" + ".join(n for n in names if n))
    if info.get("size"):
        bits.append(human_size(info["size"]))
    return " · ".join(bits)


@tool("render_video", "Turn a Python animation script (written with the bundled lumovideo library) into a playable MP4 in the workspace, with sound, then check the result. "
      "Use only when the user asked for a video or animation. Load the video-skill first.",
      {"script": S("the .py script in the workspace, e.g. videos/fight.py"),
       "output": S("optional .mp4 path; default videos/<script name>.mp4"),
       "quality": S("draft (fast preview) | standard (default) | hd | fhd", enum=["draft", "standard", "hd", "fhd"]),
       "timeout": I("seconds, default 900, max 3600"),
       "open": B("open the finished video in the device player (only if the user wants to watch it now)")}, ["script"])
def t_render_video(a, ctx):
    sp = fs_path(ctx, a.get("script"), "render video")
    if not sp.is_file() or sp.suffix != ".py":
        raise ToolError("script must be an existing .py file in the workspace (write it first with write_file): %s" % a.get("script"))
    timeout = max(30, min(to_int(a.get("timeout"), 900), 3600))
    quality = str(a.get("quality") or "").strip().lower()
    if quality and quality not in ("draft", "standard", "hd", "fhd"):
        raise ToolError("quality must be draft, standard, hd or fhd")
    out_arg = str(a.get("output") or "").strip()
    outp = None
    if out_arg:
        outp = fs_path(ctx, out_arg, "write video", write=True)
        if outp.suffix.lower() not in (".mp4", ".gif"):
            raise ToolError("output must end in .mp4")
        if not inside(outp, ctx.ws) and not ctx.full_access:
            raise ToolError("the video must be saved inside the workspace")
    miss = missing_tools()
    if miss:
        return "ERROR: %s not installed yet, so no video can be made. Install with run_shell: %s. Then call render_video again." % (" and ".join(miss), INSTALL_HINT)
    code = sp.read_text(encoding="utf-8", errors="replace")[:200000]
    outs = [] if ctx.full_access else script_outside_paths(ctx, code)
    if outs:
        okk, _ = ask_outside(ctx, outs, "running a video script that references the locations above")
        if not okk:
            return denied("access outside the workspace is not allowed")
    else:
        target = "%s → %s" % (rel(ctx, sp), rel(ctx, outp) if outp else "videos/%s.mp4" % sp.stem)
        okk, why = ask(ctx, "Video", clip(target, tw() - 12), ["Renders frames with Python and encodes them with ffmpeg%s." % (" (%s)" % quality if quality else "")])
        if not okk:
            return denied(why)
    copied = ensure_library(sp.parent)
    env = ["PYTHONDONTWRITEBYTECODE=1", "LUMO_VIDEO_REQUIRE_FFMPEG=1", "LUMO_VIDEO_TOOL=1", "LUMO_SOUNDS_DIR=%s" % shlex.quote(str(ctx.ws / "sounds")), "PYTHONPATH=%s%s" % (shlex.quote(str(VIDEOKIT)), os.pathsep + shlex.quote(os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else "")]
    if outp:
        outp.parent.mkdir(parents=True, exist_ok=True)
        env.append("LUMO_VIDEO_OUT=%s" % shlex.quote(str(outp)))
    if quality:
        env.append("LUMO_VIDEO_QUALITY=%s" % quality)
    cmd = "env %s %s %s" % (" ".join(env), shlex.quote(python_exe()), shlex.quote(str(sp)))
    res = shell_run(cmd, ctx.ws, timeout, live=True)
    run_status_line(res, timeout)
    text = cap(clean_output(res["text"]), 6000)
    if res["timeout"]:
        return "ERROR: rendering took longer than %ds and was stopped. Make the video shorter, lower the quality (quality=draft or standard), or raise timeout.\n%s" % (timeout, text[-1500:])
    m = REPORT_RX.findall(res["text"])
    if res["code"] != 0 or not m:
        tail = "\n".join(text.splitlines()[-25:])
        hint = ""
        if re.search(r"unknown |has no attribute|NameError|ImportError|TypeError|AttributeError", tail):
            hint = ("\nA name or argument is wrong. Do not guess: call video_api with the right topic (moves, poses, actor, show, fight, scene3d, canvas, video, sound, stages, easing, components, recipes) "
                    "and use exactly the names it lists. If what you need does not exist, say so and build it yourself with the library's building blocks (define_pose, define_move, Canvas drawing).")
        return "ERROR: the script did not produce a video (exit %s). Read the last lines, fix the script and render again:\n%s%s" % (res["code"], tail, hint)
    rep = json.loads(m[-1])
    final = rep.get("file")
    if not final or not os.path.exists(final):
        return "ERROR: the script finished but %s does not exist. Call v.render() at the end of the script." % (final or "the output file")
    info = probe(final) or {}
    qa = rep.get("qa") or {}
    rp = rel(ctx, __import__("pathlib").Path(final)) if inside(final, ctx.ws) else final
    lines = ["OK: video saved to %s · %s · rendered in %ss" % (rp, describe(info) if info else "%ss, %sx%s" % (rep.get("duration"), rep.get("width"), rep.get("height")), rep.get("render_s"))]
    if rep.get("workers", 1) > 1 or (rep.get("blur") or 1) > 1:
        lines.append("render: %d CPU cores · motion blur x%d · %s fps" % (rep.get("workers", 1), rep.get("blur", 1), rep.get("fps")))
    lines.append("checks: %s · motion %s · brightness %s%s" % ("no blank frames" if not qa.get("blank_frames") else "%d blank frames" % qa["blank_frames"],
                                                               qa.get("motion"), qa.get("brightness"), " · sound included" if rep.get("audio") else " · no sound"))
    if rep.get("format") == "gif":
        lines.append("WARNING: ffmpeg was missing, so this is a GIF without sound. Install ffmpeg for an MP4.")
    for w in qa.get("warnings", []):
        lines.append("WARNING: " + w)
    if copied:
        lines.append("note: lumovideo.py was copied next to the script, so `python %s` also works on its own" % rel(ctx, sp))
    if a.get("open"):
        opener = shutil.which("termux-open") or shutil.which("xdg-open")
        if opener:
            try:
                subprocess.Popen([opener, final], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                lines.append("opened in the video player")
            except OSError:
                lines.append("could not open the player automatically")
        else:
            lines.append("no player launcher found; open the file from your gallery or file manager")
    lines.append("HOW TO PLAY (tell the user this, in their language, in your final answer): " + how_to_play(rp))
    return "\n".join(lines)


@tool("video_info", "Inspect a video or GIF: length, size, fps, codecs, sound, and whether frames are blank or frozen.", {"path": S("video file in the workspace")}, ["path"])
def t_video_info(a, ctx):
    p = fs_path(ctx, a.get("path"), "inspect video")
    if not p.is_file():
        raise ToolError("no such file: %s" % a.get("path"))
    if not shutil.which("ffprobe"):
        return "ERROR: ffprobe is not installed (it comes with ffmpeg). Install: %s" % INSTALL_HINT
    info = probe(p)
    if not info or not info.get("vcodec"):
        return "ERROR: not a readable video file: %s" % rel(ctx, p)
    qa = sample_frames(p, info.get("duration") or 1.0)
    lines = ["OK: %s · %s" % (rel(ctx, p), describe(info))]
    if qa:
        lines.append("checks over %d sampled frames: %s · motion %s · brightness %s · %d%% of the changes are frozen" %
                     (qa["frames"], "no blank frames" if not qa["blank"] else "%d blank frames" % qa["blank"], qa["motion"], qa["brightness"], int(qa["frozen"] * 100)))
        if qa["blank"]:
            lines.append("WARNING: some frames are a flat colour (nothing drawn)")
        if qa["frozen"] > 0.5 and (info.get("duration") or 0) > 2:
            lines.append("WARNING: more than half of the sampled frames do not change")
    return "\n".join(lines)


@tool("find_sound", "Search FREE sound effects on the internet (CC0 and CC-BY only) and save a few short WAV takes in sounds/ with a credit file. "
      "Use only for a video the user asked for, when real recordings would make it better; lumovideo already has over 80 synthesised effects that need no download. "
      "Then use sfx.file('sounds/<name>.wav') or fight.use_sounds(punch=[...]) in the script.",
      {"query": S("the sound in 1-4 English words, e.g. 'punch impact', 'zombie growl', 'rifle shot'"),
       "count": I("takes to save, default 3, max 6"),
       "max_seconds": I("cut each take to this length in seconds, default 4"),
       "url": S("optional: a direct https link to an audio file instead of searching")}, ["query"])
def t_find_sound(a, ctx):
    q = str(a.get("query") or "").strip()
    url = str(a.get("url") or "").strip()
    if not q and not url:
        raise ToolError("give a query such as 'punch impact'")
    count = max(1, min(to_int(a.get("count"), 3), 6))
    secs = max(1, min(to_int(a.get("max_seconds"), 4), 15))
    if not shutil.which("ffmpeg"):
        return "ERROR: ffmpeg is not installed, so downloaded sounds cannot be converted. Install: %s. The synthesised effects work without it: sfx.get('punch')." % INSTALL_HINT
    key = secret_values(ctx).get("FREESOUND_API_KEY", "")
    okk, why = ask(ctx, "Sound", clip(url or q, tw() - 12), ["Looks up free sound effects (Openverse%s) and saves up to %d short WAV files in sounds/." % (" and Freesound" if key else "", count)])
    if not okk:
        return denied(why)
    vk = load_videokit()
    folder = str(ctx.ws / "sounds")
    saved, notes = [], []
    old_key = os.environ.get("FREESOUND_API_KEY")
    if key:
        os.environ["FREESOUND_API_KEY"] = key
    try:
        items = [url] if url else vk.find_sounds(q, limit=count, max_seconds=secs)
        for it in items:
            try:
                path = vk.fetch_sound(it, name=q or None, max_seconds=secs, folder=folder)
                saved.append((path, it))
            except vk.SoundError as e:
                notes.append(str(e))
    except vk.SoundError as e:
        return ("ERROR: no sound found (%s). Fall back to the synthesised effects: sfx.get('%s'), or try other words (English works best), "
                "or give a direct https link to a .wav/.mp3 in the url argument." % (e, re.sub(r"[^a-z]+", "_", q.lower()).strip("_") or "hit"))
    finally:
        if key:
            if old_key is None:
                os.environ.pop("FREESOUND_API_KEY", None)
            else:
                os.environ["FREESOUND_API_KEY"] = old_key
    if not saved:
        return "ERROR: nothing could be downloaded (%s). Use the synthesised effects instead: sfx.names() lists them." % ("; ".join(notes[:2]) or "unknown error")
    lines = ["OK: saved %d sound(s) for '%s' in sounds/" % (len(saved), q or url)]
    for path, it in saved:
        meta = it if isinstance(it, dict) else {}
        lines.append("  %s%s" % (rel(ctx, __import__("pathlib").Path(path)), (" · %ss · \"%s\" by %s · %s" % (meta.get("duration"), clip(str(meta.get("title")), 30), meta.get("creator"), meta.get("license"))) if meta else ""))
    first = rel(ctx, __import__("pathlib").Path(saved[0][0]))
    lines.append("use it: buf = sfx.file(\"%s\"); v.sound(buf, at=1.2)   |   several takes in turn for a fight: fight.use_sounds(punch=[...paths...])" % first)
    lines.append("Credits are in sounds/CREDITS.txt. CC-BY sounds must be credited if the video is published: tell the user, and show the credit in the video if they plan to publish it.")
    return "\n".join(lines)


@tool("video_api", "Look up the REAL names in the video library (moves, poses, Actor, Show, Fight, Scene3D, Canvas, sound effects, stages, working recipes) "
      "instead of guessing or reading its source file. Call it with no topic for the list, then with the topic you need BEFORE writing or fixing a video script.",
      {"topic": S("overview | recipes | moves | poses | actor | show | fight | scene3d | canvas | video | sound | stages | easing | components (empty = list the topics)")}, [])
def t_video_api(a, ctx):
    vk = load_videokit()
    try:
        return vk.catalog(str(a.get("topic") or "").strip().lower() or None)
    except ValueError as e:
        return "ERROR: %s" % e
