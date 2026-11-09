#!/usr/bin/env python3
"""__TITLE__: a kinetic typography video made with Python (lumovideo): one punchy line at a time with pops, slides and sound.

Run:        python kinetic.py                    writes videos/kinetic.mp4 (854x480, 30 fps)
            python kinetic.py --selftest         checks the scenes and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       LINES (the words on screen), the palette and MUSIC. Each line is one scene of SECONDS_PER_LINE seconds.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import PALETTES, Video, ease, music, sfx             # noqa: E402

TITLE = "__TITLE__"
LINES = ["__LINE_1__", "__LINE_2__", "__LINE_3__", "__LINE_4__"]    # short lines read best: one to four words
SECONDS_PER_LINE = 1.1
PALETTE = PALETTES["sunset"]
MUSIC = None                              # None, or "8bit" | "fight" | "epic" | "chill"
VERTICAL = False                          # True makes a 720x1280 video for Reels, Shorts and stories


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h, fps=30)
    slides = ["slide_left", "slide_right", "slide_up", "zoom"]

    def line_scene(i, text):
        top, accent = PALETTE[(i + 3) % len(PALETTE)], PALETTE[i % len(PALETTE)]
        size = 190 if len(text) < 8 else 140 if len(text) < 14 else 100

        def draw(c, t):
            c.background("#0b0d1a", top)
            c.glow(w / 2.0, h / 2.0, 520, accent, 0.45)
            pop = ease(t / 0.28, "out_back")
            lines = c.wrap(text.upper(), size, w * 0.9)                          # break long lines so they fit the screen
            n = lines.count("\n") + 1
            sz = size * (1.0 if n == 1 else 0.82)
            c.text(lines, w / 2.0 + 6, h / 2.0 + 8, sz, "#000000", scale=pop, alpha=0.35)                  # soft shadow
            c.text(lines, w / 2.0, h / 2.0, sz, "#ffffff", outline="#000000", outline_w=8, scale=pop, rot=(-2.5 if i % 2 else 2.5) * (1 - ease(t / 0.4, "out_cubic")))
            c.rect(w / 2.0, h / 2.0 + sz * (0.62 * n + 0.28), w * 0.5 * ease((t - 0.15) / 0.5, "out_cubic"), 10, fill=accent, anchor="c")
        return draw

    for i, text in enumerate(LINES):
        sc = v.scene(SECONDS_PER_LINE, line_scene(i, text), name="line%d" % (i + 1), transition=slides[i % len(slides)] if i else "cut", trans_dur=0.25)
        v.sound(sfx.pop(), sc.start + 0.02, 0.8)
        v.sound(sfx.whoosh(0.2, 0.4), sc.start, 0.5)
    if MUSIC:
        bpm = {"8bit": 140, "fight": 128, "epic": 100, "chill": 90}[MUSIC]
        bars = int(v.duration / (4 * 60.0 / bpm)) + 1
        v.sound(music.beat(bpm, bars, MUSIC, vol=0.9), 0.0, 0.3)
    return v


def selftest():
    v = make_video()
    assert len(v.scenes) == len(LINES) and v.duration > 1, v.duration
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the scene list only")
    else:
        rep = v.dry_run(6)
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
