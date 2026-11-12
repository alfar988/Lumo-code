#!/usr/bin/env python3
"""__TITLE__: a 3D scene with a moving camera (low-poly world, a 3D stick figure that acts, labels) made with Python: lumovideo Scene3D.

Run:        python world3d.py                    writes videos/world3d.mp4 (854x480, 30 fps; 3D frames are heavy: try quality "draft" first)
            python world3d.py --selftest         checks a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       the settings and the objects in build(). Everything moves by functions of time t inside animate(): set .pos / .rot of shapes, figure.play("move", t),
            world.camera.orbit(...) or world.camera.look(pos, target). Moves and poses: poses(), moves(), define_pose(), define_move().
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import Scene3D, Video, moves, sfx   # noqa: E402

TITLE = "__TITLE__"
SECONDS = float("__SECONDS__")
SKY = ("#6fa8ff", "#dff0ff")             # top and horizon colours
GROUND = "#4b8b4f"
ACTIONS = ["wave", "cheer", "salute", "point"]    # the figure plays these in turn (any names from moves())


def build():
    rnd = random.Random(5)
    world = Scene3D(duration=SECONDS, sky=SKY, ground=GROUND, title=TITLE)
    for i in range(16):                                                  # trees on a ring
        a = i * 2 * math.pi / 16 + rnd.uniform(-0.1, 0.1)
        x, z = 11 * math.cos(a), 4 + 11 * math.sin(a)
        world.cylinder(0.22, 1.2, color="#5a3a1e", pos=(x, 0.6, z))
        world.cone(1.1, 2.6, color=rnd.choice(["#2f6b3a", "#3a7d44", "#2a5e34"]), pos=(x, 2.5, z))
    towers = [world.box(1.4, 2.0 + i, 1.4, color=c, pos=(-3 + i * 3, 1.0 + i / 2.0, 9)) for i, c in enumerate(["#ff6b6b", "#ffd166", "#4aa3ff"])]
    ball = world.sphere(0.6, color="#ffd166", pos=(3.2, 0.6, 3))
    hero = world.person(color="#4aa3ff", pos=(0, 0, 3), yaw=-90, name="HERO")
    acts = [m for m in ACTIONS if m in moves()] or ["wave"]

    def animate(w, t):
        ball.pos = (3.2, 0.6 + abs(math.sin(t * 3.0)) * 1.1, 3)
        for i, tw in enumerate(towers):
            tw.rot = (0, math.sin(t * 0.8 + i) * 8, 0)
        k = int(t // 2.0) % len(acts)
        hero.play(acts[k], t % 2.0)
        w.camera.orbit((0, 1.2, 3), 8.5 - 1.5 * math.sin(t * 0.3), 2.6 + 0.8 * math.sin(t * 0.5), t * 22.0, fov=55.0)
        w.label(acts[k], (0, 2.3, 3), size=34)
    world.animate = animate
    world.sound(0.0, sfx.wind(SECONDS, 0.25), 0.5)
    v = Video(1280, 720, fps=30)
    v.add(world)
    return v, world


def selftest():
    v, world = build()
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: nothing else to check")
    else:
        rep = v.dry_run(5)
        assert rep["blank_frames"] == 0 and rep["motion"] > 0.2, rep
    print("all checks passed")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    v, world = build()
    v.render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
