#!/usr/bin/env python3
"""__TITLE__: a 2D stickman fight video made with Python (lumovideo) and rendered to MP4 with sound.

Run:        python fight.py                      writes videos/fight.mp4 (854x480, smooth 60 fps, varied sounds)
            python fight.py --selftest           checks the choreography and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow). The render_video tool installs nothing itself.
EDIT:       the names, colours, stage and length in the settings below. build() holds the fight: either the automatic director
            (f.auto) or your own moments (f.attack, f.block, f.dodge ...). Keep the rest.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import Fight, Stick, Video                           # noqa: E402

# ---- settings ----
TITLE = "__TITLE__"                    # shown at the top of the screen (use "" for none)
NAME_A, NAME_B = "__NAME_A__", "__NAME_B__"
COLOR_A, COLOR_B = "#4aa3ff", "#ff5252"
STAGE = "__STAGE__"                    # dojo | city_night | sunset | arena | forest | plain
SECONDS = float("__SECONDS__")         # length of the fight before the winner banner (the video is a little longer: hit stops and slow motion)
WINNER = "__WINNER__"                  # "a" or "b"
SEED = 3                               # another number gives another fight
MUSIC = None                           # None, or "fight" | "epic" | "8bit" | "chill" for a background track
PACE = 1.0                             # 0.7 slow and tense | 1.0 normal | 1.5 frantic (more exchanges per second)
VOICES = False                         # True adds synthesised grunts and shouts
REAL_SOUNDS = False                    # True looks for free real sound effects on the internet (cached in sounds/, credits in sounds/CREDITS.txt); offline it keeps the synthesised ones


def build():
    a = Stick(NAME_A, COLOR_A, headband="#ffffff", gloves="#ff4d4d")
    b = Stick(NAME_B, COLOR_B, headband="#ffd166", gloves="#2b2b2b")
    f = Fight(a, b, stage=STAGE, title=TITLE or None, music=MUSIC, voices=VOICES)
    f.auto(duration=SECONDS, winner=WINNER, seed=SEED, pace=PACE)
    if REAL_SOUNDS:
        f.use_internet_sounds()
    # By hand instead of f.auto(...):
    #   f.gap(0.5, 90, 1.2); f.attack("a", "jab", at=2.0); f.attack("b", "cross", at=2.9, hit=False); f.dodge("a", at=2.85)
    #   f.attack("a", "round_kick", at=6.0, finisher=True); f.victory("a", at=8.0); f.text(6.4, "K.O.", 1.4, 200, "#ff5252", "slam")
    v = Video(1280, 720)
    v.add(f)
    return v, f


def selftest():
    v, f = build()
    s = f.summary()
    assert s["ko"] in (NAME_A, NAME_B), s
    assert s["hp"][0 if s["ko"] == NAME_A else 1] == 0, s
    assert sum(s["hits"]) >= 2 and s["duration"] > 4, s
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the choreography only")
    else:
        rep = v.dry_run(6)
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
