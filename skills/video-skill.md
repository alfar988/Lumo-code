---
name: video-skill
description: ANY video made with Python, 2D or 3D (explainers, promos, tutorials, data charts, slideshows, kinetic text, logo intros, countdowns, science animations, stories, trailers, fights, 3D scenes) rendered to a playable MP4 with sound: genre choice, storyboard, the bundled lumovideo library, video_api, render_video, checks and repairs.
---
# Video skill (any 2D or 3D video with Python → MP4)

## Quick rules (read first)
1. Make a video only when the user asked for one (or for an animation they want to watch). Questions, code help, "video game", an HTML `<video>` tag or a video player page are not video requests. Do not add a video, a GIF, music, an intro, credits or extra scenes that nobody asked for.
2. If the user says "MP3" for a video, they mean MP4 (MP3 is audio only). Make the MP4 and say so in one short line.
3. Build everything in Python: one script `videos/<name>.py` that starts with `from lumovideo import *`, then run the `render_video` tool on it. The tool turns the script into a real MP4 (H.264 + AAC, plays in any player) inside the workspace. Do not hand the user frames, or a script to run, unless they asked for the script.
4. Do not interrogate the user. Missing details get the defaults below; say the assumptions in one line. Ask one short question only when the subject itself is unknown ("a video of what?").
5. Read what `render_video` returns (the `checks:` line and every `WARNING:`). Fix the warnings before you say it is done. Finish with the file path, the length, what is in it and how to play it.
6. Draw everything with the library. Sound: use its synthesised effects (over 80, no download); when the user wants real or more varied sound effects, use `find_sound` (free CC0 / CC-BY recordings, credits in `sounds/CREDITS.txt`). Never download songs, music, lyrics, copyrighted characters or footage, and never use a real person's face or voice.
7. Every request is paid for from a daily allowance on free models: start from a template (`use_template`) and change only the settings, write the script in one `write_file`, render once, fix only real warnings. A finished video should take about four requests, not thirty.
8. The library is a toolbox, not a list of templates: ANY video the user describes can be made, whatever the subject (a cooking tutorial, a product promo, a soldier and zombie battle, a love story skit, a 3D city flythrough, a birthday card, a data story, a game trailer). Templates are only starting points for the subjects they name; if none fits, write your own script from the building blocks below. Never say "I can only make fights" and never force a request into the nearest template.
9. Never invent a name. Before you write or fix a script, call `video_api` for the topic you need (`recipes` has complete working scripts; `moves`, `poses`, `actor`, `show`, `fight`, `scene3d`, `canvas`, `sound`, `stages` list the real names) and use exactly what it returns. Do not read `lumovideo.py` line by line: it costs requests and the tool is exact. If something you need does not exist, say so in one line and build it yourself (`define_pose`, `define_move`, Canvas drawing).
10. Stay on the request and make it connect. Everything the user named (characters, weapons, setting, mood, length) must be SEEN in the video, in an order that makes sense (setup, conflict, payoff), and nothing important that they did not name is added. No text-only slides, no counters standing in for a story, no actions without a visible target.
11. The viewer must see the action. `Show` has an automatic camera that keeps the characters in the picture and closes in on the ones who shoot, talk or get hit: do not set `camera_keys` unless you want a path of your own, and use `show.focus(at, dur, who=actor)` for a close-up. Keep the stage compact: both sides of a fight start inside one screen width (about 1000 px apart at most), so every shot has a visible target.
12. Pick the genre from the request (the table below). A fight is one genre among many: never default to one, and never turn a different request (a promo, a tutorial, a chart, a story) into a fight.
13. An error is about one wrong name, value or call, not about the feature. Repair the call (look the name up with `video_api`, write the missing move with `define_move`) and render again. Never delete the sound, camera move, scene, character or effect to make the render pass. If a part still fails after four distinct attempts, keep it in the script, say which part fails and why, and ask whether to drop it.

