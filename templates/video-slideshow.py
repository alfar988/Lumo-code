#!/usr/bin/env python3
"""__TITLE__: a photo slideshow video made with Python (lumovideo): slow zoom and pan on every picture, captions, cross-fades, optional soft music.

Run:        python slideshow.py                  writes videos/slideshow.mp4
            python slideshow.py --selftest       checks the scenes and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       PHOTOS (paths of the user's pictures), CAPTIONS (one per picture), SECONDS, MUSIC, VERTICAL. With no PHOTOS it draws colour cards so the video still plays.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import PALETTES, Video, ease, music, sfx   # noqa: E402

TITLE = "__TITLE__"
SUBTITLE = "__SUBTITLE__"
PHOTOS = []                                      # for example ["photos/beach.jpg", "photos/hike.jpg"]; relative paths are read from the folder you run it in
CAPTIONS = ["First stop", "Second stop", "Third stop", "Last stop"]
SECONDS = 4.0                                    # per picture
MUSIC = False                                    # True adds a quiet chill loop; only when the user asked for music
VERTICAL = False
PALETTE = PALETTES["candy"]


def load_pictures(w, h):
    """The user's pictures (shrunk once so every frame is quick), or generated colour cards when there are none."""
    from PIL import Image, ImageDraw
    from lumovideo import mix
    found = []
    for p in PHOTOS:
        try:
            im = Image.open(p).convert("RGB")
        except (OSError, ValueError):
            print("cannot open %s: skipped" % p)
            continue
        im.thumbnail((int(w * 1.5), int(h * 1.5)))
        found.append(im)
    if found:
        return found
    cards = []
    for k in range(len(CAPTIONS)):
        im = Image.new("RGB", (int(w * 1.3), int(h * 1.3)))
        d = ImageDraw.Draw(im)
        top, bottom = PALETTE[k % len(PALETTE)], PALETTE[(k + 2) % len(PALETTE)]
        for y in range(im.height):
            d.line([(0, y), (im.width, y)], fill=mix(top, bottom, y / im.height))
        d.ellipse([im.width * 0.55, im.height * 0.15, im.width * 0.85, im.height * 0.15 + im.width * 0.3], fill=mix(bottom, "#ffffff", 0.35))
        cards.append(im)
    return cards


def make_video():
    w, h = (720, 1280) if VERTICAL else (1280, 720)
    v = Video(w, h)
    cx, cy = w / 2.0, h / 2.0
    pics = load_pictures(w, h)

    def slide(i, im):
        cover = max(w / im.width, h / im.height)
        zin = i % 2 == 0
        dx = (1 if i % 4 < 2 else -1) * w * 0.025
        cap = CAPTIONS[i] if i < len(CAPTIONS) else ""

        def draw(c, t):
            k = ease(t / SECONDS, "in_out_sine")
            zoom = (1.0 + 0.12 * k) if zin else (1.12 - 0.12 * k)
            c.image(im, cx + dx * (k - 0.5) * 2, cy, w=im.width * cover * zoom)
            if i == 0:
                c.tint("#000000", 0.35)
                c.text(TITLE, cx, cy - 20, 88 if not VERTICAL else 70, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.6, "out_back"), max_w=w * 0.88)
                c.text(SUBTITLE, cx, cy + 80, 40, "#f3f3f3", outline="#000000", outline_w=3, alpha=ease((t - 0.6) / 0.5, "out_quad"), max_w=w * 0.88)
            elif cap:
                c.rect(0, h - 150, w, 150, fill="#000000", alpha=0.45)
                c.text(cap, cx, h - 75, 52, "#ffffff", outline="#000000", outline_w=4, alpha=ease((t - 0.3) / 0.5, "out_quad"), max_w=w * 0.9)
        return draw

    for i, im in enumerate(pics):
        sc = v.scene(SECONDS, slide(i, im), name="photo%d" % (i + 1), transition=None if i == 0 else "crossfade", trans_dur=0.6,
                     fade_in=0.4 if i == 0 else 0.0, fade_out=0.6 if i == len(pics) - 1 else 0.0)
        if i:
            v.sfx("whoosh", sc.start, vol=0.25)
    if MUSIC:
        v.sound(music.beat(84, 8, "chill"), 0.0, vol=0.3)
    return v


def selftest():
    v = make_video()
    assert v.duration >= SECONDS and len(v.scenes) >= 1, v.duration
    rep = v.dry_run(8)
    assert rep["blank_frames"] == 0 and rep["motion"] > 0.05, rep
    print("all checks passed")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    make_video().render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
