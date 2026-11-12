#!/usr/bin/env python3
"""__TITLE__: a 3D stickman fight (low-poly arena, moving camera) made with Python: lumovideo Fight + Scene3D.

Run:        python fight3d.py                    writes videos/fight3d.mp4 (854x480, 30 fps; 3D frames are heavy: try quality "draft" first)
            python fight3d.py --selftest         checks the choreography and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       the settings below. The choreography is the same as the 2D fight (f.auto, or script it by hand with f.attack / f.dodge / f.text); only the camera differs.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import Fight, Scene3D, Stick, Video   # noqa: E402

TITLE = "__TITLE__"
NAME_A, NAME_B = "__NAME_A__", "__NAME_B__"
COLOR_A, COLOR_B = "#4aa3ff", "#ff5a5a"
STAGE = "__STAGE__"                      # dojo | city_night | arena | forest | sunset | plain
SECONDS = float("__SECONDS__")
WINNER = "__WINNER__"                    # "a" or "b"
SEED = 3
PACE = 1.0                               # 0.7 slow and tense | 1.5 frantic
MUSIC = None                             # None | "fight" | "epic" | "8bit" | "chill"


def build():
    a = Stick(NAME_A, COLOR_A, headband="#ffffff", gloves="#ff4d4d")
    b = Stick(NAME_B, COLOR_B, headband="#ffd166", gloves="#2b2b2b")
    f = Fight(a, b, stage=STAGE, title=TITLE or None, music=MUSIC)
    f.auto(duration=SECONDS, winner=WINNER, seed=SEED, pace=PACE)
    world = Scene3D.from_fight(f)
    v = Video(1280, 720, fps=30)
    v.add(world)
    return v, f


def selftest():
    v, f = build()
    s = f.summary()
    assert s["ko"] in (NAME_A, NAME_B) and sum(s["hits"]) >= 2, s
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the choreography only")
    else:
        rep = v.dry_run(5)
        assert rep["blank_frames"] == 0 and rep["motion"] > 0.2, rep
    print("all checks passed")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    v, f = build()
    print(f.summary())
    v.render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
