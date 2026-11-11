---
name: video-skill
description: 2D videos made with Python (stickman fights, explainers, kinetic text, charts, slideshows) rendered to a playable MP4 with sound: brief, storyboard, the bundled lumovideo library, render_video, checks.
---
# Video skill (2D videos with Python → MP4)

## Quick rules (read first)
1. Make a video only when the user asked for one (or for an animation they want to watch). Questions, code help, "video game", an HTML `<video>` tag or a video player page are not video requests. Do not add a video, a GIF, music, an intro, credits or extra scenes that nobody asked for.
2. If the user says "MP3" for a video, they mean MP4 (MP3 is audio only). Make the MP4 and say so in one short line.
3. Build everything in Python: one script `videos/<name>.py` that starts with `from lumovideo import *`, then run the `render_video` tool on it. The tool turns the script into a real MP4 (H.264 + AAC, plays in any player) inside the workspace. Do not hand the user frames, or a script to run, unless they asked for the script.
4. Do not interrogate the user. Missing details get the defaults below; say the assumptions in one line. Ask one short question only when the subject itself is unknown ("a video of what?").
5. Read what `render_video` returns (the `checks:` line and every `WARNING:`). Fix the warnings before you say it is done. Finish with the file path, the length, what is in it and how to play it.
6. Draw everything with the library. Sound: use its synthesised effects (over 80, no download); when the user wants real or more varied sound effects, use `find_sound` (free CC0 / CC-BY recordings, credits in `sounds/CREDITS.txt`). Never download songs, music, lyrics, copyrighted characters or footage, and never use a real person's face or voice.
7. Every request is paid for from a daily allowance on free models: start from a template (`use_template`) and change only the settings, write the script in one `write_file`, render once, fix only real warnings. A finished video should take about four requests, not thirty.

## Defaults (use them, do not ask)
| Missing | Use |
|---|---|
| length | fight 12-16 s, title or quote 5-8 s, explainer 20-40 s, chart 8-12 s |
| format | 1280x720 landscape; 720x1280 (`Video(720, 1280)`) when the user says TikTok, Reels, Shorts, story or vertical |
| quality | `standard` (854x480, smooth 60 fps, several CPU cores). `draft` (480x270, 24 fps) first when the script is new and over 25 s. `hd` only when asked. Leave `fps` out of `Video(...)`: the quality chooses it |
| sound | hit and whoosh sounds for fights, a soft `ding`/`whoosh` on text reveals. Music only when the user asks for music or a mood |
| text language | the user's language, short lines, readable at phone size |
| names, colours, stage | pick distinct colours (blue vs red) and a fitting stage; use the names the user gave |