## Pick the genre first
Decide the genre from the user's words, then start from the matching template or recipe (`use_template("list")` shows all). Every genre below is fully supported; none is the default.
| The user asks for | Genre | Start from | Length and format |
|---|---|---|---|
| explain, teach, "how does X work" | Explainer | `video-explainer` | 20-40 s |
| ad, promo, product, brand, launch, sale | Promo | `video-promo` | 15-30 s, vertical for social |
| tutorial, how to install or use, steps, command demo | Tutorial | `video-tutorial` | 15-45 s |
| chart, statistics, growth, report, results | Data story | `video-data-chart` | 12-25 s |
| quote, motivation, their own words, poem, caption | Kinetic text | `video-kinetic-text` | 8-20 s |
| slideshow, photos, memories, birthday, trip | Slideshow | `video-slideshow` | 3-5 s per picture |
| intro, outro, logo, title card, channel opener | Logo reveal | recipe `logo_reveal` (`video_api recipes`) | 3-6 s |
| countdown, new year, event, launch day | Countdown | `video-countdown` | 8-15 s |
| science, math, physics, algorithm, planets, waves | Science animation | `video-science` | 15-30 s |
| story, skit, dialogue, comedy, cartoon characters | Story | `video-story` (Actor + Show) | 15-40 s |
| soldiers, zombies, battle, shooting, game trailer | Action scene | `video-soldier-zombies` | 12-20 s |
| fight, stickman, martial arts, duel | Fight | `video-stickman-fight`, `video-3d-fight` | 12-16 s |
| 3D, city, flythrough, product spin, camera moves | 3D scene | `video-3d-scene` | 10-20 s |
| landscape, road trip, night city, space, wallpaper, loop | Ambient scene | recipe `road_trip` | 8-20 s |
| music visualizer, beat, equalizer | Beat visual | playbook below | as long as the sound |
| news, headline, timeline, history | Timeline | playbook below | 15-30 s |
| Reels, TikTok, Shorts, story, square post | Format only | any genre with `Video(720, 1280)` or `Video(1000, 1000)` | 15-30 s |
When the request mixes genres (a promo with a short story, a tutorial with a chart), build one video in the main genre and borrow scenes from the others. When no row fits, write your own scenes from the building blocks.

## Defaults (use them, do not ask)
| Missing | Use |
|---|---|
| length | promo 15-30 s, tutorial 15-45 s, explainer 20-40 s, data story 12-25 s, science 15-30 s, countdown 8-15 s, slideshow 3-5 s per picture, title or quote 5-8 s, fight 12-16 s |
| format | 1280x720 landscape; 720x1280 (`Video(720, 1280)`) when the user says TikTok, Reels, Shorts, story or vertical |
| quality | `standard` (854x480, smooth 60 fps, several CPU cores). `draft` (480x270, 24 fps) first when the script is new and over 25 s. `hd` only when asked. Leave `fps` out of `Video(...)`: the quality chooses it |
| sound | hit and whoosh sounds for fights, a soft `ding`/`whoosh` on text reveals. Music only when the user asks for music or a mood |
| text language | the user's language, short lines, readable at phone size |
| names, colours, stage | pick distinct colours (blue vs red) and a fitting stage; use the names the user gave |

