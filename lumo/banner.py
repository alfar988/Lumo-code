"""Startup banner: an emblem (a glowing ring with a four-point star) next to a spaced LUMO CODE title, a gradient rule, and a card with a gradient frame.

The emblem is painted with half-block characters, two pixels per text cell (foreground = upper pixel, background = lower pixel), so it is smooth
in a truecolor terminal and still readable in 256 colors. Three layouts fit every phone: emblem + title side by side, emblem above the title, and a
one-line title. The older shadow-lettered LUMO is still there as the "shadow" style (/banner shadow, needs 41+ columns).
Color is used only when the terminal supports it (NO_COLOR is respected); a plain version exists for terminals without Unicode.
"""

import math
import os
import sys
import time

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


def _fg(rgb, text):
    if not USE_COLOR:
        return text
    code = "38;2;%d;%d;%d" % rgb if TRUECOLOR else "38;5;%d" % _to256(rgb)
    return "\033[" + code + "m" + text + "\033[0m"


def _cell(top, bottom):
    """One text cell holding two vertical pixels (each an rgb tuple or None = transparent)."""
    if top is None and bottom is None:
        return " "
    def fg(c): return "38;2;%d;%d;%d" % c if TRUECOLOR else "38;5;%d" % _to256(c)
    def bg(c): return "48;2;%d;%d;%d" % c if TRUECOLOR else "48;5;%d" % _to256(c)
    if not USE_COLOR:
        return "█" if (top and bottom) else "▀" if top else "▄"
    if top is not None and bottom is not None:
        return "\033[%s;%sm▀\033[0m" % (fg(top), bg(bottom))
    if top is not None:
        return "\033[%sm▀\033[0m" % fg(top)
    return "\033[%sm▄\033[0m" % fg(bottom)


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
STYLES = ("bold", "thin", "emblem", "shadow", "mini")
STYLE_ALIASES = {"aurora": "bold", "beam": "bold"}


def _over(base, layer):
    """Composite layer = (rgb, alpha) over base = (rgb, alpha); alpha 0..1."""
    (c1, a1), (c2, a2) = base, layer
    a = 1.0 - (1.0 - a1) * (1.0 - a2)
    if a <= 0.0:
        return (0, 0, 0), 0.0
    w2 = a2 / a
    return tuple(int(c1[i] * (1.0 - w2) + c2[i] * w2) for i in range(3)), a


def emblem_pixels(n):
    """n x n pixels of the emblem: [[(rgb, alpha)]]. A glowing ring, a concave four-point star in the middle, a small gold satellite on the ring."""
    c = (n - 1) / 2.0
    r_out, r_in = n * 0.485, n * 0.31
    sat = (c + (r_in + r_out) / 2.0 * math.cos(-0.785), c + (r_in + r_out) / 2.0 * math.sin(-0.785))
    rows = []
    for y in range(n):
        row = []
        for x in range(n):
            dx, dy = x - c, y - c
            r = math.hypot(dx, dy)
            base = _gradient((x + y) / float(2 * (n - 1)))
            px = ((0, 0, 0), 0.0)
            if r < r_in:                                                       # a faint glow inside the ring
                px = _over(px, (_shade(base, 0.9), 0.20 * (1.0 - r / r_in) ** 1.2))
            ring = max(0.0, min(1.0, min(r - r_in, r_out - r) + 0.5))           # anti-aliased ring
            if ring > 0:
                inner = 1.0 - min(1.0, max(0.0, (r - r_in) / max(0.01, r_out - r_in)))
                px = _over(px, (_lift(base, 0.30 * inner), ring))
            sx, sy = abs(dx) / (n * 0.23), abs(dy) / (n * 0.23)
            star = max(0.0, min(1.0, (1.0 - (sx ** 0.6 + sy ** 0.6)) * 2.6))
            if star > 0:
                px = _over(px, (_lerp((255, 255, 255), SPARK, min(1.0, r / (n * 0.2))), star))
            d = math.hypot(x - sat[0], y - sat[1])
            dot = max(0.0, min(1.0, 1.25 - d))
            if dot > 0:
                px = _over(px, (SPARK, dot))
            row.append(px)
        rows.append(row)
    return rows


def emblem(n=12):
    """The emblem as n/2 text rows (half blocks)."""
    pix = emblem_pixels(n)
    lines = []
    for r in range(0, n, 2):
        cells = []
        for x in range(n):
            t, b = pix[r][x], pix[r + 1][x]
            tc = tuple(int(v * min(1.0, t[1] * 1.08)) for v in t[0]) if t[1] > 0.12 else None      # blend toward black (dark terminals)
            bc = tuple(int(v * min(1.0, b[1] * 1.08)) for v in b[0]) if b[1] > 0.12 else None
            cells.append(_cell(tc, bc))
        lines.append("".join(cells))
    return lines


