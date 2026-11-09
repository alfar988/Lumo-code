"""Video tools: render a Python animation script into a playable MP4 in the workspace, and inspect a video file."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys

from lumo.config import APP_DIR
from lumo.security import ask_outside, fs_path, inside, outside_paths
from lumo.state import ask, ToolError
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
    env = ["PYTHONDONTWRITEBYTECODE=1", "LUMO_VIDEO_REQUIRE_FFMPEG=1", "PYTHONPATH=%s%s" % (shlex.quote(str(VIDEOKIT)), os.pathsep + shlex.quote(os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else "")]
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
        return "ERROR: the script did not produce a video (exit %s). Read the last lines, fix the script and render again:\n%s" % (res["code"], tail)
    rep = json.loads(m[-1])
    final = rep.get("file")
    if not final or not os.path.exists(final):
        return "ERROR: the script finished but %s does not exist. Call v.render() at the end of the script." % (final or "the output file")
    info = probe(final) or {}
    qa = rep.get("qa") or {}
    rp = rel(ctx, __import__("pathlib").Path(final)) if inside(final, ctx.ws) else final
    lines = ["OK: video saved to %s · %s · rendered in %ss" % (rp, describe(info) if info else "%ss, %sx%s" % (rep.get("duration"), rep.get("width"), rep.get("height")), rep.get("render_s"))]
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
    else:
        lines.append("play it: termux-open %s (Termux) or open the file from your gallery / file manager" % rp)
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
