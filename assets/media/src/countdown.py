#!/usr/bin/env python3
"""Source of assets/media/countdown.mp4, made from templates/video-countdown.py: a countdown with fireworks.

Render from the Lumo folder:  LUMO_VIDEO_OUT=assets/media/countdown.mp4 python assets/media/src/countdown.py
Check without ffmpeg:         python assets/media/src/countdown.py --selftest
Needs:                        Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "videokit"))      # the bundled lumovideo library
from lumovideo import PALETTES, Particles, Video, ease, sfx   # noqa: E402

TITLE = "Happy New Year"
SUBTITLE = "See you in 2027"
START = 5
BURSTS = 9                                       # fireworks in the last scene
VERTICAL = False
PALETTE = PALETTES["sunset"]
BG_TOP, BG_BOTTOM = "#0a0820", "#241a52"


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h)
    cx, cy = w / 2.0, h / 2.0
    r = min(w, h) * 0.28

    def backdrop(c, accent):
        c.background(BG_TOP, BG_BOTTOM)
        c.glow(cx, cy, 440, accent, 0.28)
        c.vignette(0.4)

    def number(n):
        accent = PALETTE[n % len(PALETTE)]

        def draw(c, t):
            backdrop(c, accent)
            k = ease(t / 1.0, "linear")
            c.arc(cx, cy, r, 0, 360, "#2c2760", 18)
            c.arc(cx, cy, r, -90, -90 + 360 * (1 - k), accent, 18)
            pop = 1.0 + 0.35 * (1 - ease(t / 0.35, "out_cubic"))
            c.text(str(n), cx, cy, r * 1.35 * pop, "#ffffff", outline="#000000", outline_w=8)
        return draw

    for n in range(START, 0, -1):
        sc = v.scene(1.0, number(n), name="n%d" % n, fade_in=0.2 if n == START else 0.0)
        v.sfx("click", sc.start, vol=0.7)
        v.sfx("beep", sc.start + 0.02, vol=0.35)

    ps = Particles(seed=4)
    for k in range(BURSTS):
        at = 0.25 + 0.42 * k
        x = w * (0.2 + 0.6 * ((k * 0.37) % 1.0))
        y = h * (0.22 + 0.3 * ((k * 0.53) % 1.0))
        ps.burst(at, x, y, n=46, speed=300, life=1.4, color=PALETTE[k % len(PALETTE)], size=7)

    def finale(c, t):
        backdrop(c, PALETTE[1])
        ps.draw(c, t)
        c.text(TITLE, cx, cy - 10, 100 if not VERTICAL else 76, "#ffffff", outline="#000000", outline_w=8, scale=ease((t - 0.3) / 0.6, "out_back"), max_w=w * 0.9)
        c.text(SUBTITLE, cx, cy + 110, 42, "#ffe9b8", outline="#000000", outline_w=3, alpha=ease((t - 1.0) / 0.5, "out_quad"), max_w=w * 0.88)
    end = 0.25 + 0.42 * BURSTS + 1.8
    sc = v.scene(max(5.0, end), finale, name="finale", transition="crossfade", trans_dur=0.3, fade_out=0.6)
    for k in range(BURSTS):
        v.sfx("explosion", sc.start + 0.25 + 0.42 * k, vol=0.45)
    v.sfx("cheer", sc.start + 0.6, vol=0.6)
    v.sfx("applause", sc.start + 1.2, vol=0.5)
    return v


def selftest():
    v = make_video()
    assert v.duration > START + 4 and len(v.scenes) == START + 1, v.duration
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
