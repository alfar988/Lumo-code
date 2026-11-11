#!/usr/bin/env python3
"""__TITLE__: a short explainer video made with Python (lumovideo): title card, key points, an optional bar chart, an outro.

Run:        python explainer.py                  writes videos/explainer.mp4 (854x480, 30 fps)
            python explainer.py --selftest       checks the scenes and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       TITLE, SUBTITLE, POINTS, DATA and the colours below. Each point becomes one scene. Keep scene() and the timing helpers.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import BarChart, PALETTES, Typewriter, Video, ease, sfx   # noqa: E402

TITLE = "__TITLE__"
SUBTITLE = "__SUBTITLE__"
POINTS = [                              # (heading, one short line)
    ("Point one", "Say the first idea in a single short line."),
    ("Point two", "Keep every line readable at phone size."),
    ("Point three", "End on the thing people should remember."),
]
DATA = [("Alpha", 82), ("Beta", 61), ("Gamma", 44)]     # a bar chart scene is added when DATA is not empty
VERTICAL = False                         # True makes a 720x1280 video for Reels, Shorts and stories
PALETTE = PALETTES["neon"]
BG_TOP, BG_BOTTOM = "#0e1330", "#26346b"


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h)
    cx, cy = w / 2.0, h / 2.0

    def backdrop(c, t, accent):
        c.background(BG_TOP, BG_BOTTOM)
        c.glow(cx, cy * 0.7, 420, accent, 0.35)
        c.vignette(0.4)

    def title(c, t):
        backdrop(c, t, PALETTE[0])
        c.text(TITLE, cx, cy - 30, 96 if not VERTICAL else 80, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.5, "out_back"), max_w=w * 0.86)
        c.rect(cx, cy + 70, min(w * 0.5, 520) * ease((t - 0.3) / 0.7, "out_cubic"), 8, fill=PALETTE[1], anchor="c")
        c.text(SUBTITLE, cx, cy + 130, 40, "#d8def5", alpha=ease((t - 0.6) / 0.5, "out_quad"), max_w=w * 0.86)
    v.scene(3.0, title, name="title", fade_in=0.3)
    v.sound(sfx.riser(1.0, 0.25), 0.0, 0.7)

    def point(i, heading, line):
        accent = PALETTE[(i + 1) % len(PALETTE)]
        tw = Typewriter(line, start=0.6, cps=26)

        def draw(c, t):
            backdrop(c, t, accent)
            p = ease(t / 0.45, "out_back")
            c.circle(cx - (w * 0.34 if not VERTICAL else 0), cy - (110 if not VERTICAL else 330), 56 * p, fill=accent)
            c.text(str(i + 1), cx - (w * 0.34 if not VERTICAL else 0), cy - (110 if not VERTICAL else 330), 60 * p, "#0b0f1a")
            c.text(heading, cx, cy - (110 if not VERTICAL else 170), 72 if not VERTICAL else 64, "#ffffff", outline="#000000", outline_w=5,
                   alpha=ease((t - 0.1) / 0.4, "out_quad"), max_w=w * 0.8)
            tw.draw(c, t, cx - w * 0.4, cy + 10, 44, "#e8ecf8", anchor="la", cursor=False, max_w=w * 0.8)
        return draw

    for i, (heading, line) in enumerate(POINTS):
        sc = v.scene(4.0, point(i, heading, line), name="point%d" % (i + 1), transition="crossfade", trans_dur=0.4)
        v.sound(sfx.whoosh(0.3, 0.5), sc.start, 0.6)
        v.sound(sfx.pop(), sc.start + 0.1, 0.7)

    if DATA:
        chart = BarChart(DATA, colors=PALETTE)

        def stats(c, t):
            backdrop(c, t, PALETTE[2])
            c.text("The numbers", cx, 90, 64, "#ffffff", outline="#000000", outline_w=4)
            chart.draw(c, t, w * 0.08, 170, w * 0.84, h * 0.6, start=0.4, dur=1.4)
        sc = v.scene(5.0, stats, name="chart", transition="slide_left", trans_dur=0.5)
        v.sound(sfx.whoosh(0.4, 0.5), sc.start, 0.6)

    def outro(c, t):
        backdrop(c, t, PALETTE[3])
        c.text(TITLE, cx, cy, 70, "#ffffff", outline="#000000", outline_w=5, alpha=ease(t / 0.5, "out_quad"), max_w=w * 0.86)
    v.scene(2.5, outro, name="outro", fade_out=0.5, transition="crossfade", trans_dur=0.4)
    return v


def selftest():
    v = make_video()
    assert v.duration > 8 and len(v.scenes) >= 2 + len(POINTS), v.duration
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the scene list only")
    else:
        rep = v.dry_run(8)
        assert rep["blank_frames"] == 0 and rep["motion"] > 0.1, rep
    print("all checks passed")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    make_video().render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
