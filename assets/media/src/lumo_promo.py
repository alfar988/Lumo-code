#!/usr/bin/env python3
"""Source of assets/media/lumo-promo.mp4, made from templates/video-promo.py: the Lumo Code promo.

Render from the Lumo folder:  LUMO_VIDEO_OUT=assets/media/lumo-promo.mp4 python assets/media/src/lumo_promo.py
Check without ffmpeg:         python assets/media/src/lumo_promo.py --selftest
Needs:                        Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "videokit"))      # the bundled lumovideo library
from lumovideo import PALETTES, Typewriter, Video, clamp, ease, sfx   # noqa: E402

BRAND = "Lumo Code"
TAGLINE = "An AI coding agent for your terminal"
HOOK = "Want to build things from your phone?"
FEATURES = [                                     # (icon, heading, one short line)
    ("bolt", "37 starters", "Games, sites, APIs and videos, tested."),
    ("shield", "Checks itself", "It tests its work, then fixes what fails."),
    ("star", "Free to start", "Works with the free models on OpenRouter."),
]
OFFER = "Open source"
CTA = "Get it on GitHub"
VERTICAL = False                                 # True makes a 720x1280 video for Reels, Shorts and stories
PALETTE = PALETTES["sunset"]
BG_TOP, BG_BOTTOM = "#1a1033", "#3b1d5c"


def icon(c, kind, x, y, s, color):
    """A simple icon from shapes, centred on x, y and about 2*s big."""
    if kind == "bolt":
        pts = [(0.15, -1), (-0.55, 0.1), (-0.05, 0.1), (-0.2, 1), (0.55, -0.2), (0.05, -0.2)]
    elif kind == "shield":
        pts = [(0, -1), (0.8, -0.7), (0.7, 0.2), (0, 1), (-0.7, 0.2), (-0.8, -0.7)]
    elif kind == "heart":
        c.circle(x - 0.36 * s, y - 0.25 * s, 0.46 * s, fill=color)
        c.circle(x + 0.36 * s, y - 0.25 * s, 0.46 * s, fill=color)
        pts = [(-0.78, -0.02), (0.78, -0.02), (0, 0.95)]
    else:                                        # star
        pts = []
        for i in range(10):
            r = 1.0 if i % 2 == 0 else 0.45
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((math.cos(a) * r, math.sin(a) * r))
    c.poly([(x + px * s, y + py * s) for px, py in pts], fill=color)


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h)
    cx, cy = w / 2.0, h / 2.0
    big = 70 if VERTICAL else 84

    def backdrop(c, accent):
        c.background(BG_TOP, BG_BOTTOM)
        c.glow(cx + 280 * math.sin(c.T * 1.2), cy * 0.8 + 100 * math.cos(c.T * 0.9), 480, accent, 0.34)      # the light drifts, so the picture is never frozen
        c.glow(cx - 320 * math.sin(c.T * 1.0 + 1.0), cy * 1.15 + 50 * math.sin(c.T * 1.7), 340, PALETTE[2], 0.22)
        c.vignette(0.4)

    def hook(c, t):
        backdrop(c, PALETTE[0])
        c.text(HOOK, cx, cy, big, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.5, "out_back"), max_w=w * 0.86)
    v.scene(2.6, hook, name="hook", fade_in=0.2)
    v.sfx("whoosh", 0.1, vol=0.6)
    v.sfx("riser", 0.5, vol=0.35)

    def brand(c, t):
        backdrop(c, PALETTE[1])
        for i in range(3):
            k = clamp((t - i * 0.2) / 1.1)
            c.circle(cx, cy - 40, 60 + 380 * ease(k, "out_cubic"), outline=PALETTE[1], width=4, alpha=1 - k)
        c.text(BRAND, cx, cy - 40, big + 26, "#ffffff", outline="#000000", outline_w=7, scale=ease((t - 0.2) / 0.6, "out_back"), max_w=w * 0.9)
        c.text(TAGLINE, cx, cy + 90, 40, "#e7dcff", alpha=ease((t - 0.8) / 0.5, "out_quad"), max_w=w * 0.86)
    sc = v.scene(3.2, brand, name="brand", transition="crossfade", trans_dur=0.4)
    v.sfx("boom", sc.start + 0.2, vol=0.5)

    def feature(i, kind, heading, line):
        accent = PALETTE[(i + 2) % len(PALETTE)]
        tw = Typewriter(line, start=0.7, cps=26)
        ix, iy, tx, ty = (cx, cy - 250, w * 0.08, cy - 40) if VERTICAL else (w * 0.22, cy, w * 0.40, cy - 80)

        def draw(c, t):
            backdrop(c, accent)
            p = ease(t / 0.5, "out_back")
            c.circle(ix, iy, 130 * p, fill=accent)
            icon(c, kind, ix, iy, 64 * p, "#1a1033")
            slide = (1 - ease((t - 0.1) / 0.5, "out_cubic")) * 70
            c.text(heading, tx - slide, ty, 78 if not VERTICAL else 68, "#ffffff", anchor="la", outline="#000000", outline_w=5,
                   alpha=ease((t - 0.1) / 0.4, "out_quad"))
            tw.draw(c, t, tx, ty + 110, 40, "#e7dcff", anchor="la", cursor=False, max_w=w - tx - w * 0.06)
        return draw

    for i, (kind, heading, line) in enumerate(FEATURES):
        sc = v.scene(3.6, feature(i, kind, heading, line), name="feature%d" % (i + 1), transition="slide_left", trans_dur=0.4)
        v.sfx("pop", sc.start + 0.1, vol=0.7)
        v.sfx("whoosh", sc.start, vol=0.4)

    def offer(c, t):
        backdrop(c, PALETTE[3])
        c.text(OFFER, cx, cy - 90, big, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.5, "out_back"), max_w=w * 0.9)
        p = ease((t - 0.5) / 0.4, "out_back")
        k = p * (1 + 0.04 * math.sin(t * 6))
        bw = max(460, 34 * len(CTA) + 90)                                    # a long call to action gets a wider button
        c.rect(cx, cy + 90, bw * k, 110 * k, fill=PALETTE[1], radius=55, anchor="c")
        c.text(CTA, cx, cy + 90, 52 * p, "#1a1033")
    sc = v.scene(4.0, offer, name="offer", transition="crossfade", trans_dur=0.4)
    v.sfx("coin", sc.start + 0.5, vol=0.8)
    v.sfx("success", sc.start + 0.9, vol=0.6)

    def outro(c, t):
        backdrop(c, PALETTE[0])
        c.text(BRAND, cx, cy - 20, big, "#ffffff", outline="#000000", outline_w=6, alpha=ease(t / 0.5, "out_quad"), max_w=w * 0.9)
        c.text("github.com/alfar988/Lumo-code", cx, cy + 70, 38, "#e7dcff", alpha=ease((t - 0.4) / 0.5, "out_quad"), max_w=w * 0.92)
    v.scene(2.2, outro, name="outro", fade_out=0.5, transition="crossfade", trans_dur=0.4)
    return v


def selftest():
    v = make_video()
    assert v.duration > 15 and len(v.scenes) >= 5 + len(FEATURES) - 1, v.duration
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
