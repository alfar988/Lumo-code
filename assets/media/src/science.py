#!/usr/bin/env python3
"""Source of assets/media/science.mp4, made from templates/video-science.py: a science animation.

Render from the Lumo folder:  LUMO_VIDEO_OUT=assets/media/science.mp4 python assets/media/src/science.py
Check without ffmpeg:         python assets/media/src/science.py --selftest
Needs:                        Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "videokit"))      # the bundled lumovideo library
from lumovideo import PALETTES, Video, ease, mix, sfx   # noqa: E402

TITLE = "Science in motion"
SUBTITLE = "Sorting, orbits and waves"
ARRAY = [7, 3, 9, 2, 6, 1, 8, 4, 5]
STEPS_PER_SECOND = 7.0
ORBITS = [("Mercury", 150, 2.4, "#c9b79c", 10), ("Earth", 240, 1.3, "#4aa3ff", 15), ("Mars", 330, 0.8, "#ff7a4a", 12)]     # name, radius, speed, colour, size
VERTICAL = False
PALETTE = PALETTES["neon"]
BG_TOP, BG_BOTTOM = "#0b1026", "#1a2356"


def sort_steps(values):
    """Every comparison of a bubble sort: (list after the step, index compared, swapped?, swaps so far)."""
    a, steps, swaps = list(values), [], 0
    for end in range(len(a) - 1, 0, -1):
        for j in range(end):
            swapped = a[j] > a[j + 1]
            if swapped:
                a[j], a[j + 1] = a[j + 1], a[j]
                swaps += 1
            steps.append((list(a), j, swapped, swaps))
    steps.append((list(a), -1, False, swaps))
    return steps


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h)
    cx, cy = w / 2.0, h / 2.0
    steps = sort_steps(ARRAY)
    sort_len = len(steps) / STEPS_PER_SECOND + 1.5

    def backdrop(c):
        c.background(BG_TOP, BG_BOTTOM)
        c.vignette(0.35)

    def title(c, t):
        backdrop(c)
        c.glow(cx, cy, 380, PALETTE[0], 0.35)
        c.text(TITLE, cx, cy - 30, 84 if not VERTICAL else 66, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.5, "out_back"), max_w=w * 0.88)
        c.text(SUBTITLE, cx, cy + 80, 40, "#cfd8ff", alpha=ease((t - 0.5) / 0.5, "out_quad"), max_w=w * 0.88)
    v.scene(2.8, title, name="title", fade_in=0.3)

    def sorting(c, t):
        backdrop(c)
        c.text("Bubble sort", cx, 80, 60, "#ffffff", outline="#000000", outline_w=4)
        arr, j, swapped, swaps = steps[min(int(t * STEPS_PER_SECOND), len(steps) - 1)]
        n, top = len(arr), max(ARRAY)
        bw, gap = w * 0.84 / n * 0.78, w * 0.84 / n * 0.22
        x0, base = w * 0.08, h * 0.80
        unit = (h * 0.5) / top
        done = int(t * STEPS_PER_SECOND) >= len(steps) - 1
        for i, val in enumerate(arr):
            col = PALETTE[1] if done else (PALETTE[3] if swapped and i in (j, j + 1) else (PALETTE[0] if i in (j, j + 1) else "#5b6bd6"))
            x = x0 + i * (bw + gap)
            c.rect(x, base, bw, val * unit, fill=col, radius=8, anchor="bl")
            c.text(str(val), x + bw / 2, base + 34, 34, "#ffffff")
        c.text("swaps: %d" % swaps, cx, h * 0.92, 40, "#cfd8ff")
    sc = v.scene(sort_len, sorting, name="sorting", transition="slide_left", trans_dur=0.5)
    v.sfx("whoosh", sc.start, vol=0.4)
    for k in range(0, len(steps), 3):
        v.sfx("click", sc.start + k / STEPS_PER_SECOND, vol=0.2)

    def orbit(c, t):
        backdrop(c)
        c.text("Orbits", cx, 80, 60, "#ffffff", outline="#000000", outline_w=4)
        oy = cy + 30
        c.glow(cx, oy, 120, "#ffd166", 1.0)
        c.circle(cx, oy, 36, fill="#ffd166")
        scale = min(w, h * 1.4) / 760
        for name, r, speed, col, size in ORBITS:
            c.circle(cx, oy, r * scale, outline="#33407f", width=2)
            for k in range(14, 0, -1):                                           # a fading trail, still a function of t
                a = (t - k * 0.04) * speed
                c.circle(cx + math.cos(a) * r * scale, oy + math.sin(a) * r * scale * 0.55, size * scale * (1 - k / 18.0) * 0.8, fill=mix(col, BG_TOP, k / 15.0))
            a = t * speed
            px, py = cx + math.cos(a) * r * scale, oy + math.sin(a) * r * scale * 0.55
            c.circle(px, py, size * scale, fill=col)
            c.text(name, px, py - size * scale - 22, 28, "#ffffff", outline="#000000", outline_w=3)
    sc = v.scene(6.0, orbit, name="orbit", transition="slide_left", trans_dur=0.5)
    v.sfx("whoosh", sc.start, vol=0.4)

    def waves(c, t):
        backdrop(c)
        c.text("Two waves add up", cx, 80, 56, "#ffffff", outline="#000000", outline_w=4)
        x0, width = w * 0.08, w * 0.84
        rows = [("wave A", cy - 200, PALETTE[0], lambda x: math.sin(x * 6 - t * 3), 58),
                ("wave B", cy, PALETTE[2], lambda x: 0.6 * math.sin(x * 14 - t * 5), 58),
                ("A + B", cy + 220, PALETTE[1], lambda x: math.sin(x * 6 - t * 3) + 0.6 * math.sin(x * 14 - t * 5), 36)]     # the sum is drawn smaller so it fits its row
        grow = ease(t / 1.2, "out_cubic")
        for label, y, col, fn, amp in rows:
            pts = [(x0 + width * i / 90, y - fn(i / 90 * math.pi) * amp * grow) for i in range(91)]
            c.line(x0, y, x0 + width, y, "#33407f", 2)
            c.polyline(pts, col, 6)
            c.text(label, x0, y - 90, 32, col, anchor="la", outline="#000000", outline_w=3)
    sc = v.scene(5.5, waves, name="waves", transition="slide_left", trans_dur=0.5, fade_out=0.5)
    v.sfx("whoosh", sc.start, vol=0.4)
    return v


def selftest():
    v = make_video()
    assert v.duration > 12 and len(v.scenes) == 4, v.duration
    last = sort_steps(ARRAY)[-1][0]
    assert last == sorted(ARRAY), last
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the scene list only")
    else:
        rep = v.dry_run(10)
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
