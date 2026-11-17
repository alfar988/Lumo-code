# Changelog

## [1.12.0] - 2026-11-17

### Added
- **`/multiagent test`**: a real check of the whole multi-agent machinery against your real provider, about 4 requests. (A) does OpenRouter accept the `openrouter:subagent` server tool for your smart model (status, worker model, the answer, usage fields), (B) can the light model read real files through the local worker, (C) can it condense an error. Prints PASS/FAIL lines with the reason and saves them in `history/multiagent-test.txt`, so a failure can be copied and sent.
- **A request budget for the worker.** Every worker request counts toward the daily limit of a free model, so: at most 3 worker jobs and 8 worker requests per task (`/multiagent budget jobs|reqs|digest|low <n>`, `/multiagent budget reset`), at most 6 model turns per job (the worker is told to batch its tools), identical `extract` jobs are answered from a session cache until a file changes (tests are never cached), and the end-of-task line shows `N req (worker M)`. `/multiagent status` shows the budget, this task's use and the free requests left today.
- **Automatic pause.** When a free smart model has 10 or fewer requests left today, the worker stops by itself: `delegate` disappears from the tool list, the server tool and the multi-agent prompt are left out, you are told once, and everything resumes when the limit resets (00:00 UTC).

### Changed
- **Error digests are rarer.** Only failures with at least 3500 characters and 30 lines are condensed by the light model (before: 1800 characters), the same error is condensed once, at most 2 per task.
- **Big battles render much faster (lumovideo 1.3.1).** A sound is now synthesised once per variant instead of once per shot: an 86-actor, 360-shot battle compiled in 54 s and now takes about 5 s, with identical sound.

## [1.11.2] - 2026-11-16

### Fixed
- **A greeting no longer goes back to old work.** A ping or greeting ("woii", "halo", "p", "?", "wkwk", "kamu siapa?") is answered in one or two friendly sentences with no tools at all. Before, the restored conversation made the model carry on with the old task and it ran `pkg search pillow pyarrow protobuf pydeck altair`.
- **Nothing is installed unless asked.** Package managers (`pkg`, `apt`, `pip`, `python -m pip`, `npm`, `yarn`, `pnpm`, `cargo`, `gem` ... for install, search, update, upgrade, remove) are skipped with an explanation unless the message asks for it ("install", "pasang", "pip", "dependencies" ...) or a program that the user asked for stopped on a missing module in this very turn. A greeting never installs anything.
- **"Unfinished work found in history" no longer resumes by default.** The question is now `Enter = no, a new start · y = yes`; work older than 24 hours is not even offered (`/resume` still goes back to it), and a finished conversation is only continued automatically within 3 hours of the last message (`auto_resume_hours`, `resume_ask_hours` in the config).

### Changed
- **A clear, crisp logo.** The ring emblem was too low-resolution and looked blurry on a phone. The default banner is now a big bold `LUMO` in solid rounded letters (half blocks, hard edges, aurora gradient), a beam of light with a gold spark, `C O D E` with the tagline, and the version. Styles: `/banner bold` (default), `thin` (thin double-line letters), `emblem` (the ring), `shadow` (shadow letters, 41+ columns), `mini` (one line).

## [1.11.1] - 2026-11-15

### Changed
- **A new banner, not just new colors.** The startup screen is now an emblem (a glowing ring with a four-point star and a small gold satellite, painted two pixels per text cell) next to a letter-spaced `L U M O  C O D E` title, a gradient rule, the tagline and the version, followed by a session card with a rounded frame whose color flows from cyan to rose. It adapts to the screen: a 16 px emblem beside the title from 42 columns, 12 px from 38, 10 px from 36, and the emblem above the title below that, so a phone in portrait gets the new look too (the old chunky logo only showed up on narrow screens before). Termux is recognised as a 24-bit color terminal even when `COLORTERM` is not set (`LUMO_COLOR=256` forces 256 colors). The lines appear one after the other when the terminal is interactive (`/banner anim off`).
- `/banner [aurora|shadow|mini]` shows the banner again and remembers the style (`shadow` is the big shadow-lettered LUMO for 41+ columns, `mini` is one line).
- Multi-agent mode keeps the coder strong: when it is switched on (or at the first request) a smart model that is the random router, or weaker than the worker, is replaced by the best coding model available (`/multiagent smart [id|n|auto]` chooses by hand; a model you picked yourself is never replaced unless the worker outranks it). The system prompt gets a "Code quality" standard (design the edge cases first, complete files without placeholders, verify and run, delegate big test runs, fix the root cause, re-read before finishing; the worker never writes code) and the `code-quality-skill` is loaded for build and task requests.

