<p align="center"><img src="assets/lumo-banner.svg" alt="Lumo Code: AI coding agent for the terminal" width="720"></p>

# Lumo Code

Lumo Code is an AI coding agent for the terminal. You describe what you want in plain language, and it plans the work, writes the files, runs commands, checks its own result and fixes what fails. It talks to [OpenRouter](https://openrouter.ai), so it works with the free models there, and it needs nothing beyond the Python standard library.

It was built to run well in Termux on a phone (narrow output, no heavy dependencies), and it runs the same on any Linux machine or macOS.

## What it does

- **Builds things end to end:** games (2D canvas and 3D Three.js), websites, web apps, APIs, bots, scripts.
- **Starts from tested templates** instead of improvising an engine: thirty-one starters (2D, 3D, puzzle, snake, breakout, runner, flappy, pong, space shooter, asteroids, falling blocks, memory, racing, platformer and tower-defense games; stickman fight, 3D fight, soldiers-vs-zombies, story, 3D scene, explainer and kinetic-text videos; landing page, app shell, dashboard, documentation site, Python and Node JSON APIs, command-line tool, Telegram bot, scraper). The code starters carry a self test.
- **Makes any video with Python, 2D or 3D:** a stickman fight, soldiers against zombies, a story, an explainer, a promo, a tutorial, kinetic text, a chart, a slideshow, a 3D scene. The agent picks `video-skill`, writes an animation script with the bundled `lumovideo` library (templates are only starting points) and turns it into a playable MP4 with sound in your workspace. It can invent its own poses, moves and attacks, and it looks names up with the `video_api` tool instead of guessing them. It makes no video unless you ask for one.
- **Researches the web:** searches through several providers with automatic fallback (web, news, code, Q&A, docs, packages, papers), reads pages in parallel, cites sources and looks up exact package versions. There is no cap on the number of searches.
- **Learns from its work:** after it fixes a non-obvious error it can save a lesson, applies relevant lessons in later sessions, and can write a new skill for a procedure it expects to repeat (it asks first). You can review and delete everything with `/lessons`.
- **Checks its own work:** syntax, undefined functions and variables, broken HTML, and a static UI review (responsive layout, accessibility, WCAG color contrast, generic "AI look") before it says it is done.
- **Repairs itself:** when a command or check fails it reads the error, applies the likely fix (install the module, change the port, correct the path) and reruns, without waiting for you.
- **Uses skills:** 33 guides with working code examples, good and bad examples and troubleshooting steps, chosen for each request.
- **Copes with unreliable free models:** automatic fallback to other models, rate-limit cooldowns, repair of broken tool-call JSON, recovery from cut-off output.
- **Stays inside your workspace** unless you approve otherwise, and deletes to a recoverable trash.

## Requirements

- Python 3.8 or newer
- git
- An OpenRouter API key (a free account is enough): https://openrouter.ai/keys

There is nothing to `pip install`.

Install the prerequisites if you do not have them:

```bash
# Termux (Android)
pkg update && pkg install python git

# Debian / Ubuntu / Kali
sudo apt update && sudo apt install python3 git

# macOS
brew install python git
```

On Windows use WSL.

## Quick start

```bash
git clone https://github.com/alfar988/Lumo-code.git
cd Lumo-code
python run.py
```

If your system has no `python` command, use `python3 run.py`.

On the first run:

1. Paste your OpenRouter key when asked (the input is hidden). It is checked against OpenRouter and stored in `~/.lumo/config.json` with owner-only permissions. Enter a different key later with `python run.py --setup`.
2. Pick a model from the list of free models that support tool calling (type a number, or press Enter for the first). Change it any time with `/models`.
3. Type a request at the prompt.

```
> build a 2D game for phones where a courier collects parcels and avoids drones
> add a login page and a REST API with SQLite to this project
> why does python app.py crash with a KeyError?
```

For build requests Lumo first researches and writes a plan, then builds in small steps. Before it writes a file or runs a command it asks `[y] yes · [n] no · [a] auto`: `y` allows it once, `n` refuses, `a` stops asking for the rest of the session (inside the workspace only). Leave with `/exit` or Ctrl+D.

### Where files go

Lumo works inside one folder, the workspace. The default is `~/workspace`. Pass a folder to use another:

```bash
python run.py ~/projects/my-game
```

If you start it from another directory, that directory becomes the workspace. Your home folder and the Lumo folder itself fall back to `~/workspace`, so the agent never edits its own source. For web projects `/serve` starts a local preview server.

## Command line options

```
python run.py [workspace] [options]

  -m, --model ID     use a specific OpenRouter model id
  -p, --prompt TEXT  run one request and exit
  -c, --continue     continue the last session
  --auto             approve edits and commands inside the workspace
  --setup            enter the API key again
  --version
```

The key can also come from the `OPENROUTER_API_KEY` environment variable. `LUMO_HOME` changes where settings are stored (default `~/.lumo`).

## Everyday commands

`/help` lists everything. The ones you will use most:

| Command | What it does |
|---|---|
| `/models` | choose a free model |
| `/plan [task]` | research and plan first, then build |
| `/ui` | review and polish the web pages in the workspace |
| `/skills`, `/skill why` | list skills, show why they were picked |
| `/search [kind] <query>` | search the web directly (`news`, `code`, `qa`, `docs`, `packages`, `academic`, `wiki`) |
| `/dig <question>` | research a question across several sources and answer with citations |
| `/lessons` | show, add or delete what Lumo learned; `/lessons off` stops learning |
| `/templates` | list the ready-made starters |
| `/resume` | continue unfinished work (progress is saved after every step) |
| `/remember [on\|off]` | keep the conversation after a restart (on by default; `/clear` starts a new topic) |
| `/play [video] [--gallery]` | watch the newest video, or copy it to your phone's Movies folder |
| `/undo`, `/trash` | revert the last change, restore deleted files |
| `/status` | model, permissions, usage today |
| `/compact` | move the older part of a long conversation to `history/archive/` and keep the newest 15 messages, so each request carries fewer tokens. No model request is used. `/compact summary` has the model write a summary instead |

Also: `!ls` runs a shell command directly, `@file.py` includes a file in your message, and a line containing only `"""` starts and ends a multi-line message.

## How it works

1. **Intent and skills.** Lumo decides whether you asked a question, a task or a build, and picks the skills that fit (for example `game-skill` and `planning-skill` for a game). `/skill why` shows the scores.
2. **Plan.** For builds it researches the web where useful and saves a plan to `history/plan.md`.
3. **Build.** It copies the best template with `use_template`, then adapts it to your request (art, rules, sections and content, and nothing you did not ask for). Lumo compares the result with the template and sends the model back when it is still nearly identical, so a recolored starter is not accepted. Large files are written in parts so no single response is cut off. If a model hits its output limit, the complete part is saved and the model is asked for smaller parts.
4. **Verify.** `verify_files` runs on the files the request created or changed, and `review_ui` on the pages a build request produced. Problems are fed back to the model until they are fixed. Other files in the workspace are left alone. For web pages and games, `node scripts/page_check.js page.html` loads the page in a stub browser at portrait and landscape sizes and reports exceptions and blank canvases (needs Node.js).
5. **Recover.** Errors trigger diagnosis hints and a debug skill. If a model keeps failing or is rate limited, Lumo switches to another one and carries the plan and progress over.

Lumo remembers: the conversation of a workspace is restored when you start it again (also after it finished normally), every request is indexed in `history/requests.md` (never compacted, part of every prompt), and older chat stays searchable in `history/transcript.md` and `history/archive/`. `/remember off` turns it off.

Each request is handled on its own. The plan and the todo list of earlier work do not carry over to a new request, and the automatic checks never open files the request did not touch. Say `continue` (or use `/resume`) to pick up unfinished work.

### Research

`web_search` tries several providers and merges the answers: DuckDuckGo and Bing for general queries, Stack Exchange and GitHub for code, MDN for web docs, npm and PyPI for packages, arXiv and Crossref for papers, Wikipedia, Hacker News, and Google and Bing News feeds. A provider that is blocked or rate limited rests for a few minutes while the others carry on, and results are cached. `deep_research` runs several queries at once, reads the best pages in parallel and returns the passages that match the question with their dates and URLs. `package_info` returns the latest version, release date and install command from PyPI, npm or crates.io. Independent lookups in one response run in parallel.

No account is needed. For better general results you can add a key for Brave Search, Tavily or Serper, or point `SEARXNG_URL` at your own SearXNG instance, either as an environment variable or with `/secret set NAME`. `/search providers` shows which providers are ready and `/search reset` clears the cache and cooldowns.

### Learning

Lessons are short notes such as "On Termux `pip install pillow` needs `pkg install libjpeg-turbo` first". They are stored in `~/.lumo/knowledge/lessons.jsonl`, shown in the system prompt only when they match the current request, and treated as data, not instructions. Text that looks like credentials or like instructions to the model is refused. Skills the agent writes for itself go to `~/.lumo/skills/` after you approve them. `/lessons off` disables the feature.

### Skills

Built in: planning, code quality, video (2D, Python), reasoning (hard questions), algorithms, frontend, design, game, backend, python, debug, environment, android, roblox, research, testing, security, database, git, javascript, command-line tools, scraping, bots, performance, documentation and self-improvement. Six larger reference skills (complex thinking, deep research, game development, memory management, planning, UI/CSS/color) load in parts so a small model's context is not filled up front. The code examples in the guides are executed by the test suite.

Add your own: put `my-skill.md` in `skills/` (optionally register trigger patterns in `skills/manifest.json`), or install one from a GitHub repo with `/skill install URL`.

### Templates

In `templates/`, each with a manifest entry (variables such as title and accent color) and covered by the test suite:

| Template | Contents |
|---|---|
| `game-2d`, `game-3d`, `game-puzzle` | canvas arcade engine, Three.js arena, tile-merging puzzle |
| `game-snake`, `game-breakout`, `game-runner`, `game-flappy` | engine-kit games: particles, screen shake, synthesised sound, power-ups, level patterns, duck and jump, tilting flyer |
| `game-pong`, `game-shooter`, `game-asteroids`, `game-tetris` | AI opponent with rounds, waves and bosses with a touch stick, drift physics with splitting rocks, 7-piece bag with ghost piece and wall kicks |
| `game-memory`, `game-racing`, `game-platformer`, `game-tower-defense` | card matching with timer, traffic racer with nitro, generated platformer levels with coyote time, towers with upgrades and 15 waves |
| `video-stickman-fight`, `video-3d-fight`, `video-soldier-zombies`, `video-story`, `video-3d-scene`, `video-explainer`, `video-kinetic-text` | Python video scripts (lumovideo): 2D or 3D fight, soldiers against zombie waves with rifles and grenades, a dialogue story, a generic 3D world, scenes with chart and typewriter text, one punchy line per scene; selftest without ffmpeg |
| `web-landing`, `web-app` | one-page site, app shell with storage |
| `dashboard` | KPI cards, SVG charts, sortable table, CSV export |
| `docs-site` | markdown pages, search, table of contents |
| `api-python`, `api-node` | JSON REST API with validation and pagination, `--selftest` |
| `cli-python` | subcommands, exit codes, `--json`, embedded tests |
| `bot-telegram` | long-polling bot with a testable router, `--selftest` |
| `scraper-python` | robots.txt, rate limit, cache, CSV/JSON output, `--selftest` |


## support device

Lumo-code can be run on both Android and desktop devices, both 32-bit and 64-bit.


Minimum RAM to run Lumo-code smoothly: 4 GB RAM, 8 GB RAM, 12 GB RAM,

### Videos (2D and 3D, Python)

Ask for a video in plain words ("make a stickman fight video", "a 20 second explainer about recycling", "vertical kinetic text for Reels"). Lumo loads `video-skill`, writes one script in `videos/` that starts with `from lumovideo import *`, runs the `render_video` tool and reads its checks (blank or frozen frames, motion, brightness) before it reports. The result is an MP4 (H.264 + AAC) that plays in any player. Watch it with `/play` (opens the newest video), `termux-open videos/fight.mp4`, or `/play --gallery`, which also copies it into your phone's Movies folder so Gallery, Files, VLC and MX Player show it (needs `termux-setup-storage` once).

- Needs `pkg install ffmpeg python-pillow` on Termux (`sudo apt install ffmpeg python3-pil` on Linux). Lumo tells you the exact command when something is missing and never installs without asking.
- `lumovideo.py` is one file with no other dependency: canvas drawing with camera and parallax, easing and keyframes, scenes with transitions, synthesised sound effects and music, a stickman rig with a fight director (stages, hit stop, slow motion, health bars, K.O.), typewriter text, particles and bar charts. `render_video` copies it next to your script, so `python videos/fight.py` also works alone. `python videos/lumovideo.py --check` shows what your device can do.
- Quality `draft` (fast preview), `standard` (854x480, default), `hd`, `fhd`. Your drawing code never changes between them.
- `video_info` inspects any video file (length, codecs, sound, blank or frozen frames).
- **Smooth by default (lumovideo 1.1).** 60 fps at `standard` quality, motion blur (automatic for scripts that ask for 30 fps or less), several CPU cores drawing frames at once (up to four; `LUMO_VIDEO_WORKERS=1` turns it off), and a stickman rig whose every pose change is blended from the pose the body really had, so fighters never snap between moves. Fights have 12 attacks (jab, cross, hook, elbow, uppercut, knee, front kick, round kick, axe kick, sweep, flying kick, superman punch), flurries, trades of blows, blocks, dodges and backflips, knock-back, hit flash, dust, speed streaks behind strikes and a camera that punches in on hard hits; `auto(pace=...)` makes them calm or frantic.
- **Your own moves and any kind of scene (lumovideo 1.2).** `define_pose(name, base, **angles)` and `define_move(name, keys, hit=...)` invent poses, animations and attacks (20 attacks and over 70 poses are built in); they work in `Fight`, in `Actor` (stickmen for any 2D scene: gaits, captions, rifles and pistols that really shoot, zombies, explosions, camera path) and in 3D. `Scene3D` is real 3D (perspective camera, lighting, fog, shadows, shapes, a 3D stick figure that uses the same poses) and `Scene3D.from_fight(fight)` shows a fight in 3D.
- **No guessing.** The `video_api` tool (or `python lumovideo.py --api moves`) prints the real names and complete example scripts from the live library; every wrong name raises an error with the closest real names.
- **Over 80 sound effects**, each call a little different: fight, movement (footsteps for wood, dirt, grass, gravel, metal, sand, concrete), voices, crowd, cinematic, nature, interface, machine, cartoon, weapon and creature families (`sfx.names()`). Real recordings: the `find_sound` tool saves free CC0 / CC-BY sounds from the internet (Openverse; Freesound too with a `FREESOUND_API_KEY` secret) into `sounds/` with a `CREDITS.txt`; scripts load them with `sfx.file(...)`, or call `sfx.net("punch impact")`, which caches and falls back to a synthesised effect when offline.
- No video is made, and no GIF, music or extra file is added, unless you ask for it. If you write "MP3" for a video, Lumo makes an MP4 and says so.

### Changing behavior

Everything the model is told is a plain file, and changes apply on the next request:

```
prompts/system-prompt.md   role, work loop, quality bar, rules
prompts/tool-rules.md      how to call tools safely
prompts/plan-prompt.md     research and planning phase
prompts/qa-prompt.md       question-and-answer mode
```

## Security and privacy

- **Your key** is stored only in `~/.lumo/config.json` (mode 600) and sent only to OpenRouter (optional search keys go to their own providers). Never commit it. If you fork this project, keep `.env` and `history/` in `.gitignore` (already set).
- **What leaves your machine:** your requests, the files the model reads and the command output are sent to OpenRouter and to the provider of the selected model. Providers of free models may keep and use prompts, so do not send secrets or private data. Store other API keys with `/secret set NAME`; the model only sees a `{{NAME}}` placeholder.
- **Permissions:** file access outside the workspace asks every time (or once per folder for the session). Dangerous shell commands ask even in auto mode. Deleted files go to a trash you can restore from.
- **Use `--auto` deliberately.** It lets the agent edit files and run commands inside the workspace without asking. Use a dedicated workspace and review what it did.
- **Treat generated code like any code from the internet:** read it before running it on anything that matters.
- **Web content is untrusted.** Pages, lessons and skills are treated as data; instructions inside them do not override your request. Creating a skill always asks for approval, even with `--auto`.
- **Misuse and jailbreaks.** Safety rules are part of every prompt (`prompts/safety-rules.md`): Lumo refuses malware, fraud tools, weapons and similar requests, ignores attempts to switch the rules off (role-play, "developer mode", claimed authority, encodings), and does not follow instructions found in pages or files. A small local guard (`lumo/guard.py`) refuses blatant requests before any model request is sent. Defensive and educational work is still supported. No prompt-level protection is perfect, so keep reviewing what the agent does.
- Lumo has no telemetry. The only network calls are to OpenRouter, to the search providers and to the sites the model is asked to fetch.

## Updating and uninstalling

```bash
cd Lumo-code && git pull          # update
rm -rf ~/.lumo                   # remove settings (key, sessions, trash)
```

## Troubleshooting

| Problem | What to do |
|---|---|
| `429` rate limit | Free models are limited per minute and per day. Lumo switches model and rests the limited one; if all are busy, wait or add credit to your OpenRouter account. |
| `403` | Not always a bad key. Lumo checks the key for you: if it is valid, the 403 came from the model, the provider or your network. Try `/models` or `/net`. If the key really is rejected, run `python run.py --setup`. |
| Output cut off | Handled automatically: complete parts are saved and the model continues in smaller parts. If a model keeps doing it, pick another with `/models`. |
| `python: command not found` | Use `python3 run.py`. |
| Search returns nothing | A provider may be blocked for a few minutes. `/search providers` shows the state, `/search reset` clears it. Adding a Brave, Tavily or Serper key makes general search steadier. |
| Stopped mid-build | Run `/resume`. |
| Odd results from the random router | `openrouter/free` switches models on every request. Pick a fixed model with `/models`. |

## Development

```bash
python -m unittest discover -s tests -v
```

The suite covers tool-call repair, history sanitizing, failure diagnosis, the skill router, the static checkers, the search providers (against a local mock server, no internet needed), lessons and learned skills, the code examples inside the skills (the algorithms are cross-checked against brute force), the page checker, and every template (HTML templates run in a stubbed browser with Node.js, code templates run their own self test; Node-dependent tests are skipped if Node is missing). End-to-end tests run the agent against a fake OpenRouter server that reproduces rate limits, 403s, broken JSON and cut-off output.

```
run.py          entry point
lumo/          the program (cli, agent, client, models, skills, verify, tools/ ...)
prompts/        system prompt and rules
skills/         skill guides and manifest.json
templates/      tested starters and manifest.json
scripts/        page_check.js: crash and blank-canvas check for HTML pages (needs Node.js)
tests/          unit, integration and template tests
```

Issues and pull requests are welcome.

## Providers and keys

Lumo Code works with several AI providers. Each provider keeps its own key and its own chosen model.

| Provider | Name for `/provider` | Environment variable |
|---|---|---|
| OpenRouter (free models included) | `openrouter` | `OPENROUTER_API_KEY` |
| Anthropic (Claude) | `anthropic` | `ANTHROPIC_API_KEY` |
| xAI (Grok) | `xai` or `grok` | `XAI_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Google Gemini | `gemini` | `GEMINI_API_KEY` |
| Groq | `groq` | `GROQ_API_KEY` |
| Mistral | `mistral` | `MISTRAL_API_KEY` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` |
| Together AI | `together` | `TOGETHER_API_KEY` |
| Cerebras, Fireworks, NVIDIA NIM | `cerebras`, `fireworks`, `nvidia` | `CEREBRAS_API_KEY`, `FIREWORKS_API_KEY`, `NVIDIA_API_KEY` |
| Ollama, LM Studio (local, no key) | `ollama`, `lmstudio` | none |
| Any OpenAI-compatible server | `custom` | `LUMO_API_KEY` |

`/provider` lists them and switches, `/key [provider]` stores a key, and `python run.py --provider xai` starts with a given provider. When exactly one provider key is found in the environment on the first run, that provider is used. Anthropic is called through its native Messages API; every other provider uses the OpenAI chat-completions format. Paid providers do not switch models on their own unless you turn `/rotate` on.

`/checklimit` shows how much of the allowance is left: credits, the free daily quota and the rate limit for OpenRouter, and the rate-limit headers of the last response for the other providers. `/checklimit probe` reads them with one tiny request. Balances of providers that do not expose them through the API are shown in their console (the link is printed).

The model list of the active provider is refreshed every 12 hours, in the background, and sorted with the most capable models first. The order combines the model family and generation, the size in its name, the context length, the release date and the price, plus how each model performed for you in earlier sessions. It is an estimate, not a benchmark: `/model <n>` or `/model <id>` always wins.

## Skills chosen by the AI

The model decides which skills to load: the system prompt lists every skill in one line, and the model calls `use_skill` for the guides that fit the task. Pin a skill yourself with `/skill use <name>`. `/skill mode auto` brings back the earlier behavior, where Lumo scores the request and loads skills itself.


## License

Apache License 2.0 (see `LICENSE` and `NOTICE`). It grants an explicit patent license, requires the notice to stay with redistributions, and does not grant the right to use the project's name. Versions before 1.3.0 were published under the MIT License. This is a summary, not legal advice.




(coded by alfar988 --- Lumo-code)