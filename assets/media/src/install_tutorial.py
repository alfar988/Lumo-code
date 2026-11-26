#!/usr/bin/env python3
"""Source of assets/media/install-tutorial.mp4, made from templates/video-tutorial.py: three commands to install it.

Render from the Lumo folder:  LUMO_VIDEO_OUT=assets/media/install-tutorial.mp4 python assets/media/src/install_tutorial.py
Check without ffmpeg:         python assets/media/src/install_tutorial.py --selftest
Needs:                        Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "videokit"))      # the bundled lumovideo library
from lumovideo import PALETTES, Typewriter, Video, ease, sfx   # noqa: E402

TITLE = "Install Lumo Code"
SUBTITLE = "Three commands in Termux"
STEPS = [                                        # (heading, one short line, what is typed in the window)
    ("Install", "Python and git, once.", "pkg update && pkg install python git"),
    ("Download", "Get the project from GitHub.", "git clone https://github.com/alfar988/Lumo-code.git"),
    ("Run", "Start it, then paste your OpenRouter key.", "cd Lumo-code && python run.py"),
]
VERTICAL = False
PALETTE = PALETTES["forest"]
BG_TOP, BG_BOTTOM = "#0f1d17", "#1f3b2e"


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h)
    cx, cy = w / 2.0, h / 2.0
    n = len(STEPS)

    def backdrop(c, accent):
        c.background(BG_TOP, BG_BOTTOM)
        c.glow(cx + 290 * math.sin(c.T * 1.1), cy * 0.7 + 100 * math.cos(c.T * 0.9), 440, accent, 0.26)      # the light drifts, so the picture is never frozen
        c.glow(cx - 330 * math.sin(c.T * 0.9 + 1.0), cy * 1.25 + 60 * math.sin(c.T * 1.6), 320, PALETTE[2], 0.18)
        c.vignette(0.35)

    def title(c, t):
        backdrop(c, PALETTE[0])
        c.text(TITLE, cx, cy - 30, 84 if not VERTICAL else 66, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.5, "out_back"), max_w=w * 0.88)
        c.text(SUBTITLE, cx, cy + 80, 40, "#d9efe3", alpha=ease((t - 0.5) / 0.5, "out_quad"), max_w=w * 0.88)
    v.scene(2.8, title, name="title", fade_in=0.3)

    def step(i, heading, line, command):
        accent = PALETTE[(i + 1) % len(PALETTE)]
        tw = Typewriter("$ " + command, start=1.0, cps=22)
        bx, by, bw, bh = (w * 0.07, cy + 20, w * 0.86, 190) if VERTICAL else (w * 0.08, cy + 20, w * 0.84, 200)

        def draw(c, t):
            backdrop(c, accent)
            p = ease(t / 0.45, "out_back")
            c.circle(w * 0.12, cy - 190 if not VERTICAL else cy - 300, 52 * p, fill=accent)
            c.text(str(i + 1), w * 0.12, cy - 190 if not VERTICAL else cy - 300, 56 * p, "#0f1d17")
            c.text(heading, w * 0.2, cy - 190 if not VERTICAL else cy - 300, 70 if not VERTICAL else 60, "#ffffff", anchor="la", outline="#000000", outline_w=5,
                   alpha=ease((t - 0.1) / 0.4, "out_quad"))
            c.text(line, w * 0.12, cy - 90 if not VERTICAL else cy - 200, 38, "#d9efe3", anchor="la", alpha=ease((t - 0.4) / 0.5, "out_quad"), max_w=w * 0.78)
            c.rect(bx, by, bw, bh, fill="#0a120e", radius=18, anchor="tl")                      # the window
            for k, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
                c.circle(bx + 28 + 30 * k, by + 28, 9, fill=col)
            tw.draw(c, t, bx + 30, by + 80, 30, "#9ff0b6", anchor="la", cursor=True, max_w=bw - 60)
            done = (i + ease(t / 4.2, "linear")) / n                                              # progress bar
            c.rect(w * 0.08, h - 70, w * 0.84, 12, fill="#2c4a3b", radius=6, anchor="tl")
            c.rect(w * 0.08, h - 70, w * 0.84 * done, 12, fill=accent, radius=6, anchor="tl")
        return draw

    for i, (heading, line, command) in enumerate(STEPS):
        sc = v.scene(4.6, step(i, heading, line, command), name="step%d" % (i + 1), transition="slide_left", trans_dur=0.4)
        v.sfx("whoosh", sc.start, vol=0.4)
        v.sfx("pop", sc.start + 0.2, vol=0.6)
        for k in range(8):
            v.sfx("click", sc.start + 1.0 + 0.22 * k, vol=0.25)                                       # keys while it types
        v.sfx("success", sc.start + 3.6, vol=0.5)

    def recap(c, t):
        backdrop(c, PALETTE[3])
        c.text("Recap", cx, 100, 64, "#ffffff", outline="#000000", outline_w=5)
        for i, (heading, _line, _cmd) in enumerate(STEPS):
            a = ease((t - 0.3 - 0.35 * i) / 0.4, "out_cubic")
            y = 230 + 110 * i
            c.circle(w * 0.2, y, 30 * a, fill=PALETTE[3])
            c.text("ok", w * 0.2, y, 26 * a, "#0f1d17")
            c.text(heading, w * 0.3, y, 52, "#ffffff", anchor="la", alpha=a, outline="#000000", outline_w=4)
    v.scene(max(3.0, 1.0 + 0.4 * n), recap, name="recap", transition="crossfade", trans_dur=0.4, fade_out=0.5)
    return v


def selftest():
    v = make_video()
    assert v.duration > 10 and len(v.scenes) == n_scenes(), v.duration
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the scene list only")
    else:
        rep = v.dry_run(8)
        assert rep["blank_frames"] == 0 and rep["motion"] > 0.1, rep
    print("all checks passed")
    return 0


def n_scenes():
    return len(STEPS) + 2


def main(argv):
    if "--selftest" in argv:
        return selftest()
    make_video().render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
