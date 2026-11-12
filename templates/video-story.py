#!/usr/bin/env python3
"""__TITLE__: a short animated story with two characters who walk in, talk (captions above their heads), gesture and react (2D, lumovideo Actor + Show).

Run:        python story.py                      writes videos/story.mp4 (854x480, smooth 60 fps)
            python story.py --selftest           checks the timeline and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       NAME_A, NAME_B, STAGE and LINES. Each line is (speaker 0 or 1, text, gesture or None). Gestures: any move name from moves() (wave point cheer salute surrender
            jump ...) or your own define_move(...). Weapons, zombies, more characters, other scenes: use Actor / Show directly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import Actor, Show, Video, sfx   # noqa: E402

TITLE = "__TITLE__"
NAME_A, NAME_B = "__NAME_A__", "__NAME_B__"
STAGE = "__STAGE__"                      # sunset | plain | forest | city_night | arena | dojo
COLOR_A, COLOR_B = "#4aa3ff", "#ff9f4a"
LINES = [
    (0, "Hi! Nice to meet you.", "wave"),
    (1, "Hello! Want to see something cool?", "point"),
    (0, "Yes, show me!", "cheer"),
    (1, "Watch this...", "jump"),
    (0, "Wow! That was amazing!", "cheer"),
]
MUSIC = "chill"                          # None | "chill" | "epic" | "fight" | "8bit"


def build():
    a = Actor(NAME_A, COLOR_A, x=120)
    b = Actor(NAME_B, COLOR_B, x=1160, facing=-1)
    a.walk(0.4, to=470, dur=1.8)
    b.walk(0.4, to=810, dur=1.8)
    t = 2.6
    for who, text, gesture in LINES:
        speaker = (a, b)[who % 2]
        dur = max(1.8, 0.07 * len(text) + 0.6)
        speaker.say(t, text, dur=dur)
        if gesture:
            speaker.play(t + 0.2, gesture)
        show_sound = sfx.pop()
        t += dur + 0.35
    a.walk(t, to=1330, dur=2.2)
    b.walk(t, to=-60, dur=2.2)
    end = t + 2.4
    show = Show(STAGE, [a, b], title=TITLE, music=MUSIC, duration=end)
    show.camera_keys([(0, 640, 1.0), (end * 0.5, 640, 1.25), (end, 640, 1.0)])
    show.text(0.2, TITLE, dur=1.8, size=84, style="pop", y=140)
    v = Video(1280, 720)
    v.add(show)
    return v, show


def selftest():
    v, show = build()
    assert show.duration > 6, show.duration
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the timeline only")
    else:
        rep = v.dry_run(6)
        assert rep["blank_frames"] == 0 and rep["motion"] > 0.2, rep
    print("all checks passed")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    v, show = build()
    v.render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
