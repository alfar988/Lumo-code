#!/bin/sh
# Turn an MP4 into a small, looping GIF preview for the README (GIFs are silent; the MP4 keeps its sound).
# Usage: assets/media/make_gif.sh input.mp4 output.gif [width=400] [fps=10] [colors=80]
set -e
in="$1"; out="$2"; width="${3:-400}"; fps="${4:-10}"; colors="${5:-80}"
[ -n "$in" ] && [ -n "$out" ] || { echo "usage: $0 input.mp4 output.gif [width] [fps] [colors]" >&2; exit 2; }
ffmpeg -v error -y -i "$in" -vf "fps=$fps,scale=$width:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=$colors:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" -loop 0 "$out"
