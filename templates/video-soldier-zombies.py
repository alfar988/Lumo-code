#!/usr/bin/env python3
"""__TITLE__: soldiers with rifles hold a street against waves of zombies (2D, made with Python: lumovideo Actor + Show).

Run:        python zombies.py                    writes videos/zombies.mp4 (854x480, smooth 60 fps, gunfire, groans, explosions)
            python zombies.py --selftest         checks the plan and a few frames without ffmpeg
Needs:      Pillow and ffmpeg (Termux: pkg install ffmpeg python-pillow).
EDIT:       the settings below. The shooting plan is worked out for you; every shot, hit, fall and explosion is a line of the timeline.
            Own animations: define_pose / define_move, then actor.play(at, "your_move"). Other scenes: write a new script with Actor and Show.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # lumovideo.py sits next to this script
from lumovideo import Actor, Show, Video, sfx   # noqa: E402

TITLE = "__TITLE__"
STAGE = "__STAGE__"                      # city_night | sunset | forest | arena | dojo | plain
SECONDS = float("__SECONDS__")
SOLDIERS = 2                             # 1 to 4
WAVES = 3
PER_WAVE = 5                             # zombies in the first wave; every wave brings two more (the last wave has a big brute)
OUTCOME = "win"                          # "win": the soldiers hold | "lose": the horde overruns them at the end
GRENADES = 1                             # grenades thrown into the crowd
SEED = 7
MUSIC = "epic"                           # None | "epic" | "fight" | "chill" | "8bit"
FRONT = 330.0                            # where the zombies stop to bite (the soldiers' line)


def build():
    rnd = random.Random(SEED)
    names = ["Rex", "Kay", "Max", "Ivy"][:max(1, min(4, SOLDIERS))]
    soldiers = [Actor(n, "#3a7d44", x=150 + i * 62, weapon="rifle", look="soldier", lane=(i % 2) * 20 - 10) for i, n in enumerate(names)]
    zombies = []
    span = max(4.0, (SECONDS - 6.0) / WAVES)
    for w in range(WAVES):
        for k in range(PER_WAVE + 2 * w):
            kind = "brute" if (w == WAVES - 1 and k == 0) else ("runner" if w > 0 and rnd.random() < 0.22 else "walker")
            hp = {"walker": 2, "runner": 1, "brute": 5}[kind]
            speed = {"walker": rnd.uniform(75, 105), "runner": rnd.uniform(170, 220), "brute": 62.0}[kind]
            born = 1.6 + w * span + k * rnd.uniform(0.3, 0.7)
            x0, stop = 1400 + rnd.uniform(0, 260), FRONT + rnd.uniform(0, 36)
            a = Actor("Z%d.%d" % (w, k), {"walker": "#7fb069", "runner": "#9bbf5a", "brute": "#5f8f4a"}[kind], x=x0, facing=-1, scale=1.3 if kind == "brute" else 1.0,
                      look="zombie", hp=hp, lane=rnd.choice((-18, 0, 18)))
            a.walk(born, to=stop, speed=speed, gait="sprint" if kind == "runner" else "zombie")
            zombies.append(dict(a=a, born=born, x0=x0, stop=stop, speed=speed, hp=hp, end=None))
    show = Show(STAGE, soldiers + [z["a"] for z in zombies], title=TITLE, music=MUSIC, duration=SECONDS)

    def px(z, t):
        return max(z["stop"], z["x0"] - z["speed"] * (t - z["born"])) if t >= z["born"] else z["x0"]

    def alive(t):
        return [z for z in zombies if z["end"] is None and z["born"] <= t and px(z, t) < 1250]
    cool = [0.0] * len(soldiers)
    grenade_at = [SECONDS * (0.42 + 0.25 * i) for i in range(GRENADES)]
    lose_from = SECONDS * 0.7 if OUTCOME == "lose" else 1e9
    t = 1.2
    while t < SECONDS - 1.8:
        if grenade_at and t >= grenade_at[0]:
            near = sorted(alive(t), key=lambda z: px(z, t))[:5]
            if len(near) >= 3:
                cx = sum(px(z, t + 0.55) for z in near) / len(near)
                soldiers[-1].play(t, "throw")
                show.explode(t + 0.55, x=cx, radius=190)
                for z in alive(t + 0.55):
                    if abs(px(z, t + 0.55) - cx) <= 190:
                        z["end"] = t + 0.55
                grenade_at.pop(0)
        for i, s in enumerate(soldiers):
            if t < cool[i] or t > lose_from:
                continue
            targets = alive(t)
            if not targets:
                continue
            z = min(targets, key=lambda q: px(q, t))
            for b in range(rnd.randint(2, 4)):
                hit = rnd.random() < 0.82
                s.shoot(t + b * 0.11, target=z["a"], hit=hit, dmg=1)
                if hit:
                    z["hp"] -= 1
                    if z["hp"] <= 0:
                        z["end"] = t + b * 0.11 + 0.05
                        break
            cool[i] = t + 0.5 + rnd.uniform(0.2, 0.5)
        t += 0.1
    for z in zombies:                                                    # zombies that got through bite the line
        if z["end"] is None and z["born"] + (z["x0"] - z["stop"]) / z["speed"] < SECONDS - 1.0:
            reach = z["born"] + (z["x0"] - z["stop"]) / z["speed"]
            for j in range(3):
                z["a"].bite(reach + j * 1.0)
            soldiers[0].hurt(reach + 0.3)
        if rnd.random() < 0.4:
            show.sound(z["born"] + 0.2, sfx.groan(dur=1.0, vol=0.5, variant=int(z["x0"]) % 5), 0.45)
    if OUTCOME == "lose":
        for i, s in enumerate(soldiers):
            s.die(SECONDS - 3.4 + i * 0.7)
    for w in range(WAVES):
        show.text(1.0 + w * span - 0.1, "WAVE %d" % (w + 1), dur=1.4, size=96, color="#ffd166", style="slam")
    show.text(SECONDS - 2.6, "SURVIVED" if OUTCOME == "win" else "OVERRUN", dur=2.2, size=120, color="#ff5252" if OUTCOME != "win" else "#3ddc84", style="slam")
    show.sound(0.0, sfx.wind(SECONDS, 0.25), 0.4)
    show.camera_keys([(0, 560, 1.18), (SECONDS * 0.5, 640, 1.22), (SECONDS, 600, 1.12)])
    v = Video(1280, 720)
    v.add(show)
    return v, show


def selftest():
    v, show = build()
    s = show.summary()
    assert s["shots"] >= 8 and s["kills"] >= 3, s
    if OUTCOME == "win":
        assert len(s["alive"]) >= SOLDIERS, s
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed: checked the plan only")
    else:
        rep = v.dry_run(6)
        assert rep["blank_frames"] == 0 and rep["motion"] > 0.2, rep
    print("all checks passed")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    v, show = build()
    print(show.summary())
    v.render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