## Workflow
1. **Brief** in your head: subject, length, format, style, sound. One line of assumptions to the user.
2. **Storyboard** (anything over 10 s), five lines before any code: setting · cast (look, colour, weapon) · 3-6 beats with seconds, for example `0-2 s title · 2-9 s fight · 9-12 s K.O. and winner` · the last frame · the user's own words you must honour. Check each requested element has a beat; if one has none, add the beat now.
3. **Script**: write the whole `videos/<name>.py` in one `write_file`. When a template fits the subject (`video-explainer`, `video-promo`, `video-tutorial`, `video-data-chart`, `video-kinetic-text`, `video-slideshow`, `video-countdown`, `video-science`, `video-story`, `video-3d-scene`, `video-soldier-zombies`, `video-stickman-fight`, `video-3d-fight`), `use_template` it; when none fits, write the script from the building blocks (`video_api` topic `recipes` has starters) and change names, colours, stage and length.
4. **Render**: `render_video` with `script`. Use `quality: "draft"` for a first pass of a long or new script, then the final render.
5. **Check and fix**: no blank frames, some motion, brightness above 6. A WARNING means a real problem: fix the script and render again. Never re-render without a reason.
6. **Report**: path (for example `videos/fight.mp4`), length, resolution, one sentence on what happens, and HOW TO PLAY it (the render result lists the commands; always pass them on, in the user's language): `termux-open videos/fight.mp4`, or `/play` inside Lumo, or for the Gallery run `termux-setup-storage` once, then `cp videos/fight.mp4 ~/storage/movies/` and open Gallery, Files, VLC or MX Player (`/play --gallery` does the copy).

If `render_video` says ffmpeg or Pillow is missing, run the install command it prints with `run_shell` (the user approves it), then render again. Python 3.8 or newer is enough; numpy is not needed.

## Tools
- `render_video(script, output?, quality?, open?)`: runs the script, encodes the MP4, probes it and returns the checks. `open: true` starts the device player; use it only when the user wants to watch it right now.
- `video_api(topic?)`: the exact names and signatures of the library (and complete example scripts). Call it before using a name you have not seen in this chat.
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

## Building blocks (pick what the video needs)
| the video has | use |
|---|---|
| text, shapes, gradients, images, charts, particles, slideshows, promos, tutorials, lyrics, trailers | `Video` + `v.scene(duration, draw)` with `Canvas` (`video_api canvas`, `components`, `recipes`) |
| people or creatures that walk, talk, gesture, shoot, fall, in any scene | `Actor` + `Show` (`video_api actor`, `show`); guns, zombies, speech captions, explosions, camera path are built in |
| your own move, attack or animation | `define_pose(name, base, **angles)` then `define_move(name, keys, hit=...)`; works in `Fight`, `Actor.play`, and `Figure3D.play` |
| a stickman fight | `Fight` (2D) or `Scene3D.from_fight(fight)` (3D) |
| real 3D: shapes, a moving camera, 3D figures, fog, shadows | `Scene3D` (`video_api scene3d`); heavy, so `Video(1280, 720, fps=30)` and `quality: draft` first |
| sound | `v.sfx(name, at)`, `sfx.*`, `sfx.file`, `sfx.net`, `find_sound`, `music.beat` (`video_api sound`) |
A new move in two lines: `define_pose("hands_up", "guard", rua=165, rfa=175, lua=165, lfa=175)` then `define_move("hooray", [(0, "guard"), (0.25, "hands_up", "out_quad"), (0.9, "hands_up"), (1.2, "guard")])`; play it with `actor.play(2.0, "hooray")`.
Soldiers against zombies is one `Show` with `Actor(weapon="rifle", look="soldier")` and `Actor(look="zombie", hp=2)`; `soldier.shoot(t, target=zed, burst=3)` fires, hits take hp, at 0 the zombie falls; `show.explode(t, x)` blows things up.

## Genre playbooks (structure, blocks, sound, mistakes)
Times are guides. Every scene is a pure function of `t` (no hidden state), text stays inside 10% margins, and each scene shows one idea.

**Explainer (20-40 s).** Hook question 3 s, then 3 to 5 idea scenes of about 5 s (heading, one short line, one moving picture that shows the idea), then a one-line recap 4 s. Blocks: `video-explainer`, `Typewriter`, `BarChart`, shapes moved with `tween`. Sound: a soft `pop` per idea, `whoosh` on transitions, music only when asked. Mistakes: paragraphs on screen, numbers instead of a picture, two ideas in one scene.

**Promo or ad (15-30 s).** The viewer's problem 2-3 s, brand reveal 3 s, two to four benefits (one scene each, a drawn icon, 3-4 s), the offer and ONE call to action 4 s, logo 2 s. Blocks: `video-promo`, `c.poly` icons, `Typewriter`. Sound: `whoosh` on cuts, `pop` per benefit, `coin` or `success` at the offer, quiet `music.beat(120, 8, "epic")` if music is wanted. Mistakes: invented prices, discounts, awards or customer counts (use only what the user gave), many claims, no single call to action, text under 5% of the height.

**Tutorial (15-45 s).** Title that promises the result 3 s, one scene per step (4-6 s: number badge, verb heading, one line, the exact command or UI action typed in a window), recap 3-4 s. Blocks: `video-tutorial`, a window from `c.rect` and three dots, `Typewriter` with a cursor. Sound: soft `click` while typing, `success` when a step ends. Mistakes: steps you did not test, more than 6 steps (split into parts), no pause to show the result of the command.

**Data story (12-25 s).** Title that states the finding 3 s, compared bars 5 s, a trend line 5 s, the one number that matters 4 s. Blocks: `video-data-chart`, `BarChart`, `c.polyline`, count-up `int(v * ease(t / 1.5, "out_cubic"))`. Rules: only the user's numbers (if none, say the numbers are an example), bars start at zero, units on every number, colour-blind safe colours. Sound: `pop` per bar, `success` at the end. Mistakes: pies with many slices, 3D effects, needless decimals, labels under 5% of the height.

**Kinetic text, quote, lyric lines (8-20 s).** One phrase per beat (0.6-1.5 s), the key word bigger or in the accent colour, 4 to 8 phrases, hold the last one 1.5 s. Blocks: `video-kinetic-text`, `Timeline`, alternating `slide_left` and `slide_right`, `scale=ease(t / 0.4, "out_back")`. Sound: `pop` per word, optional `music.beat(100, 4, "chill")`. Rules: the user's own words only; never reproduce songs or poems by others.

**Slideshow (3-5 s per picture).** Title over the first picture 3 s, then each picture 4 s with a slow zoom (1.0 to 1.12) and a short caption, a closing line. Blocks: `video-slideshow`, `c.image` (load and resize the picture ONCE outside the draw function), `crossfade` 0.6 s. Rules: only the user's pictures; with none, the template draws colour cards, say so. Sound: quiet `music.beat(84, 8, "chill")` only when asked. Mistakes: stretching (scale to cover, keep the aspect), opening the file every frame.

**Logo reveal, intro, title card (3-6 s).** 0-1 s a ring expands or shapes assemble, 1-2.5 s the name pops in with a glow, 2.5-4 s the tagline fades in, hold 1 s. Blocks: recipe `logo_reveal`, `c.glow`, `ease(..., "out_back")`, `c.circle(outline=...)`. Sound: `riser` into `boom` or `ding`. Mistakes: longer than 6 s, a tiny tagline.

**Countdown or event (8-15 s).** Numbers N to 1, each 1 s with a ring that drains and a pop, then fireworks (`Particles` bursts every 0.4 s) and the big message. Blocks: `video-countdown`. Sound: `click` every second, `explosion` per firework, `cheer`. Mistakes: a number that stays longer or shorter than its second, no pop to mark the change.

**Science, math, algorithm (15-30 s).** Question title 3 s, one scene per idea that shows the PROCESS moving (bars swap, a planet orbits, waves add up) with a label on what moves, takeaway 3 s. Blocks: `video-science`; precompute the steps, then `steps[min(int(t * rate), len(steps) - 1)]`; `math.sin` and `math.cos` for orbits; a trail by drawing earlier times `t - k * 0.04`. Rules: correctness first (assert your own result, for example `last == sorted(data)`), real values, labelled axes and units. Mistakes: an animation that does not follow the real algorithm, state kept between frames.

**Story, skit, dialogue (15-40 s).** Setup (where, who) 3-5 s, conflict (someone wants something) 8-20 s, payoff 3-5 s; every beat visible, speech as captions. Blocks: `video-story`, `Actor`, `Show`, `actor.say`, `show.focus`, `define_move` for your own gestures. Sound: `step` on the floor surface, a quiet `wind` or `rain` bed, `laugh` for comedy. Mistakes: characters talking with nobody in frame, slides of text instead of action.

**Action scene (12-20 s).** One `Show`; `video-soldier-zombies`; `soldier.shoot(t, target=zed, burst=3)`, `show.explode(t, x)`. Keep both sides inside one screen width; leave the automatic camera on.

**3D scene or flythrough (10-20 s).** `video-3d-scene`, `Scene3D` with camera keys; draft first and `fps=30`. Keep it under about 300 shapes; add fog and a ground shadow for depth.

**Ambient or parallax scene (8-20 s).** Recipe `road_trip`; `with c.parallax(0.3):` layers (sky, hills, road, foreground), clouds and stars that drift as `(t * speed) % width` so it loops. Sound: a `wind` or `rain` bed only.

**Beat visual or music visualizer.** `buf = music.beat(bpm, bars, style)` and bars whose height follows the tempo: `h = base + amp * pulse(t + i * 0.07, 2 * 60 / bpm)` with `noise(i * 1.7 + t * 0.5)` for variety, drawn with `c.rect(x, y, w, h, anchor="bl")`, and a `c.glow` that swells on the kick. Length = `bars * 4 * 60 / bpm`. The visual follows the tempo, not a real audio file: say so when the user brings a song, and never download music.

**News, timeline, history (15-30 s).** Title, an axis that draws left to right, events that pop in at their date with a one-line label, the conclusion. Blocks: `Timeline`, `c.line`, `c.circle`, `Typewriter`, `Subtitles`. Rules: facts come from the user or from a source you looked up with `web_search` (name it); never invent dates, quotes or headlines.

**Vertical and square formats.** `Video(720, 1280)` for Reels, Shorts, TikTok and stories, `Video(1000, 1000)` for a square post. Everything is drawn in those logical coordinates: centre on `w / 2`, wrap text with `max_w=w * 0.86`, keep important content in the middle 80% (app bars cover the top and bottom).

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

## What makes it look good
- Readable characters: the library draws a pale rim around figures so dark colours stay visible on dark stages; still pick colours with contrast against the stage, and let the camera close in (the automatic camera zooms to about 1.5x on small groups) so characters fill a quarter to a third of the height.
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
| N of M shots, hits and explosions happen outside the picture | the action is off-screen: remove `camera_keys` (the automatic camera follows the action), start the sides closer together, or add `show.focus(...)` |
| no character is in view for X% of the video | same fix; also check that actors are placed with x between 0 and 1280 when they should be seen |
| ffmpeg or Pillow missing | install as the error says, then render again |
Make small fixes with `edit_file`, not a full rewrite. After the final render, if the length or look is not what was asked, change it once and render again.

## When something fails: repair the call, never the feature
An error names one wrong thing. Find it, fix it, render again.
| Error or warning | Repair |
|---|---|
| unknown sound, move, pose, stage or easing ("did you mean ...") | the message lists the real names: use one, or call `video_api` for the topic; a move that does not exist is written with `define_move` |
| AttributeError or TypeError on a library call | `video_api` for the topic, then fix the argument names and order; fix every other place with the same mistake in the same edit |
| `y1 must be greater than or equal to y0` from `c.rect` | a negative width or height: pass a positive size and choose the anchor (`anchor="bl"` grows a bar upward from its base) |
| text cut off at the edge | `max_w=w * 0.86`, a smaller size, or two lines |
| blank frames or a flat colour | a scene draws nothing at that time: check the scene lengths and the `if` tests on `t` |
| ffmpeg or Pillow missing | run the install command the tool prints, then render again |
| slow render | `quality: "draft"`, fewer shapes per frame, resize big pictures once outside the draw function |
Never delete the sound, the camera move, the scene, the character or the effect that raised the error, never swap it for something weaker without saying so, and never report the video as finished while a warning is open. If a part still fails after four distinct attempts, keep it in the script, tell the user which part fails and why, and ask whether to drop it.

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

Data story: bars, then the one number that counts up (a real chart needs the user's numbers; these are an example).
```python
# check: runs
from lumovideo import *

SERIES = [("2023", 40), ("2024", 62), ("2025", 91)]
v = Video(1280, 720)
chart = BarChart(SERIES, colors=PALETTES["ocean"])

def bars(c, t):
    c.background("#08202b", "#12495c")
    c.text("Users per year", 640, 90, 60, "#ffffff", outline="#000000", outline_w=4)
    chart.draw(c, t, 100, 170, 1080, 430, start=0.3, dur=1.5)

def key(c, t):
    c.background("#08202b", "#12495c")
    n = int(SERIES[-1][1] * ease((t - 0.2) / 1.4, "out_cubic"))
    c.text(str(n), 640, 330, 200, "#ffffff", outline="#000000", outline_w=8, scale=ease(t / 0.4, "out_back"))
    c.text("users in 2025", 640, 470, 44, "#d6edf5")

v.scene(4.0, bars, name="bars")
v.scene(3.0, key, name="key", transition="crossfade", trans_dur=0.4)
rep = v.dry_run(6)
assert rep["blank_frames"] == 0 and rep["motion"] > 0.1, rep
print("data story ok", round(v.duration, 1))
```

Countdown in a square 1000x1000 video, with fireworks:
```python
# check: runs
from lumovideo import *

v = Video(1000, 1000)
cx, cy = 500, 500

def number(n):
    def draw(c, t):
        c.background("#0a0820", "#241a52")
        c.arc(cx, cy, 260, 0, 360, "#2c2760", 16)
        c.arc(cx, cy, 260, -90, -90 + 360 * (1 - t), "#ff7a59", 16)
        c.text(str(n), cx, cy, 340 * (1 + 0.3 * (1 - ease(t / 0.3, "out_cubic"))), "#ffffff", outline="#000000", outline_w=8)
    return draw

for n in (3, 2, 1):
    v.scene(1.0, number(n), name="n%d" % n)

ps = Particles(seed=2)
for k in range(4):
    ps.burst(0.2 + 0.4 * k, 250 + 160 * k, 300, n=40, speed=300, life=1.2, color=PALETTES["sunset"][k], size=7)

def finale(c, t):
    c.background("#0a0820", "#241a52")
    ps.draw(c, t)
    c.text("HAPPY NEW YEAR", cx, cy + 120, 90, "#ffffff", outline="#000000", outline_w=6, scale=ease(t / 0.5, "out_back"), max_w=900)

v.scene(3.0, finale, name="finale")
rep = v.dry_run(6)
assert rep["blank_frames"] == 0 and rep["motion"] > 0.1, rep
print("countdown ok", v.duration)
```

Beat visual: bars that follow the tempo (a pure function of time).
```python
# check: runs
from lumovideo import *

BPM = 120
beat = 60.0 / BPM
v = Video(1280, 720)

def bars(c, t):
    c.background("#0f0a1e", "#2a1458")
    n = 24
    for i in range(n):
        h = 40 + 260 * pulse(t + i * 0.07, beat * 2) * (0.5 + 0.5 * abs(noise(i * 1.7 + t * 0.5)))
        c.rect(90 + i * 47, 600, 34, h, fill=mix(PALETTES["neon"][0], PALETTES["neon"][2], i / n), radius=8, anchor="bl")
    c.glow(640, 600, 420 + 60 * pulse(t, beat), PALETTES["neon"][1], 0.4)

v.scene(4.0, bars, name="visualizer")
v.sound(music.beat(BPM, 2, "epic"), at=0.0, vol=0.4)
rep = v.dry_run(6)
assert rep["blank_frames"] == 0 and rep["motion"] > 0.1, rep
print("visualizer ok")
```