## Workflow
1. **Brief** in your head: subject, length, format, style, sound. One line of assumptions to the user.
2. **Storyboard** (anything over 10 s): 3-6 beats with times, for example `0-2 s title · 2-9 s fight · 9-12 s K.O. and winner`.
3. **Script**: write the whole `videos/<name>.py` in one `write_file`. When a template fits, `use_template` it (`video-stickman-fight`, `video-explainer`, `video-kinetic-text`) and change names, colours, stage and length.
4. **Render**: `render_video` with `script`. Use `quality: "draft"` for a first pass of a long or new script, then the final render.
5. **Check and fix**: no blank frames, some motion, brightness above 6. A WARNING means a real problem: fix the script and render again. Never re-render without a reason.
6. **Report**: path (for example `videos/fight.mp4`), length, resolution, one sentence on what happens, and HOW TO PLAY it (the render result lists the commands; always pass them on, in the user's language): `termux-open videos/fight.mp4`, or `/play` inside Lumo, or for the Gallery run `termux-setup-storage` once, then `cp videos/fight.mp4 ~/storage/movies/` and open Gallery, Files, VLC or MX Player (`/play --gallery` does the copy).

If `render_video` says ffmpeg or Pillow is missing, run the install command it prints with `run_shell` (the user approves it), then render again. Python 3.8 or newer is enough; numpy is not needed.

## Tools
- `render_video(script, output?, quality?, open?)`: runs the script, encodes the MP4, probes it and returns the checks. `open: true` starts the device player; use it only when the user wants to watch it right now.
- `video_info(path)`: length, size, fps, codecs, sound, blank or frozen frames of any video file.
- `find_sound(query, count?, max_seconds?, url?)`: looks up FREE sound effects on the internet (Openverse; Freesound too when the user stored a `FREESOUND_API_KEY` secret), saves short WAV takes in `sounds/` and writes `sounds/CREDITS.txt`. Use English queries (`punch impact`, `zombie growl`, `rifle shot`). Use it only when real recordings are wanted; the synthesised effects need no download.
- The user can type `/play` (newest video) or `/play --gallery` (also copies it to the phone's Movies folder).
- Inside a script `print(fight.summary())` or `print(v.dry_run())` shows numbers about the result without rendering. The text appears in the render log.

## The lumovideo library (what you can call)
Coordinates are always in the `Video(width, height)` space (1280x720 by default); `quality` only changes the output pixels.

**Video and scenes**
- `v = Video(1280, 720, bg="#000000")` (fps follows the quality: 60; `fps=30` is allowed and then motion blur is added; `blur=3` forces blur), `v.scene(seconds, draw, fade_in=0, fade_out=0, transition=None, trans_dur=0.5)`, `v.add(obj)` (a Fight or any object with `.duration` and `.draw(c, t)`), `v.sound(buffer, at, vol=1, pan=0)`, `v.render()`.
- `draw(c, t)` is called per frame: `c` is the Canvas, `t` the seconds since the scene started (`c.T` is the global time, `c.W` and `c.H` the size). A scene that takes only `c` also works.
- Transitions: `cut`, `fade`, `crossfade`, `slide_left`, `slide_right`, `slide_up`, `slide_down`, `wipe_left`, `wipe_right`, `zoom`.
- `v.frame_at(t)` returns a PIL image, `v.dry_run()` returns the checks without ffmpeg.

**Canvas (drawing)**
- `c.background(top, bottom)`, `c.clear(color)`, `c.line`, `c.polyline`, `c.circle(x, y, r, fill, outline, width, alpha)`, `c.ellipse`, `c.rect(x, y, w, h, fill, outline, radius, anchor, alpha)`, `c.poly`, `c.arc`, `c.glow(x, y, r, color, strength)`, `c.vignette`, `c.tint(color, amount)`, `c.letterbox`.
- `c.text(s, x, y, size, color, anchor="mm", outline=, outline_w=, shadow=(dx, dy, color), alpha=, scale=, rot=, max_w=)`: `anchor` is two letters, horizontal l/m/r + vertical a/m/d. `scale=ease(t / 0.4, "out_back")` pops text in. `c.text_size(s, size)` measures it.
- `c.image(path_or_PIL, x, y, w=, h=, alpha=, rot=)` for pictures the user gave you.
- Camera: `c.camera(x, y, zoom, shake)`; `with c.screen():` draws without the camera (HUD, captions); `with c.parallax(0.3):` draws a far layer that moves less.
- Colours: `"#rrggbb"`, a name, or a tuple. `mix(a, b, t)`, `shade(color, 0.3)` (lighter) or `-0.3` (darker), `PALETTES["neon" | "sunset" | "ocean" | "forest" | "candy" | "mono"]`.

**Timing**
- `ease(t, name)` with `linear`, `smooth`, and `in_`/`out_`/`in_out_` + `quad cubic quart quint sine expo circ back elastic`, plus `out_bounce`. `t` is progress 0..1 and is clamped.
- `tween(t, t0, t1, a, b, easing)`, `remap`, `lerp` (numbers or tuples), `pulse(t, period)`, `noise(x)`, `Keys([(0, 0), (1, 100, "out_cubic")])(t)`, `Spring`, `Timeline().add("title", 0, 1.5)` then `tl.p("title", t)`.

**Sound** (all synthesised)
- Over 80 effects, and every call sounds a little different (pitch, noise, length): `v.sfx("punch", 1.5)` or `v.sound(sfx.punch(1.2), at=1.5, vol=0.9, pan=-0.3)`. Families: fight `punch hit kick slap thud smash crack block clang slash whoosh swing ko` · movement `step(surface="wood|dirt|grass|gravel|metal|sand|concrete") slide land jump fall cloth` · voice `kiai grunt pain gasp laugh` · crowd `crowd cheer applause ooh` · cinematic `boom impact riser downer stinger heartbeat gong taiko drum_roll cymbal rimshot explosion` · nature `wind thunder rain fire drip splash` · interface `ding bell coin pop click blip error laser success fail powerup zap select notify` · machine `beep alarm engine camera key snare hat` · cartoon `boing whistle bonk honk trombone squeak` · weapon `gunshot rifle pistol reload shell` · creature `groan roar zombie_death`. `sfx.names()` lists them, `sfx.get(name, **kw)` calls one by name, `sfx.tone(freq, dur, wave, vol, decay, sweep)` makes your own.
- Vary the sound: use two or three different effects for the same event (a `whoosh` before every strike, `punch` plus `thud` on a heavy hit, `step` with the stage's surface, a `crowd`/`cheer`/`applause` for arenas, `wind` or `rain` as a quiet bed). Never reuse one buffer for every event.
- Real recordings: `buf = sfx.file("sounds/punch-ab12cd.wav")` (wav always, mp3/ogg with ffmpeg), or `sfx.net("punch impact")` inside the script (free CC0 / CC-BY from the internet, cached in `sounds/`, falls back to a synthesised effect when offline). CC-BY needs a credit when the video is published: say so.
- `music.beat(bpm, bars, style, key, seed, vol)` with style `fight`, `chill`, `8bit` or `epic`. `v.sound(music.beat(120, 8, "epic"), at=0, vol=0.35)`. `Mixer(duration)` for your own mix.

**Components**: `Typewriter(text, start, cps).draw(c, t, x, y, size)`, `Particles().burst(at, x, y, n, speed, color)` and `.draw(c, t)`, `BarChart(data).draw(c, t, x, y, w, h, start, dur)`, `Subtitles([(start, end, text)]).draw(c, t)`.

## Stickman fights
`Stick(name, color, headband=, gloves=, belt=, weapon="sword"|"staff"|"knife", scale=1.0)` is the fighter, `Fight(a, b, stage=, title=, music=, voices=False, surface=None)` stages it (`voices=True` adds synthesised grunts and shouts; `surface` = the footstep sound of the floor). Stages: `dojo`, `city_night`, `sunset`, `arena`, `forest`, `plain`. A `Stage` object or any object with `draw(c, t)` also works.

**Fastest good result**: `f.auto(duration=14, winner="a", seed=3, pace=1.0)` writes a complete fight (pace 1.5 = frantic, 0.7 = slow and tense): READY / FIGHT!, walk-in, combos, flurries, trades of blows, blocks, dodges, backflips and counters, a finishing blow, K.O. in slow motion, victory pose and a winner banner. Health bars follow the hits, the loser ends at zero on the finishing blow. Change `seed` for a different fight, `winner` to pick who wins, `finisher=` to pick the last move. Use it unless the user described specific moments.

**By hand** (times in seconds of fight time):
```
f.gap(0.5, 90, 1.2)                         # both walk to fighting distance
f.attack("a", "jab", at=2.0)                # moves: jab cross hook elbow uppercut knee front_kick round_kick axe_kick sweep flying_kick superman_punch
f.attack("b", "cross", at=2.9, hit=False)   # a miss; schedule f.dodge("a", at=2.85) to make it look right
f.block("b", at=3.7); f.attack("a", "front_kick", at=3.8)   # a block around the impact absorbs it
f.attack("a", "round_kick", at=6.0, finisher=True)          # knock-out
f.victory("a", at=8.0); f.text(6.4, "K.O.", 1.4, 200, "#ff5252", "slam")
```
Also `walk`, `run`, `step(who, at, by=60)` (footwork: by > 0 toward the opponent), `dodge(who, at, style="flip")` (a backflip), `duck`, `taunt`, `bow`, `jump`, `use_sounds(punch=[...], kick=..., whoosh=[...])` (your own recordings, used in turn), `use_internet_sounds()` (free real sounds, cached; synthesised when offline), `freeze(at, dur)`, `slowmo(at, dur, rate)`, `zoom(at, dur, amount)`, `sound(at, buffer)`, `text(at, s, dur, size, color, style)` with style `pop`, `slam` or `fade`. Hits already add hit-stop, sparks, a damage number, screen shake and sound; the finisher adds slow motion and a zoom.

**Choreography rules**: three acts (setup, exchange, finish). Alternate who attacks, let one fighter dominate, give a block or dodge before a big hit, keep 1-2 seconds between exchanges, finish with the heaviest move. A fight under 8 s feels rushed, over 20 s drags.
**Your own props or effects**: `f.extra = lambda c, t: ...` draws in world coordinates after the fighters (ground is `f.ground`). Weapons are cosmetic: the same punches and kicks play.
**In a longer video**: `v.scene(2, title_card)`, then `f.transition = "crossfade"; v.add(f)`. The fight adds its own sound track.

## Other kinds of video
- **Title or quote**: gradient `c.background`, `c.text` with `scale=ease(t / 0.5, "out_back")`, a `c.glow` behind it, `fade_out=0.4`.
- **Kinetic text**: one word per beat; each word is a scene of 0.4-0.8 s or a `Timeline` item; change colour with `PALETTES`, alternate `slide_left` and `slide_right` transitions, `sfx.pop()` on each word.
- **Explainer**: one idea per scene (4-6 s), a heading, a short line (`max_w` wraps it), a simple shape animation, `Subtitles` only if the user wants captions. `Typewriter` for code or quotes.
- **Chart**: `BarChart(data).draw(...)` or draw lines and bars yourself with `tween`. Label every bar, keep numbers readable, end with a 1-second hold.
- **Slideshow of the user's pictures**: `c.image(path, x, y, w=...)` with a slow zoom (`1.0 → 1.12` through `ease`) and `crossfade` transitions, 3-5 s per picture.
- **Counting, countdown, loader**: `str(int(ease(t / 3, "linear") * 100))` in big text, `c.arc` for a ring.
- **Cartoon scene (ball, car, character)**: positions from `Keys` or `tween`; squash and stretch with `rx, ry` on `c.ellipse`; shadows on the ground; one idea per scene.

## What makes it look good
- Motion has weight: ease everything (`in_out_cubic` for moves, `out_back` for pop-ins, `out_bounce` for drops). Never move at constant speed unless it is a scroll.
- Anticipation and follow-through: pull back before a fast move, settle after it. Hold the key frame for 2-4 frames on impact.
- Text: at least 5 percent of the video height, always with an outline or shadow or a `c.rect(..., alpha=0.5)` behind it, max two lines, on screen at least 1.2 s plus 0.06 s per word.
- Colour: a dark or mid background with one bright accent; use a `PALETTES` set; keep contrast high.
- Keep one thing moving at a time in the foreground, with slow motion in the background (`c.parallax`).
- Sound sparingly: a sound on each real event, quiet loops under speech or text, never louder than the effects.
- Smooth: leave `fps` to the quality (60 fps), never move a thing by whole pixels per frame, and let every change of pose or position take 0.1 s or more with an ease. Fights blend every pose change for you; in your own scenes tween with `ease`.
- More than numbers: a counter, a percentage or a bar going up is not an animation. Show the idea with moving things (characters, shapes, icons, camera moves, particles) and use numbers only as small labels. Every second needs something to look at that moves with a purpose.
- Layers give depth: sky or gradient, a slow parallax background, the action, foreground dust or particles, then the HUD. `Stage` adds drifting dust, fireflies and camera flashes by itself.
- Impact: a hit needs a pause of two or three frames (hit stop), a flash, sparks or dust, a small shake and two layered sounds. Fights already do this.
- Do not fill the video with extras. Everything on screen should be what the user asked for.

## Checking the result
`render_video` returns `checks: no blank frames · motion X · brightness Y`. Meaning and fixes:
| Warning | Cause and fix |
|---|---|
| frames show a flat colour | a scene draws nothing at that time: check scene durations, `if` conditions, `c.t` ranges |
| more than half of the frames do not change | long holds; add motion or cut the length |
| almost no motion | the animation does not use time: every moving value must depend on `t` |
| picture almost black | the background is never drawn or the colours are too dark |
| ffmpeg or Pillow missing | install as the error says, then render again |
Make small fixes with `edit_file`, not a full rewrite. After the final render, if the length or look is not what was asked, change it once and render again.

## Troubleshooting
- `No module named lumovideo`: render with the tool (it places the library next to the script) or run the script from its own folder.
- Text looks tiny or square: no TrueType font was found. `import lumovideo; lumovideo.USER_FONT = "path/to/font.ttf"` or `pkg install ttf-dejavu` on Termux.
- Rendering is slow or the phone gets hot: render with `quality: "draft"`, shorten the video, avoid `c.image` with huge pictures (resize first). Frames are drawn on up to four CPU cores at once; `LUMO_VIDEO_WORKERS=1` turns that off, `fps=30` halves the work.
- A script that keeps hidden state between frames (a global counter changed inside a draw function) is drawn on one core automatically; make every drawing a pure function of `t` instead.
- `find_sound` says no internet or finds nothing: use the synthesised effects (`sfx.get(...)`), they always work.
- The video does not open: `termux-open` needs `pkg install termux-tools`; otherwise copy it to the Gallery (`/play --gallery`) and open it from there.
- A tool timeout: raise `timeout` or render a shorter test first.
- No sound in the player: `v.sound(...)` was never called, or the environment sets `LUMO_VIDEO_NOAUDIO`.

## Examples (these run in the tests)
Timing helpers (no drawing needed):
```python
# check: runs
from lumovideo import ease, Keys, Timeline, tween, lerp, noise
assert abs(ease(0, "out_back")) < 1e-9 and abs(ease(1, "out_back") - 1) < 1e-9 and ease(2, "in_quad") == 1
k = Keys([(0, 0), (1, 100, "linear"), (2, 40, "linear")])
assert k(0.5) == 50 and k(5) == 40 and k(-1) == 0
tl = Timeline().add("title", 0, 1.5).add("body", 1.0, 2.0)
assert tl.p("title", 0.75) == 0.5 and tl.p("body", 0.0) == 0 and tl.active("body", 1.5)
assert tween(0.5, 0, 1, (0, 0), (10, 20), "linear") == (5.0, 10.0)
assert -1 <= noise(3.3) <= 1
print("timing ok")
```
A scene with text and shapes, checked without ffmpeg:
```python
# check: runs
try:
    import PIL
except ImportError:
    raise SystemExit(0)                      # drawing needs Pillow; the test skips when it is missing
from lumovideo import Video, PALETTES, ease
v = Video(1280, 720)
def title(c, t):
    c.background("#101626", "#243b6b")
    c.glow(640, 360, 380, PALETTES["neon"][0], 0.6)
    c.text("Lumo", 640, 340, 150, "#ffffff", outline="#000000", outline_w=8, scale=ease(t / 0.5, "out_back"))
    c.rect(340, 470, 600 * ease((t - 0.3) / 0.8, "out_cubic"), 8, fill=PALETTES["neon"][1])
v.scene(2.0, title, fade_out=0.3)
rep = v.dry_run(6)
assert rep["blank_frames"] == 0 and rep["motion"] > 0 and v.duration == 2.0, rep
print("scene ok")
```
A fight, checked by numbers:
```python
# check: runs
try:
    import PIL
except ImportError:
    raise SystemExit(0)
from lumovideo import Fight, Stick, Video
a, b = Stick("RYU", "#4aa3ff", headband="#ffffff"), Stick("KEN", "#ff5252", weapon="staff")
f = Fight(a, b, stage="dojo", title="ROUND 1")
f.gap(0.3, 90, 1.0)
f.attack("a", "jab", at=1.6)
f.attack("b", "cross", at=2.4, hit=False)
f.dodge("a", at=2.35)
f.attack("a", "round_kick", at=3.4, finisher=True)
f.victory("a", at=5.0)
s = f.summary()
assert s["ko"] == "KEN" and s["hp"][1] == 0 and s["hits"][0] == 2 and s["missed"][1] == 1, s
v = Video(1280, 720)
v.add(f)
assert v.dry_run(5)["blank_frames"] == 0
auto = Fight(Stick("A"), Stick("B", "#ff5252"), stage="arena").auto(duration=12, winner="b", seed=3).summary()
assert auto["ko"] == "A" and auto["hp"][0] == 0 and auto["hp"][1] > 0, auto
print("fight ok", s["duration"], auto["duration"])
```
Sound, written to a WAV (no ffmpeg needed):
```python
# check: runs
import os, tempfile, wave
from lumovideo import Mixer, sfx, music
m = Mixer(3.0)
m.add(sfx.punch(), at=0.5, vol=0.9, pan=-0.3)
m.add(sfx.ko(), at=1.2)
m.add(music.beat(120, 2, "chill"), at=0.0, vol=0.4)
path = os.path.join(tempfile.mkdtemp(), "mix.wav")
m.save(path, length=3.0)
w = wave.open(path)
assert w.getnchannels() == 2 and abs(w.getnframes() / w.getframerate() - 3.0) < 0.01
print("sound ok")
```
