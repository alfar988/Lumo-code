"""Startup banner: LUMO in solid colour blocks and one line with the name and version.

The blocks are background-coloured spaces, not block glyphs. On some phones the font leaves thin seams between block glyphs (the letters came out
striped); a background colour is filled by the terminal itself and has no seams. Without colour the letters are drawn with full-block characters.
Color is used only when the terminal supports it (NO_COLOR is respected).
"""

import os
import sys

from lumo.config import VERSION
from lumo.ui import bold, dim, USE_COLOR, vlen

STOPS = ((110, 231, 255), (130, 170, 255), (176, 148, 255))     # cyan, blue, violet
STYLES = ("bold", "mini")
STYLE_ALIASES = {"aurora": "bold", "beam": "bold", "thin": "bold", "emblem": "bold", "shadow": "bold", "none": "mini"}


def _truecolor():
    if os.environ.get("LUMO_COLOR", "").lower() in ("256", "8bit"):
        return False
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") or os.environ.get("LUMO_COLOR", "").lower() in ("truecolor", "24bit"):
        return True
    # Termux and most phone terminals draw 24-bit color even when they do not announce it
    return bool(os.environ.get("TERMUX_VERSION")) or "com.termux" in (os.environ.get("PREFIX", "") + os.environ.get("HOME", ""))


TRUECOLOR = _truecolor()


def _utf8():
    enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    return enc.startswith("utf8")


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _gradient(t):
    t = min(max(t, 0.0), 1.0) * (len(STOPS) - 1)
    i = min(int(t), len(STOPS) - 2)
    return _lerp(STOPS[i], STOPS[i + 1], t - i)


def _to256(rgb):
    r, g, b = rgb
    cube = [0, 95, 135, 175, 215, 255]

    def near(v):
        return min(range(6), key=lambda i: abs(cube[i] - v))
    ri, gi, bi = near(r), near(g), near(b)
    cube_rgb = (cube[ri], cube[gi], cube[bi])
    gray = round((r + g + b) / 3.0)
    gi2 = max(0, min(23, int(round((gray - 8) / 10.0))))
    gray_rgb = (8 + 10 * gi2,) * 3
    dist = lambda p: sum((p[i] - rgb[i]) ** 2 for i in range(3))
    return 232 + gi2 if dist(gray_rgb) < dist(cube_rgb) else 16 + 36 * ri + 6 * gi + bi


def _bg(rgb):
    return "\033[48;2;%d;%d;%dm" % rgb if TRUECOLOR else "\033[48;5;%dm" % _to256(rgb)


def _lift(rgb, k):
    return tuple(int(v + (255 - v) * k) for v in rgb)


SLAB = {  # 6 x 7 pixels per letter (the M is 7 wide)
    "L": ["##....", "##....", "##....", "##....", "##....", "##....", "######"],
    "U": ["##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
    "M": ["##...##", "###.###", "#######", "##.#.##", "##...##", "##...##", "##...##"],
    "O": [".####.", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
}
WORD = "LUMO"


def logo_rows(cell=2):
    """The wordmark as 7 text rows. Each pixel is `cell` spaces with a background colour, cyan to violet across the word and a little lighter at the top."""
    cols = []
    for i, ch in enumerate(WORD):
        cols.append(SLAB[ch])
        if i < len(WORD) - 1:
            cols.append(["."] * 7)                                   # one empty pixel column between the letters
    grid = ["".join(c[r] for c in cols) for r in range(7)]
    w = len(grid[0])
    plain = not USE_COLOR or not _utf8()
    rows = []
    for r, line in enumerate(grid):
        cells = []
        for x, ch in enumerate(line):
            if ch != "#":
                cells.append(" " * cell)
            elif plain:
                cells.append(("█" if _utf8() else "#") * cell)
            else:
                cells.append(_bg(_lift(_gradient(x / float(max(1, w - 1))), 0.22 * (1.0 - r / 6.0))) + " " * cell + "\033[0m")
        rows.append("".join(cells))
    return rows


def header_lines(width, style="bold"):
    """Logo and one line with name and version. Each line starts with two spaces and fits `width` columns."""
    style = STYLE_ALIASES.get(style, style)
    name = "  " + bold("Lumo Code") + dim("  v" + VERSION + "  ·  /help")
    if vlen(name) > width:
        name = "  " + bold("Lumo Code") + dim("  v" + VERSION)
    if vlen(name) > width:
        name = "  " + bold("Lumo Code")
    if style == "mini":
        return [name]
    cell = 2 if width >= 58 else 1 if width >= 31 else 0
    if not cell:
        return [name]
    return ["  " + r for r in logo_rows(cell)] + ["", name]


def print_header(out, width, style="bold"):
    for line in header_lines(width, style):
        out(line)
