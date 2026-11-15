"""Startup banner: the LUMO wordmark with a soft aurora gradient, depth shading and a glass highlight, then an info card.

The logo comes in three sizes so it fits a phone terminal: a shadow-lettered one (37 columns, 6 rows), a half-block one (34 columns, 4 rows)
and a compact one (23 columns, 3 rows), plus a plain ASCII version for terminals that cannot show Unicode.
Color is used only when the terminal supports it (NO_COLOR is respected).
"""

import os
import sys

from lumo.config import VERSION
from lumo.ui import ANSI_RE, bold, clip, dim, faint, USE_COLOR, vlen


# Each glyph is a bitmap: '#' = lit pixel. Two pixel rows become one text row (upper half, lower half, full block).
BIG = {   # 8 pixel rows -> 4 text rows, 7 columns per letter
    "L": ["##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######"],
    "U": ["##...##", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####.", "..###.."],
    "M": ["##...##", "###.###", "#######", "##.#.##", "##...##", "##...##", "##...##", "##...##"],
    "O": ["..###..", ".#####.", "##...##", "##...##", "##...##", "##...##", ".#####.", "..###.."],
}
SMALL = {  # 6 pixel rows -> 3 text rows, 5 columns per letter
    "L": ["#....", "#....", "#....", "#....", "#....", "#####"],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", ".###."],
}
SHADOW = {  # box-drawing letters with a built-in shadow: 6 rows, 37 columns for LUMO
    "L": ["██╗     ", "██║     ", "██║     ", "██║     ", "███████╗", "╚══════╝"],
    "U": ["██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "M": ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║", "╚═╝     ╚═╝"],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
}
WORD = "LUMO"
GAP = {"big": 2, "small": 1}

# Aurora: ice cyan, soft blue, violet, a touch of rose. One warm spark (gold) as the single accent.
STOPS = ((110, 231, 255), (118, 166, 255), (176, 148, 255), (240, 150, 214))
SPARK = (255, 212, 121)
TRUECOLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


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


def _fg(rgb, text):
    if not USE_COLOR:
        return text
    code = "38;2;%d;%d;%d" % rgb if TRUECOLOR else "38;5;%d" % _to256(rgb)
    return "\033[" + code + "m" + text + "\033[0m"


def _shade(rgb, k):
    return tuple(max(0, min(255, int(v * k))) for v in rgb)


def _bitmap(size):
    glyphs = BIG if size == "big" else SMALL
    rows = len(glyphs["L"])
    out = ["" for _ in range(rows)]
    for n, ch in enumerate(WORD):
        for r in range(rows):
            out[r] += glyphs[ch][r] + (" " * GAP[size] if n < len(WORD) - 1 else "")
    return out


def _half_blocks(bits):
    """Two bitmap rows -> one text row of upper-half, lower-half and full block characters."""
    text = []
    for r in range(0, len(bits), 2):
        top, bot = bits[r], bits[r + 1]
        text.append("".join("█" if (t == "#" and b == "#") else "▀" if t == "#" else "▄" if b == "#" else " "
                            for t, b in zip(top, bot)))
    return text


def _lift(rgb, k):
    """Brighten toward white by k (0..1)."""
    return tuple(int(v + (255 - v) * k) for v in rgb)


def _shadow_rows():
    rows = ["" for _ in range(6)]
    for ch in WORD:
        for r in range(6):
            rows[r] += SHADOW[ch][r]
    return rows


def _shadow_wordmark():
    rows = _shadow_rows()
    w, h = len(rows[0]), len(rows)
    sheen = w * 0.58                                           # a soft diagonal glint, like light on glass
    lines = []
    for r, row in enumerate(rows):
        cells = []
        for x, ch in enumerate(row):
            if ch == " ":
                cells.append(" ")
                continue
            base = _gradient(x / float(max(1, w - 1)))
            if ch == "█":                                      # the face of the letter: bright, a little darker toward the bottom
                rgb = _shade(base, 1.0 - 0.20 * (r / float(h - 1)))
                glint = max(0.0, 1.0 - abs((x - sheen) - 1.7 * (r - 2)) / 3.2)
                rgb = _lift(rgb, 0.34 * glint)
            else:                                              # the shadow strokes: the same hue, much darker, for depth
                rgb = _shade(base, 0.46)
            cells.append(_fg(rgb, ch))
        lines.append("".join(cells))
    return lines


def wordmark(width):
    """The logo as colored text lines (no indent). Returns [] when the terminal is too narrow."""
    if _utf8() and width >= 41:
        return _shadow_wordmark()
    size = "big" if (width >= 38 and _utf8()) else "small"
    bits = _bitmap(size)
    if width < len(bits[0]) + 2:
        return []
    if not _utf8():
        return ["".join(c if c == " " else "#" for c in row) for row in bits]
    text = _half_blocks(bits)
    w, h = len(text[0]), len(text)
    lines = []
    for r, row in enumerate(text):
        cells = []
        for x, ch in enumerate(row):
            if ch == " ":
                cells.append(" ")
                continue
            rgb = _shade(_gradient(x / float(max(1, w - 1))), 1.0 - 0.16 * (r / float(max(1, h - 1))))
            cells.append(_fg(rgb, ch))
        lines.append("".join(cells))
    return lines


def beam(width):
    """A thin ray of light under the wordmark: bright at the spark, fading to the right."""
    if not _utf8():
        return "-" * width
    parts = [_fg(SPARK, "✦")]
    n = max(4, width - 2)
    for i in range(n):
        t = i / float(max(1, n - 1))
        ch = "━" if t < 0.62 else ("─" if t < 0.86 else "╌")
        parts.append(_fg(_shade(_gradient(t), 1.0 - 0.55 * t), ch))
    return "".join(parts)


TAGLINE = "AI agent for the terminal"


def header_lines(width):
    """Everything above the info card: wordmark, beam, product line. Each line starts with two spaces."""
    mark = wordmark(width)
    lines = []
    if mark:
        lines += ["  " + l for l in mark]
        lines.append("  " + beam(vlen(mark[0])))
        lines.append("")
    title = "  " + bold("Lumo Code") + dim("  v" + VERSION) + faint("  ·  ") + dim(TAGLINE)
    lines.append(title if vlen(title) <= width else "  " + bold("Lumo Code") + dim("  v" + VERSION))
    return lines


def card_lines(rows, width, title=""):
    """A rounded info card. rows = [(label, value)]; value may already carry color. Every line is at most `width` columns."""
    W = max(28, min(width, 60))
    utf = _utf8()
    tl, tr, bl, br, hz, vt = ("╭", "╮", "╰", "╯", "─", "│") if utf else ("+", "+", "+", "+", "-", "|")
    inner = W - 6
    label_w = min(12, max((len(l) for l, _v in rows), default=6))
    head = ""
    if title:
        head = " " + title + " "
    top = "  " + faint(tl) + (faint(hz) + dim(head) + faint(hz * max(0, W - 4 - 1 - len(head))) if head else faint(hz * (W - 4))) + faint(tr)
    lines = [top]
    for label, value in rows:
        room = inner - label_w - 2
        val = value if vlen(value) <= room else clip(ANSI_RE.sub("", value), room)
        body = dim(label.ljust(label_w)) + "  " + val
        pad = " " * max(0, inner - vlen(body))
        lines.append("  " + faint(vt) + " " + body + pad + " " + faint(vt))
    lines.append("  " + faint(bl + hz * (W - 4) + br))
    return lines


def print_header(out, width):
    for line in header_lines(width):
        out(line)
