#!/usr/bin/env python3
"""__TITLE__: a data story video made with Python (lumovideo): title, animated bars, a growing line, one number that matters.

Run:        python datachart.py                  writes videos/datachart.mp4
            python datachart.py --selftest       checks the scenes and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       SERIES (label, value) with the user's real numbers, UNIT, KEY_VALUE, KEY_LABEL, VERTICAL. Never invent data: ask or say it is an example.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import BarChart, PALETTES, Video, ease, sfx   # noqa: E402

TITLE = "__TITLE__"
SUBTITLE = "__SUBTITLE__"
SERIES = [("Jan", 42), ("Feb", 58), ("Mar", 51), ("Apr", 73), ("May", 88)]       # (label, value), at least 3 entries
UNIT = ""                                                                          # shown after the numbers, for example " users"
KEY_VALUE = 88                                                                     # the one number the story ends on
KEY_LABEL = "the latest value"
VERTICAL = False
PALETTE = PALETTES["ocean"]
BG_TOP, BG_BOTTOM = "#08202b", "#12495c"
GRID = "#2f6275"


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h)
    cx, cy = w / 2.0, h / 2.0

    def backdrop(c, accent):
        c.background(BG_TOP, BG_BOTTOM)
        c.glow(cx + 290 * math.sin(c.T * 1.1), cy * 0.6 + 100 * math.cos(c.T * 0.9), 440, accent, 0.28)      # the light drifts, so the picture is never frozen
        c.glow(cx - 330 * math.sin(c.T * 0.9 + 1.0), cy * 1.2 + 60 * math.sin(c.T * 1.6), 320, PALETTE[2], 0.2)
        c.vignette(0.35)

    def title(c, t):
        backdrop(c, PALETTE[0])
        c.text(TITLE, cx, cy - 30, 84 if not VERTICAL else 68, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.5, "out_back"), max_w=w * 0.88)
        c.rect(cx, cy + 60, min(w * 0.5, 520) * ease((t - 0.3) / 0.7, "out_cubic"), 8, fill=PALETTE[1], anchor="c")
        c.text(SUBTITLE, cx, cy + 120, 38, "#d6edf5", alpha=ease((t - 0.6) / 0.5, "out_quad"), max_w=w * 0.88)
    v.scene(3.0, title, name="title", fade_in=0.3)
    v.sfx("riser", 0.2, vol=0.4)

    chart = BarChart([(lab, val) for lab, val in SERIES], colors=PALETTE, fmt="{:.0f}" + UNIT)

    def bars(c, t):
        backdrop(c, PALETTE[2])
        c.text("Compared", cx, 90, 60, "#ffffff", outline="#000000", outline_w=4)
        chart.draw(c, t, w * 0.08, 170, w * 0.84, h * 0.62, start=0.4, dur=1.6)
    sc = v.scene(5.5, bars, name="bars", transition="slide_left", trans_dur=0.5)
    v.sfx("whoosh", sc.start, vol=0.5)
    for i in range(len(SERIES)):
        v.sfx("pop", sc.start + 0.4 + 0.15 * i, vol=0.45)

    def line(c, t):
        backdrop(c, PALETTE[3])
        c.text("Over time", cx, 90, 60, "#ffffff", outline="#000000", outline_w=4)
        x0, y0, cw, ch = w * 0.1, 190, w * 0.8, h * 0.52
        top = max(val for _lab, val in SERIES) * 1.15
        n = len(SERIES)
        for k in range(5):
            gy = y0 + ch * k / 4
            c.line(x0, gy, x0 + cw, gy, GRID, 2)
        pts = [(x0 + cw * i / (n - 1), y0 + ch * (1 - val / top)) for i, (_lab, val) in enumerate(SERIES)]
        prog = ease((t - 0.3) / 2.4, "in_out_cubic") * (n - 1)
        i = int(prog)
        shown = pts[:i + 1]
        if i < n - 1:
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            f = prog - i
            shown.append((ax + (bx - ax) * f, ay + (by - ay) * f))
        if len(shown) > 1:
            c.polyline(shown, PALETTE[0], 8)
        for j, (px, py) in enumerate(pts):
            c.text(SERIES[j][0], px, y0 + ch + 40, 30, "#cfe6ee")
            if j <= i:
                c.circle(px, py, 13, fill="#ffffff", outline=PALETTE[0], width=5)
                c.text("%s%s" % (SERIES[j][1], UNIT), px, py - 38, 30, "#ffffff", outline="#000000", outline_w=3)
    sc = v.scene(5.5, line, name="line", transition="slide_left", trans_dur=0.5)
    v.sfx("whoosh", sc.start, vol=0.5)

    def key(c, t):
        backdrop(c, PALETTE[1])
        n = int(KEY_VALUE * ease((t - 0.3) / 1.6, "out_cubic"))
        c.text("%d%s" % (n, UNIT), cx, cy - 40, 190 if not VERTICAL else 150, "#ffffff", outline="#000000", outline_w=8, scale=ease(t / 0.4, "out_back"), max_w=w * 0.94)
        c.text(KEY_LABEL, cx, cy + 110, 44, "#d6edf5", alpha=ease((t - 1.2) / 0.5, "out_quad"), max_w=w * 0.86)
    sc = v.scene(4.0, key, name="key", transition="crossfade", trans_dur=0.5, fade_out=0.5)
    v.sfx("success", sc.start + 1.8, vol=0.6)
    return v


def selftest():
    v = make_video()
    assert v.duration > 12 and len(v.scenes) == 4 and len(SERIES) >= 3, v.duration
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
