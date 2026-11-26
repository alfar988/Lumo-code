# Media for the README

| File | What it is | Made with |
|---|---|---|
| `demo-terminal.gif` | A real Lumo Code session in the terminal: request, starter template, edit (as a diff), render, automatic check | Lumo's own interface in a pseudo terminal, recorded with a scripted stand-in for the model so it repeats exactly (the interface, tools, template and video are real) |
| `hero.mp4` / `hero.gif` | "Describe it. Lumo builds it. Checks it. Fixes it." | `templates/video-kinetic-text.py` |
| `lumo-promo.mp4` / `.gif` | The Lumo Code promo | `templates/video-promo.py` |
| `install-tutorial.mp4` / `.gif` | The three install commands, typed out | `templates/video-tutorial.py` |
| `by-the-numbers.mp4` / `.gif` | The 37 starters by kind (counted from `templates/manifest.json`) | `templates/video-data-chart.py` |
| `science.mp4` / `.gif` | Bubble sort, orbits and two waves adding up | `templates/video-science.py` |
| `countdown.mp4` / `.gif` | A countdown with fireworks | `templates/video-countdown.py` |

The scripts that rendered the videos are in `src/`. Rebuild one from the Lumo folder (needs Pillow and ffmpeg):

```bash
LUMO_VIDEO_QUALITY=standard LUMO_VIDEO_OUT=assets/media/lumo-promo.mp4 python assets/media/src/lumo_promo.py
assets/media/make_gif.sh assets/media/lumo-promo.mp4 assets/media/lumo-promo.gif 400 8 64
```

`python assets/media/src/<name>.py --selftest` checks a script without ffmpeg. The MP4s are 854x480 at 60 fps with sound (H.264 + AAC); the GIFs are silent previews.