def _spaced(text, rgb_at):
    """'LUMO' -> 'L U M O', each letter in its own gradient color."""
    letters = [ch for ch in text]
    out = []
    for i, ch in enumerate(letters):
        out.append(bold(_fg(rgb_at(i / float(max(1, len(letters) - 1))), ch)) if USE_COLOR else ch)
    return " ".join(out)


def _rule(n, t0=0.0, t1=1.0):
    ch = "─" if _utf8() else "-"
    return "".join(_fg(_gradient(t0 + (t1 - t0) * i / float(max(1, n - 1))), ch) for i in range(n))


def lockup(width, version=VERSION, tagline=TAGLINE):
    """Emblem next to the title, or above it on a narrow screen. Lines include the two-space indent."""
    if not _utf8():
        return ["  Lumo Code v%s" % version, "  " + tagline]
    ver = "v" + version
    for n, side in ((16, True), (12, True), (10, True), (12, False)):
        ecols = n
        if side and width < 2 + ecols + 3 + 21:
            continue
        em = emblem(n)
        tw_ = max(16, width - 2 - ecols - 3) if side else max(16, width - 4)
        title = _spaced("LUMO", lambda t: _gradient(0.0 + 0.55 * t)) + "   " + dim(" ".join("CODE"))
        tag = tagline if len(tagline) <= tw_ else "terminal AI agent"
        hint = "/help for commands" if len(ver) + 5 + 18 <= tw_ else "/help"
        right = {"title": title, "rule": _rule(min(tw_, 30), 0.0, 0.75), "tag": dim(clip(tag, tw_)),
                 "ver": faint(ver) + (faint("  ·  ") + dim(clip(hint, max(0, tw_ - len(ver) - 5))) if len(ver) + 5 + len(hint) <= tw_ else "")}
        rows = len(em)
        if side:
            slots = {}
            first = max(0, (rows - 4) // 2)
            for i, key in enumerate(("title", "rule", "tag", "ver")):
                slots[first + i] = right[key]
            lines = ["  " + em[i] + "   " + slots.get(i, "") for i in range(rows)]
            return [l.rstrip() for l in lines]
        lines = ["  " + e for e in em]
        return lines + ["  " + right["title"], "  " + right["rule"], "  " + right["tag"], "  " + right["ver"]]
    return ["  " + _spaced("LUMO", lambda t: _gradient(0.55 * t)) + "  " + dim(ver), "  " + dim(clip(tagline, width - 4))]


THIN = {  # a thin double-line alphabet: 3 rows, 3 columns per letter, crisp in any terminal font
    "L": ["╦  ", "║  ", "╩═╝"], "U": ["╦ ╦", "║ ║", "╚═╝"], "M": ["╔╦╗", "║║║", "╩ ╩"], "O": ["╔═╗", "║ ║", "╚═╝"],
    "C": ["╔═╗", "║  ", "╚═╝"], "D": ["╔╦╗", " ║║", "═╩╝"], "E": ["╔═╗", "║╣ ", "╚═╝"],
}


def _thin_rows(words, gap=1, word_gap=4):
    """Rows of the thin logotype for e.g. ['LUMO', 'CODE'] as plain text."""
    rows = ["", "", ""]
    for wi, word in enumerate(words):
        for li, ch in enumerate(word):
            for r in range(3):
                rows[r] += THIN[ch][r] + (" " * gap if li < len(word) - 1 else "")
        if wi < len(words) - 1:
            rows = [r + " " * word_gap for r in rows]
    return rows


def _paint(text, t0, t1, lift=0.0):
    """Color a plain string with the gradient from t0 to t1 (columns), bold; spaces stay spaces."""
    n = max(1, len(text) - 1)
    return "".join(ch if ch == " " else bold(_fg(_lift(_gradient(t0 + (t1 - t0) * i / float(n)), lift), ch)) for i, ch in enumerate(text))


def _light_beam(n):
    """A line of light: thick and bright in the middle, thinner and dimmer toward both ends, a gold spark at the centre."""
    c = (n - 1) / 2.0
    out = []
    for i in range(n):
        d = abs(i - c) / max(1.0, c)
        t = i / float(max(1, n - 1))
        if i == int(c) or (n % 2 == 0 and i == int(c) + 1):
            out.append(_fg(SPARK, "✦") if i == int(c) else _fg(_lift(_gradient(t), 0.4), "━"))
            continue
        ch = "━" if d < 0.33 else "─" if d < 0.85 else "╌"
        out.append(_fg(_shade(_lift(_gradient(t), 0.5 * (1.0 - d) ** 2), 0.55 + 0.45 * (1.0 - d)), ch))
    return "".join(out)


def beam_hero(width, version=VERSION, tagline=TAGLINE):
    """LUMO CODE in thin letters, a beam of light, the tagline and the version, centred in a column of at most 60."""
    W = max(20, min(width - 2, 60))
    ver = "v" + version
    if W >= 36:
        rows = _thin_rows(["LUMO", "CODE"])
    else:
        rows = _thin_rows(["LUMO"])
    mw = len(rows[0])

    def centre(plain_len, painted):
        return "  " + " " * max(0, (W - plain_len) // 2) + painted

    lines = [centre(mw, _paint(r, 0.0, 0.85)) for r in rows]
    bw = min(W, max(mw + 8, 28))
    lines.append(centre(bw, _light_beam(bw)))
    tag = tagline if len(tagline) <= W else "terminal AI agent"
    lines.append(centre(len(tag), dim(tag)))
    hint = ver + "  ·  /help for commands" if len(ver) + 5 + 18 <= W else ver
    lines.append(centre(len(hint), faint(ver) + (faint("  ·  ") + dim("/help for commands") if hint != ver else "")))
    if W < 36:
        lines.insert(3, centre(4, dim("C O D E")))
    return lines


SLAB = {  # bold rounded letters, 8 x 10 pixels (two pixels per text row), hard edges: crisp on any screen
    "L": ["##......"] * 8 + ["########"] * 2,
    "U": ["##....##"] * 8 + [".######.", "..####.."],
    "M": ["##....##", "###..###", "########", "##.##.##", "##.##.##"] + ["##....##"] * 5,
    "O": ["..####..", ".######."] + ["##....##"] * 6 + [".######.", "..####.."],
}


def slab_rows(word="LUMO", gap=2):
    """The wordmark as text rows (half blocks, solid colors, a horizontal aurora gradient and a lighter top edge); no blending, no soft edges."""
    cols = []
    for i, ch in enumerate(word):
        cols.append(SLAB[ch])
        if i < len(word) - 1:
            cols.append(["." * gap] * 10)
    grid = ["".join(c[r] for c in cols) for r in range(10)]
    w = len(grid[0])
    lines = []
    for tr in range(0, 10, 2):
        cells = []
        for x in range(w):
            def px(r):
                if grid[r][x] != "#":
                    return None
                base = _gradient(0.0 + 0.9 * x / float(max(1, w - 1)))
                return _lift(base, 0.34 * (1.0 - r / 9.0))                # the top of each letter catches the light
            cells.append(_cell(px(tr), px(tr + 1)))
        lines.append("".join(cells))
    return lines


def slab_hero(width, version=VERSION, tagline=TAGLINE):
    """Big, bold, crisp LUMO, a beam of light under it, 'C O D E' with the tagline, then the version. Centred in a column of at most 60."""
    W = max(20, min(width - 2, 60))
    rows = slab_rows()
    mw = vlen(rows[0])
    ver = "v" + version

    def centre(painted):
        return "  " + " " * max(0, (W - vlen(painted)) // 2) + painted
    lines = [centre(r) for r in rows]
    bw = max(mw, 30)
    lines.append(centre(_light_beam(min(W, bw))))
    code = _paint("C O D E", 0.1, 0.9)
    tag = tagline if len("C O D E  ·  ") + len(tagline) <= W else "terminal AI agent"
    lines.append(centre(code + faint("  ·  ") + dim(tag)))
    hint = faint(ver) + (faint("  ·  ") + dim("/help for commands") if len(ver) + 5 + 18 <= W else "")
    lines.append(centre(hint))
    return lines


def header_lines(width, style="bold"):
    """Everything above the info card. Each line starts with two spaces and fits `width` columns."""
    style = STYLE_ALIASES.get(style, style)
    if style == "mini" or not _utf8():
        title = "  " + bold("Lumo Code") + dim("  v" + VERSION) + faint("  ·  ") + dim(TAGLINE)
        return [title if vlen(title) <= width else "  " + bold("Lumo Code") + dim("  v" + VERSION)]
    if style == "shadow":
        mark = wordmark(width) if width >= 41 else []
        if mark:
            title = "  " + bold("Lumo Code") + dim("  v" + VERSION) + faint("  ·  ") + dim(TAGLINE)
            return ["  " + l for l in mark] + ["  " + beam(vlen(mark[0])), "", title if vlen(title) <= width else "  " + bold("Lumo Code") + dim("  v" + VERSION)]
    if style == "emblem":
        return lockup(width)
    if style == "thin" or width < 42:
        return beam_hero(width)
    return slab_hero(width)


def print_header(out, width, style="bold", animate=False):
    lines = header_lines(width, style)
    for line in lines:
        out(line)
        if animate:
            time.sleep(0.045)