## [1.11.0] - 2026-11-15

### Added
- **Multi-agent mode** (`/multiagent`, or `--multiagent` at start). A smart model (the one chosen with `/model`) plans, writes code, answers and repairs errors; a light worker model unpacks and reads files, runs tests and condenses errors. Two links connect them: the OpenRouter server tool `openrouter:subagent` (one entry in the request's `tools` array, the worker model in `parameters`) and a local `delegate` tool (`role=extract` or `role=test`) that works on your workspace with a small read-only toolset. `/multiagent worker [id|n|auto]` picks the worker (automatic: a lighter model of the same provider), `/multiagent server on|off` switches the server tool. When OpenRouter refuses the server tool, Lumo drops it for the session and carries on with `delegate`. A failing check with long output is read by the light model first (digest plus raw tail).
- **Scope guard.** Questions, small talk, research and new builds no longer start by listing folders or reading files: reading tools answer "not needed" unless the message points at the workspace (a file, folder, path, `@file`, "fix", "continue" ...). The planning prompt no longer scans the workspace on its own.
- **New banner.** Shadow-lettered LUMO with an aurora gradient and a glint, a rounded session card, and a multi-agent row; three logo sizes for narrow phones.

- **Videos you can follow (lumovideo 1.3).** The automatic `Show` camera frames the action (heroes outrank a crowd; groups are closed in on; look-ahead smoothing), `Show.focus(...)` and `Show.camera_auto(...)` direct it, figures have a rim light, and the render report warns when shots, hits or explosions happen outside the picture or no character is in view. The soldiers-and-zombies template no longer starts the horde 1400 px away (shots at invisible targets) and no longer pins a fixed camera; the story template uses the automatic camera. `video-skill` adds "stay on the request and make it connect" and a five-line storyboard.

### Changed
- The system prompt describes a modest, general AI agent (not a coding project machine): plain tone, honest about what it does not know, no bragging, files stay untouched unless the request is about them.
- Small talk ("hi", "thanks", "who are you") is answered in Q&A mode.
- The earlier-conversations note says plainly that it is background and must not be opened unprompted.

## [1.10.0] - 2026-11-12

### Added
- **Any kind of video.** The video skill now says plainly that every video can be built (stories, characters, battles, explainers, promos, tutorials, slideshows, data stories, trailers, 3D scenes) and that templates are only starting points. New templates: `video-soldier-zombies`, `video-3d-fight`, `video-3d-scene`, `video-story`.
- **Your own moves.** `define_pose(name, base, **angles)` and `define_move(name, keys, hit=...)` invent poses, animations and attacks that work in `Fight`, `Actor.play` and `Figure3D.play`; validation explains every mistake. Twenty built-in attacks (new: palm strike, side kick, low kick, headbutt, shoulder charge, dropkick, hammer fist, flying knee) and ten gestures and actions (shoot, reload, throw, wave, cheer, point, salute, surrender, zombie bite), more than seventy poses, eight gaits (zombie, march, sneak, limp, rifle, sprint ...).
- **Actor and Show.** Stickmen for any 2D scene: walk in any gait, play any move or pose, speak in captions, carry and fire rifles and pistols (tracers, muzzle flash, shells, hit sparks, hit points, falling), zombies, explosions, camera path, sound.
- **Real 3D.** `Scene3D` (perspective camera, flat lighting, fog, shadows, depth sorting, boxes, spheres, cylinders, cones, labels, glows), `Figure3D` (a 3D stick figure that uses the same poses, moves and gaits, yours included) and `Scene3D.from_fight(fight)`, which shows a 2D fight's choreography in 3D with a moving camera.
- **No more guessing.** `video_api` tool and `python lumovideo.py --api [topic]` print the real names from the live library, with complete example scripts; every unknown name or attribute raises an error with the closest real names and the full list; a failed render points the model to `video_api`.
- **Memory across restarts.** Lumo restores the last conversation of a workspace when it starts (also after it finished normally, not only after an error), keeps a never-compacted index of every request (`history/requests.md`) that is part of every prompt, and tells the model where to search the older chat. `/remember on|off` switches it; `/clear` starts a new topic.

### Fixed
- A render that failed half-way left ffmpeg running; it is stopped now.

## [1.9.0] - 2026-11-10

### Added
- **Smoother video.** `standard` quality now renders at 60 fps (draft 24); scripts that ask for 30 fps or less get motion blur automatically (`Video(..., blur=N)` or `LUMO_VIDEO_BLUR` to choose); frames are drawn on up to four CPU cores at once (`LUMO_VIDEO_WORKERS=1` disables it; a script with hidden state between frames is detected and drawn on one core). A parallel render is byte-identical to a single-core one.
- **Better fights.** Every pose change is blended from the pose the body really had (no more snapping between moves), twelve attacks (new: hook, elbow, knee, axe kick, superman punch), backflip dodge (`dodge(..., style="flip")`), knock-back on hard hits, hit flash, dust, a fading streak behind the striking hand or foot, camera punch-in on hard hits, footwork (`step`), and a new director: flurries, trades of blows, blocks, dodges, counters, taunts and jumps, fitted to the requested length (`auto(pace=...)`). Stages now have drifting dust, fireflies, embers and camera flashes.
- **Over 80 synthesised sound effects** in eleven families (new: weapons and creatures, for example `gunshot`, `reload`, `groan`, `zombie_death`) (every call sounds different; `sfx.names()`, `v.sfx("punch", 1.5)`), footsteps per surface, optional voices (`Fight(voices=True)`), a reverb, filters and echo toolbox, and a faster mixer.
- **Real sounds from the internet.** New `find_sound` tool and `sfx.net()` / `find_sounds()` / `fetch_sound()` / `load_sound()` / `sfx.file()` in lumovideo: free CC0 and CC-BY recordings from Openverse (Freesound too with a `FREESOUND_API_KEY` secret), https only, private addresses refused, cached in `sounds/` with `CREDITS.txt`, synthesised fallback when offline. `Fight.use_sounds(...)` and `Fight.use_internet_sounds()` use them for hits and steps.
- **How to play.** New `/play [video] [--gallery]` command; the render result and the script's own output now list the exact commands (`termux-open`, copy to the Gallery with `termux-setup-storage`).
- **Daily free-model limit.** The OpenRouter limit message now says whose limit it is (the account's, not Lumo's, and shared by every `:free` model), when it resets in the phone's own clock, and the ways out; when `/rotate` is on and another provider already has a saved key and a chosen model, Lumo continues there automatically instead of stopping.

### Changed
- `video-skill` rewritten around smooth output, varied sound, how to play and using as few requests as possible (templates first). The no-download rule now allows free sound effects with credits, never music, lyrics or footage.

## [1.8.0] - 2026-11-09

### Added
- **2D video with Python.** New `render_video` tool: runs an animation script written with the bundled `lumovideo` library and produces a playable MP4 (H.264 + AAC, faststart) inside the workspace, then probes it and returns checks (blank frames, motion, brightness, sound). `video_info` inspects any video. Both ask permission like `run_python`, stay inside the workspace, and are offered in the strictest limit saver only when the request mentions video.
- `videokit/lumovideo.py`: one file, Pillow + ffmpeg only. Canvas with camera, shake and parallax, easing and keyframes, scenes with ten transitions, synthesised sound effects and music, a stickman rig (30 poses, 20 moves, weapons), a fight director (`Fight.auto` or scripted: blocks, dodges, hit stop, slow-motion K.O., health bars, stages), typewriter, particles, bar chart, subtitles, automatic frame checks, a GIF fallback without ffmpeg and `--check` / `--selftest`.
- New `video-skill` (workflow, defaults, library reference, fight choreography, other video kinds, craft rules, troubleshooting, examples executed by the tests) and three templates: `video-stickman-fight`, `video-explainer`, `video-kinetic-text`.
- Eight new game templates on the engine kit: `game-pong`, `game-shooter`, `game-asteroids`, `game-tetris`, `game-memory`, `game-racing`, `game-platformer`, `game-tower-defense`.
- The prompt tells the model to make a video only when asked and never to add extra videos, GIFs, music or files.

### Changed
- The engine kit is now version 2: on-screen buttons built from `CONFIG.controls` (`dpad`, `lr`, `lr-action`, `action`, `stick`, `none` or custom buttons), a touch stick, edge-triggered keys (`pressed`), particles, floating text, screen shake, flash, named sound effects, saved mute setting, `swipe()`, helper maths, a live region for screen readers, focus on the overlay button and protection against a key press and a click both starting the game twice. A frame error no longer stops the loop.
- `game-snake`, `game-breakout`, `game-runner` and `game-flappy` were rebuilt on it: timed bonus food, power-ups and level patterns, duck and flying obstacles with coins and parallax, pipes with caps and moving pipes.
- The template list in the system prompt is shorter (default file and the usual variables are stated once), which saves tokens on every request even with 27 templates.

## [1.7.0] - 2026-11-07

### Added
- Four new game templates built on one shared engine kit (canvas scaling, clamped time step, keyboard, pointer and on-screen buttons, HUD, start, pause and game-over screens, guarded best score, optional sound): `game-snake`, `game-breakout`, `game-runner` and `game-flappy`.
- The Node harness now plays every template that uses the kit (presses keys, drags, plays until game over, restarts, pauses) and fails on errors or NaN values, and the page check runs for every shipped HTML template instead of a fixed list.

## [1.6.0] - 2026-11-07

### Added
- A second hidden limit saver for the strictest case. It is not listed in `/help`, in Tab completion or in this README. The existing one keeps its name and its balanced behavior (level 1). The new one is the maximum level (level 2): everything level 1 does, with smaller limits, and it also shortens the skill and template lists in the prompt, cuts notes and project text to under half, shortens tool descriptions, leaves out rarely used tools unless the request mentions what they do, archives old history by itself the way `/compact` does (no model request), plans without web research, and asks the model for short answers and as few tool calls as possible. On a typical build request each request is about 30 percent smaller before any history (measured: 16.4k to 11.2k estimated tokens). Error fixing, automatic verification, the template check and the safety rules stay on at every level.
- The saved choice is `false`, `true` (level 1) or `2` (level 2) in `config.json`; older configs keep working.

## [1.5.0] - 2026-11-07

### Added
- `/compact` now archives the older part of the conversation. Everything except the newest 15 messages is written to `history/archive/compact-<time>.md` and removed from the history that is sent to the model, so every later request is smaller and the key reaches its limit later. Nothing is deleted: the archive holds the full text and `history/transcript.md` keeps the session log. No model request is used, so it works when the key is rate-limited, and if the archive cannot be written nothing is removed. A short note takes the place of the archived messages: it names the archive and repeats the first request, the last request before the cut and the current task.
- `/compact summary` keeps the earlier behavior, where the model writes a summary of the earlier conversation. Automatic compaction is unchanged.

## [1.4.0] - 2026-11-06

### Changed
- The project is now called Lumo Code (it was Axion Code). The Python package is `lumo`, settings live in `~/.lumo`, the project file is `LUMO.md` and the environment variables start with `LUMO_`. Existing installs keep working: `AXION_*` / `AXON_*` variables, `~/.axion` (copied once into `~/.lumo`, the old folder stays) and `AXION.md` are still read.
- Startup shows a new LUMO wordmark with a color gradient (two sizes for narrow phone screens, plain ASCII fallback, no color when `NO_COLOR` is set). `assets/lumo-banner.svg` is the same logo for the README.
- The six imported skills keep their text; only the assistant's name changed from Axion AI to Lumo AI, and their checksums in the tests were updated.
- Example projects in the guides and the README no longer use the playful bunny theme.

### Added
- All 25 built-in guides were extended. Each now opens with "Quick rules (read first)" and a safety note written for that topic, and ends with good and bad examples, common mistakes with fixes, and a checklist. The runnable examples are executed by the test suite.
- A new guide, `safety-skill`, with refusal and jailbreak examples (good and bad answers), prompt-injection handling and a decision test for doubtful requests.
- Safety layers: `prompts/safety-rules.md` is part of every prompt (refusals, jailbreak tricks, prompt injection, secrets), `skills/safety-skill.md` explains how to apply it with good and bad examples, and `lumo/guard.py` refuses blatant requests for malware, fraud tools or weapons before any model request is spent. Defensive and educational wording passes.
- A hidden limit saver for rate-limited keys. It is not listed in `/help`, in Tab completion or in this README.

## [1.3.0] - 2026-11-05

### Added
- More AI providers: Anthropic (native Messages API), xAI (Grok), OpenAI, Google Gemini, Groq, Mistral, DeepSeek, Together, Cerebras, Fireworks, NVIDIA NIM, Ollama, LM Studio and any OpenAI-compatible URL. Each provider has its own key and remembered model. `/provider`, `/key [provider]` and `--provider` manage them.
- `/checklimit` shows the remaining allowance: credits, free daily quota and rate limit for OpenRouter, and rate-limit headers for the other providers. `/checklimit probe` reads them with one small request.
- The model list is refreshed in the background every 12 hours and sorted by estimated capability. Offline, the last list is kept.
- Plans carry acceptance criteria, risks, assumptions, out-of-scope items and a check for every step. A plan check reports features that no step mentions.
- `NOTICE` file.

### Changed
- The AI chooses skills itself with `use_skill` (several names at once). `/skill mode auto` restores automatic selection.
- The license is now Apache-2.0 (was MIT): explicit patent grant, notice preservation and no trademark grant. Copies released earlier under MIT stay under MIT.
- Question-and-answer mode and the planning prompt were rewritten; `PLAN_MAX_STEPS` is 12.
- Models that reject `max_tokens` or `temperature` (newer OpenAI models) are detected once and remembered.
- Fallback models are on by default only for OpenRouter's free models; paid providers switch only when `/rotate` is on.

## [1.2.0] - 2026-11-01

### Added
- `reasoning-skill` for hard questions: restate, choose a method, compute and cross-check instead of guessing, and answer in a short fixed shape. Runnable examples cover exact arithmetic, enumeration and seeded simulation.
- `algorithms-skill`: constraints to complexity target to pattern, brute force first, a stress-test helper that shrinks failing inputs, and reference code for binary search on the answer, sliding window, prefix sums, Dijkstra, BFS, union-find, topological sort, dynamic programming, intervals and backtracking. `tests/test_skill_algorithms.py` cross-checks every function against brute force.
- `scripts/page_check.js` loads an HTML page in a stub browser at portrait and landscape sizes and reports exceptions, canvas size and draw calls per frame, so a blank or frozen screen is found before the user sees it.
- Question-and-answer mode can use `run_python` for calculations and brute-force checks. It asks for approval as usual and is told never to change files.

### Changed
- Skills, templates and prompts no longer demand extra features. The "at least two mechanics beyond the template" lists, the "minimum bar" in `game-skill` and the planning rule for features beyond a template are replaced by rules that follow the request: adapt the template to what the user described and add nothing they did not ask for.
- `code-quality-skill` opens with a work order (read first, list requirements, pick examples, smallest design, small steps, review the diff) and checks every requirement against evidence.
- `debug-skill` covers empty canvases, bugs that appear only in landscape, smeared text, wrong results without errors and regressions.
- `game-skill` has a first-frame checklist. `design-skill` keeps small edits small and keeps text crisp.

## [1.1.1] - 2026-11-01

### Fixed
- The agent no longer works on files outside the current request. The automatic UI review used to fall back to every HTML page in the workspace when the request had changed none, so an unrelated request could end with edits to an old page. Automatic checks now look only at files the request created or changed, and the UI review runs for build requests only.
- The plan, todo list and automatic instructions of earlier work no longer carry over to a new request, and skills picked for earlier work are not reused. `continue`, `lanjut` and `/resume` still resume unfinished work, and `/resume` no longer starts a new plan.
- The type of files in the workspace no longer selects a skill on its own.
- The verification header is not printed when only notes or data files changed.

### Changed
- The prompts state the current request and a scope rule: leave other files alone, create only the files the task needs, keep new files inside the workspace, and report unrelated problems instead of fixing them.
- Saved notes are marked as reference material that may belong to earlier work.

### Added
- `tests/test_scope.py`: regression tests, including a session against a fake server that reproduces the reported behavior.

## [1.1.0] - 2026-10-30

### Added
- Multi-provider web search with automatic fallback, caching and rank fusion (`web_search`), kinds for news, code, Q&A, docs, packages, papers, wiki and discussion, and optional Brave, Tavily, Serper and SearXNG backends.
- `deep_research`: several queries in parallel, pages read in parallel, matching passages returned with dates and source URLs.
- `package_info`: latest version, release date, requirements and install command from PyPI, npm and crates.io.
- `web_fetch` accepts several URLs and reads them in parallel; independent web lookups in one model response run in parallel.
- Lessons that persist between sessions (`learn`, `recall`, `/lessons`) and agent-written skills (`create_skill`, always approved by the user). After a turn that fixed an error the agent is asked once whether anything is worth keeping.
- Commands `/search`, `/dig` and `/lessons`.
- Twelve skills with runnable examples: research, testing, security, database, git, javascript, command-line tools, scraping, bots, performance, documentation, self-improvement.
- Eight templates: game-puzzle, dashboard, docs-site, api-python, api-node, cli-python, bot-telegram, scraper-python.
- Tests for search providers, lessons, learned skills, skill examples and code templates.

### Changed
- Prompts: neutral wording, an explicit research protocol, a debugging protocol and a learning step; the agent no longer adds self-promotion to what it generates.
- The startup banner is a plain header; `/abilities` is now `What Lumo Code can do`.
- Limit per user message raised from 40 to 60 steps.
- Template variables are escaped for string literals in code templates.
- External skills can declare `keywords:` in their front matter for routing.

### Fixed
- Compressed responses are decompressed with an output limit (a small download could expand without bound).
- Page text is decoded with the charset from the `<meta>` tag when the HTTP header has none.
- Timeouts and HTTP 429/5xx responses are retried once for GET requests.
- A search engine answering with an HTTP error was treated as "no results".
- Leftover non-English labels in the website audit output.
- The OpenRouter referer pointed to a repository name that does not exist.

## [1.0.0]

First public version.
