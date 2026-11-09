"""lumovideo: 2D video for Lumo Code.

Pillow draws every frame, ffmpeg turns the frames into an MP4 (H.264 + AAC) that plays everywhere.
One file, no other dependencies (numpy is not needed). Typical script:

    from lumovideo import *
    v = Video(1280, 720, fps=30)                 # coordinates are always 1280x720, whatever the output quality
    def intro(c, t):
        c.background("#101626", "#243b6b")
        c.text("Hello", 640, 360, 120, "white", outline="#000000", outline_w=6, scale=ease(t / 0.6, "out_back"))
    v.scene(3.0, intro, fade_out=0.4)
    v.render()                                   # videos/<script name>.mp4, or $LUMO_VIDEO_OUT

Main parts: ease/Keys (timing), Canvas (drawing, camera), sfx/music/Mixer (sound), Video (scenes, render, checks),
Stick/Fight/Stage (stickman characters and fights), Typewriter/Particles/BarChart/Subtitles (components).
"""

__version__ = "1.0.0"

import array
import bisect
import inspect
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat
except ImportError:                      # the render step explains how to install it
    Image = ImageChops = ImageDraw = ImageFont = ImageStat = None

__all__ = [
    "Video", "Scene", "Canvas", "Keys", "Spring", "ease", "lerp", "clamp", "remap", "tween", "noise", "pulse", "EASINGS",
    "rgb", "mix", "shade", "PALETTES", "font", "Mixer", "sfx", "music", "note_freq", "Stick", "Fight", "Stage", "POSES", "MOVES",
    "Typewriter", "Particles", "BarChart", "Subtitles", "Timeline", "check_requirements", "ffmpeg_path", "find_font", "frame_stats",
]


# ======================================================================================
# timing: easing, tweening, keyframes
# ======================================================================================
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _out(f):
    return lambda t: 1 - f(1 - t)


def _in_out(f):
    return lambda t: f(t * 2) / 2 if t < 0.5 else 1 - f((1 - t) * 2) / 2


def _poly(n):
    return lambda t: t ** n


def _back(t, s=1.70158):
    return t * t * ((s + 1) * t - s)


def _elastic(t):
    if t in (0, 1):
        return t
    return -(2 ** (10 * t - 10)) * math.sin((t * 10 - 10.75) * (2 * math.pi / 3))


def _bounce_out(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


_BASE = {
    "quad": _poly(2), "cubic": _poly(3), "quart": _poly(4), "quint": _poly(5),
    "sine": lambda t: 1 - math.cos(t * math.pi / 2),
    "expo": lambda t: 0.0 if t == 0 else 2 ** (10 * t - 10),
    "circ": lambda t: 1 - math.sqrt(max(0.0, 1 - t * t)),
    "back": _back, "elastic": _elastic,
}
EASINGS = {"linear": lambda t: t, "smooth": lambda t: t * t * (3 - 2 * t), "smoother": lambda t: t * t * t * (t * (t * 6 - 15) + 10),
           "step": lambda t: 0.0 if t < 1 else 1.0, "out_bounce": _bounce_out, "in_bounce": lambda t: 1 - _bounce_out(1 - t),
           "in_out_bounce": _in_out(lambda t: 1 - _bounce_out(1 - t))}
for _n, _f in _BASE.items():
    EASINGS["in_" + _n] = _f
    EASINGS["out_" + _n] = _out(_f)
    EASINGS["in_out_" + _n] = _in_out(_f)


def ease(t, name="in_out_cubic"):
    """Map progress t (0..1, clamped) through an easing curve: linear, smooth, in_/out_/in_out_ + quad cubic quart quint sine expo circ back elastic, bounce."""
    f = EASINGS.get(name) if isinstance(name, str) else name
    if f is None:
        raise ValueError("unknown easing %r; choose one of: %s" % (name, ", ".join(sorted(EASINGS))))
    return f(clamp(t))


def lerp(a, b, t):
    """Linear interpolation of numbers or equal-length tuples/lists."""
    if isinstance(a, (tuple, list)):
        return type(a)(x + (y - x) * t for x, y in zip(a, b)) if isinstance(a, tuple) else [x + (y - x) * t for x, y in zip(a, b)]
    return a + (b - a) * t


def remap(v, a0, a1, b0, b1, easing="linear"):
    """Map v from [a0, a1] to [b0, b1] (clamped) through an easing curve."""
    t = 0.0 if a1 == a0 else (v - a0) / (a1 - a0)
    return lerp(b0, b1, ease(t, easing))


def tween(t, t0, t1, a, b, easing="in_out_cubic"):
    """Value at time t of an animation from a (at t0) to b (at t1). Holds a before t0 and b after t1."""
    return remap(t, t0, t1, a, b, easing)


def pulse(t, period=1.0, lo=0.0, hi=1.0):
    """Smooth repeating wave between lo and hi."""
    return lo + (hi - lo) * (0.5 - 0.5 * math.cos(t / period * 2 * math.pi))


def noise(x, seed=0):
    """Smooth deterministic value noise in -1..1 (camera shake, wobble, hand-held feel)."""
    def h(i):
        n = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFF) / 32767.5 - 1.0
    i = math.floor(x)
    f = x - i
    f = f * f * (3 - 2 * f)
    return h(i) * (1 - f) + h(i + 1) * f


class Keys:
    """Keyframes: Keys([(0, 0), (1.0, 100, "out_cubic"), (2.5, 40)]). Call it with a time. The easing of a key shapes the segment that ends on it.
    Values can be numbers or tuples (positions, colors)."""

    def __init__(self, keys, default_ease="in_out_cubic"):
        ks = sorted(keys, key=lambda k: k[0])
        if not ks:
            raise ValueError("Keys needs at least one key")
        self.t = [k[0] for k in ks]
        self.v = [k[1] for k in ks]
        self.e = [(k[2] if len(k) > 2 else default_ease) for k in ks]

    def __call__(self, t):
        if t <= self.t[0]:
            return self.v[0]
        if t >= self.t[-1]:
            return self.v[-1]
        i = bisect.bisect_right(self.t, t)
        t0, t1 = self.t[i - 1], self.t[i]
        return lerp(self.v[i - 1], self.v[i], ease((t - t0) / (t1 - t0), self.e[i]))


class Spring:
    """Critically damped follower: smooth camera or UI motion. s = Spring(0); s.update(target, dt) returns the new value."""

    def __init__(self, value=0.0, speed=8.0):
        self.x, self.v, self.speed = value, 0.0, speed

    def update(self, target, dt):
        w = self.speed
        d = self.x - target
        t = (self.v + w * d) * dt
        e = math.exp(-w * dt)
        self.x = target + (d + t) * e
        self.v = (self.v - w * t) * e
        return self.x


# ======================================================================================
# colour and fonts
# ======================================================================================
_NAMED = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (230, 57, 70), "green": (46, 204, 113), "blue": (52, 152, 219),
          "yellow": (255, 214, 10), "orange": (255, 149, 0), "purple": (155, 89, 182), "pink": (255, 105, 180), "cyan": (0, 220, 255),
          "gray": (128, 128, 128), "grey": (128, 128, 128), "gold": (255, 200, 40), "navy": (18, 28, 64), "teal": (0, 150, 150)}
PALETTES = {
    "neon": ["#08f7fe", "#fe53bb", "#f5d300", "#09fbd3", "#7122fa"],
    "sunset": ["#ff5e5b", "#ffb347", "#ffd166", "#6a4c93", "#1d2b53"],
    "ocean": ["#03045e", "#0077b6", "#00b4d8", "#90e0ef", "#caf0f8"],
    "forest": ["#1b4332", "#2d6a4f", "#52b788", "#95d5b2", "#d8f3dc"],
    "candy": ["#ff99c8", "#fcf6bd", "#d0f4de", "#a9def9", "#e4c1f9"],
    "mono": ["#0b0d12", "#2b303b", "#565e6e", "#a7b0c0", "#f1f4f9"],
}


def rgb(c):
    """Colour from '#rgb', '#rrggbb', a name, or an (r, g, b[, a]) tuple. Returns an (r, g, b) tuple."""
    if isinstance(c, (tuple, list)):
        return tuple(int(clamp(v, 0, 255)) for v in c[:3])
    if isinstance(c, str):
        s = c.strip().lower()
        if s in _NAMED:
            return _NAMED[s]
        if s.startswith("#"):
            s = s[1:]
        if len(s) in (3, 4):
            s = "".join(ch * 2 for ch in s)
        if len(s) in (6, 8) and re.fullmatch(r"[0-9a-f]+", s):
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    raise ValueError("cannot read colour %r (use '#rrggbb', a name or an (r, g, b) tuple)" % (c,))


def mix(c1, c2, t):
    """Blend two colours: t=0 gives c1, t=1 gives c2."""
    a, b = rgb(c1), rgb(c2)
    t = clamp(t)
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def shade(c, k):
    """Lighten (k > 0) or darken (k < 0) a colour by a fraction."""
    return mix(c, (255, 255, 255), k) if k >= 0 else mix(c, (0, 0, 0), -k)


_FONT_FILES = {
    True: ["DejaVuSans-Bold.ttf", "Roboto-Bold.ttf", "NotoSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf",
           "Helvetica-Bold.ttf", "DroidSans-Bold.ttf", "FreeSansBold.ttf", "Inter-Bold.ttf"],
    False: ["DejaVuSans.ttf", "Roboto-Regular.ttf", "NotoSans-Regular.ttf", "LiberationSans-Regular.ttf", "Arial.ttf", "arial.ttf",
            "Helvetica.ttf", "DroidSans.ttf", "FreeSans.ttf", "Inter-Regular.ttf"],
}
_FONT_DIRS = ["/data/data/com.termux/files/usr/share/fonts", "/system/fonts", "/usr/share/fonts", "/usr/local/share/fonts",
              "/Library/Fonts", "/System/Library/Fonts", "C:\\Windows\\Fonts", os.path.expanduser("~/.fonts")]
_FONT_PATH = {}
_FONTS = {}
USER_FONT = None                              # set a path to a .ttf to use your own font everywhere


def find_font(bold=True):
    """Path of a usable TrueType font on this device, or None."""
    if USER_FONT and os.path.exists(USER_FONT):
        return USER_FONT
    if bold in _FONT_PATH:
        return _FONT_PATH[bold]
    want = [n.lower() for n in _FONT_FILES[bold]]
    found = None
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        hits = {}
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower() in want:
                    hits[f.lower()] = os.path.join(root, f)
            if len(hits) >= len(want):
                break
        for n in want:
            if n in hits:
                found = hits[n]
                break
        if found:
            break
    _FONT_PATH[bold] = found
    return found


def font(size, bold=True):
    """A PIL font of the given pixel size (cached). Falls back to Pillow's built-in font when no TrueType font exists."""
    size = max(6, int(round(size)))
    key = (size, bold, USER_FONT)
    f = _FONTS.get(key)
    if f is None:
        p = find_font(bold)
        try:
            f = ImageFont.truetype(p, size) if p else ImageFont.load_default(size)
        except Exception:
            f = ImageFont.load_default()
        if len(_FONTS) > 200:
            _FONTS.clear()
        _FONTS[key] = f
    return f


# ======================================================================================
# Canvas: what a scene draws on
# ======================================================================================
class _Cam:
    def __init__(self, x, y):
        self.x, self.y, self.zoom, self.sx, self.sy = x, y, 1.0, 0.0, 0.0


_BG_CACHE = {}
_GLOW_CACHE = {}
_VIG_CACHE = {}
_IMG_CACHE = {}


def _cache_put(cache, key, value, limit=8):
    if len(cache) >= limit:
        cache.pop(next(iter(cache)))
    cache[key] = value
    return value


class Canvas:
    """One frame. Draw with logical coordinates (the Video width x height, 1280x720 by default); the output quality never changes your numbers.

    World mode (default): drawing goes through the camera (c.camera(x, y, zoom, shake)). Use `with c.screen():` for things that must not move
    (HUD, captions). All sizes scale with the camera zoom in world mode. Colours: '#rrggbb', a name or an (r, g, b) tuple."""

    def __init__(self, w, h, px_w, px_h, ss=2, bg="#000000"):
        self.W, self.H = w, h
        self.pw, self.ph, self.ss = px_w, px_h, ss
        self.k = px_w * ss / float(w)
        self.im = Image.new("RGB", (px_w * ss, px_h * ss), rgb(bg))
        self.d = ImageDraw.Draw(self.im)
        self.cam = _Cam(w / 2.0, h / 2.0)
        self.world = True
        self.t = self.T = 0.0
        self.frame = 0
        self.fps = 30
        self.seed = 0

    # ---- transforms ----
    def _pt(self, x, y):
        if self.world:
            c = self.cam
            return ((x - c.x) * c.zoom + self.W / 2.0 + c.sx) * self.k, ((y - c.y) * c.zoom + self.H / 2.0 + c.sy) * self.k
        return x * self.k, y * self.k

    def _len(self, v):
        return v * (self.cam.zoom if self.world else 1.0) * self.k

    def to_screen(self, x, y):
        """World point -> logical screen position."""
        px, py = self._pt(x, y)
        return px / self.k, py / self.k

    def to_world(self, sx, sy):
        c = self.cam
        return (sx - self.W / 2.0 - c.sx) / c.zoom + c.x, (sy - self.H / 2.0 - c.sy) / c.zoom + c.y

    def camera(self, x=None, y=None, zoom=None, shake=0.0, shake_speed=22.0):
        """Aim the camera at world point (x, y) with a zoom (1 = normal). shake = strength in logical pixels (hand-held / impact shake)."""
        if x is not None:
            self.cam.x = x
        if y is not None:
            self.cam.y = y
        if zoom is not None:
            self.cam.zoom = max(0.05, zoom)
        if shake:
            s = self.T * shake_speed
            self.cam.sx, self.cam.sy = noise(s, self.seed + 1) * shake, noise(s, self.seed + 2) * shake
        else:
            self.cam.sx = self.cam.sy = 0.0

    def screen(self):
        return _Mode(self, False)

    def parallax(self, fx, fy=None, fzoom=0.0):
        """Draw a far layer that moves less than the camera: fx 0 = fixed to the screen, 1 = moves with the world."""
        return _Parallax(self, fx, fx if fy is None else fy, fzoom)

    # ---- filling ----
    def clear(self, color="#000000"):
        self.d.rectangle([0, 0, self.im.width, self.im.height], fill=rgb(color))

    def background(self, top, bottom=None):
        """Fill the frame with a flat colour or a vertical gradient (top -> bottom)."""
        top = rgb(top)
        bottom = rgb(bottom) if bottom is not None else top
        if top == bottom:
            self.clear(top)
            return
        key = (self.im.size, top, bottom)
        bg = _BG_CACHE.get(key)
        if bg is None:
            mask = Image.linear_gradient("L").resize(self.im.size, Image.BILINEAR)
            bg = _cache_put(_BG_CACHE, key, Image.composite(Image.new("RGB", self.im.size, bottom), Image.new("RGB", self.im.size, top), mask))
        self.im.paste(bg, (0, 0))

    # ---- shapes ----
    def line(self, x1, y1, x2, y2, color="white", width=4, cap=True):
        self.polyline([(x1, y1), (x2, y2)], color, width, cap=cap)

    def polyline(self, pts, color="white", width=4, cap=True, closed=False):
        p = [self._pt(x, y) for x, y in pts]
        if closed:
            p.append(p[0])
        w = max(1, int(round(self._len(width))))
        col = rgb(color)
        self.d.line(p, fill=col, width=w, joint="curve" if w > 2 else None)
        if cap and w > 2:
            r = w / 2.0
            for q in (p[0], p[-1]):
                self.d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)

    def circle(self, x, y, r, fill=None, outline=None, width=3, alpha=1.0):
        px, py = self._pt(x, y)
        rr = self._len(r)
        if alpha < 1.0 and fill is not None:
            self._alpha_sprite(px - rr, py - rr, 2 * rr, 2 * rr, lambda d, s: d.ellipse([0, 0, s[0] - 1, s[1] - 1], fill=rgb(fill) + (255,)), alpha)
            fill = None
            if outline is None:
                return
        self.d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=rgb(fill) if fill is not None else None,
                       outline=rgb(outline) if outline is not None else None, width=max(1, int(round(self._len(width)))))

    def ellipse(self, x, y, rx, ry, fill=None, outline=None, width=3, alpha=1.0):
        px, py = self._pt(x, y)
        a, b = self._len(rx), self._len(ry)
        if alpha < 1.0 and fill is not None:
            self._alpha_sprite(px - a, py - b, 2 * a, 2 * b, lambda d, s: d.ellipse([0, 0, s[0] - 1, s[1] - 1], fill=rgb(fill) + (255,)), alpha)
            return
        self.d.ellipse([px - a, py - b, px + a, py + b], fill=rgb(fill) if fill is not None else None,
                       outline=rgb(outline) if outline is not None else None, width=max(1, int(round(self._len(width)))))

    def rect(self, x, y, w, h, fill=None, outline=None, width=3, radius=0, anchor="tl", alpha=1.0):
        """Rectangle. anchor: 'tl' (x, y is the top-left corner) or 'c' (the centre) or 'bl', 'bc', 'tr', 'br', 'tc', 'cl', 'cr'."""
        ax = {"l": 0.0, "c": 0.5, "r": 1.0}[anchor[-1] if anchor[-1] in "lcr" else ("l" if anchor == "tl" else "c")]
        ay = {"t": 0.0, "c": 0.5, "b": 1.0}[anchor[0] if anchor[0] in "tcb" else "c"]
        if anchor in ("c", "mm", "cc"):
            ax = ay = 0.5
        x0, y0 = x - w * ax, y - h * ay
        p0, p1 = self._pt(x0, y0), self._pt(x0 + w, y0 + h)
        r = min(self._len(radius), abs(p1[0] - p0[0]) / 2, abs(p1[1] - p0[1]) / 2)
        if alpha < 1.0 and fill is not None:
            sw, sh = p1[0] - p0[0], p1[1] - p0[1]

            def paint(d, s):
                d.rounded_rectangle([0, 0, s[0] - 1, s[1] - 1], r, fill=rgb(fill) + (255,))
            self._alpha_sprite(p0[0], p0[1], sw, sh, paint, alpha)
            fill = None
            if outline is None:
                return
        kw = dict(fill=rgb(fill) if fill is not None else None, outline=rgb(outline) if outline is not None else None,
                  width=max(1, int(round(self._len(width)))))
        if r >= 1:
            self.d.rounded_rectangle([p0[0], p0[1], p1[0], p1[1]], r, **kw)
        else:
            self.d.rectangle([p0[0], p0[1], p1[0], p1[1]], **kw)

    def poly(self, pts, fill=None, outline=None, width=3):
        p = [self._pt(x, y) for x, y in pts]
        if fill is not None:
            self.d.polygon(p, fill=rgb(fill))
        if outline is not None:
            self.polyline(pts, outline, width, closed=True)

    def arc(self, x, y, r, start, end, color="white", width=4):
        """Arc of a circle, angles in degrees (0 = right, 90 = down)."""
        px, py = self._pt(x, y)
        rr = self._len(r)
        self.d.arc([px - rr, py - rr, px + rr, py + rr], start, end, fill=rgb(color), width=max(1, int(round(self._len(width)))))

    def glow(self, x, y, r, color="white", strength=1.0):
        """Soft radial light (muzzle flash, sun, hit spark, spotlight)."""
        px, py = self._pt(x, y)
        size = int(max(4, self._len(r) * 2))
        col = rgb(color)
        key = (size, col)
        sp = _GLOW_CACHE.get(key)
        if sp is None:
            g = Image.radial_gradient("L").resize((size, size), Image.BILINEAR)
            alpha = g.point(lambda v: int(255 * max(0.0, 1 - min(1.0, v / 180.0)) ** 2))
            sp = Image.new("RGBA", (size, size), col + (0,))
            sp.putalpha(alpha)
            _cache_put(_GLOW_CACHE, key, sp, 40)
        self._blit(sp, px - size / 2.0, py - size / 2.0, strength)

    def vignette(self, strength=0.5):
        """Darken the frame edges."""
        key = (self.im.size, round(strength, 2))
        m = _VIG_CACHE.get(key)
        if m is None:
            g = Image.radial_gradient("L").resize(self.im.size, Image.BILINEAR)
            m = _cache_put(_VIG_CACHE, key, g.point(lambda v: int(255 * strength * (v / 255.0) ** 2.4)), 4)
        self.im.paste((0, 0, 0), (0, 0), m)

    def tint(self, color, amount):
        """Cover the whole frame with a colour (amount 0..1): fades, flashes, colour grading."""
        if amount <= 0:
            return
        self.im.paste(rgb(color), (0, 0), Image.new("L", self.im.size, int(255 * clamp(amount))))

    def letterbox(self, ratio=2.39, color="#000000"):
        """Cinema bars: crop the picture to this aspect ratio."""
        bar = max(0.0, (self.H - self.W / ratio) / 2.0)
        if bar > 0:
            with self.screen():
                self.rect(0, 0, self.W, bar, fill=color)
                self.rect(0, self.H - bar, self.W, bar, fill=color)

    # ---- text and pictures ----
    def text_size(self, s, size=40, bold=True):
        """(width, height) of the text in logical units, at zoom 1."""
        f = font(size * self.k, bold)
        b = self.d.multiline_textbbox((0, 0), str(s), font=f) if "\n" in str(s) else self.d.textbbox((0, 0), str(s), font=f)
        return (b[2] - b[0]) / self.k, (b[3] - b[1]) / self.k

    def wrap(self, s, size, max_w, bold=True):
        """Break text into lines that fit max_w logical units."""
        f = font(size * self.k, bold)
        lines = []
        for para in str(s).split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = (cur + " " + word).strip()
                if cur and self.d.textlength(trial, font=f) / self.k > max_w:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        return "\n".join(lines)

    def text(self, s, x, y, size=48, color="white", anchor="mm", bold=True, outline=None, outline_w=0, shadow=None, alpha=1.0, scale=1.0,
             rot=0.0, max_w=None, line_spacing=0.25):
        """Draw text. anchor: two letters, horizontal l/m/r + vertical a(top)/m/d(bottom): 'mm' centred, 'la' top-left. scale grows the size
        (ease(t, 'out_back') pops it in). outline/outline_w add a stroke, shadow=(dx, dy, colour) a drop shadow, rot turns it (degrees)."""
        s = str(s)
        size = size * scale
        if size <= 0.5 or alpha <= 0.0:
            return
        if max_w:
            s = self.wrap(s, size, max_w, bold)
        f = font(self._len(size), bold)
        stroke = int(round(self._len(outline_w))) if outline is not None else 0
        px, py = self._pt(x, y)
        multi = "\n" in s
        sp = self._len(size) * line_spacing
        align = {"l": "left", "m": "center", "r": "right"}[anchor[0]]
        anc = anchor[0] + ("a" if anchor[1] == "a" else "m" if anchor[1] == "m" else "d")

        def paint(d, ox, oy, col, st):
            if multi:
                d.multiline_text((ox, oy), s, font=f, fill=col, anchor=anc, align=align, spacing=sp, stroke_width=st,
                                 stroke_fill=rgb(outline) if outline is not None and st else None)
            else:
                d.text((ox, oy), s, font=f, fill=col, anchor=anc, stroke_width=st, stroke_fill=rgb(outline) if outline is not None and st else None)
        if alpha >= 1.0 and not rot:
            if shadow:
                sdx, sdy, scol = shadow
                paint(self.d, px + self._len(sdx), py + self._len(sdy), rgb(scol), stroke)
            paint(self.d, px, py, rgb(color), stroke)
            return
        # rotated or translucent text goes through a small sprite
        b = (self.d.multiline_textbbox((0, 0), s, font=f, spacing=sp, stroke_width=stroke) if multi
             else self.d.textbbox((0, 0), s, font=f, stroke_width=stroke))
        pad = int(self._len(abs(shadow[0]) + abs(shadow[1])) + 4) if shadow else 4
        tw, th = int(b[2] - b[0]) + pad * 2 + 2, int(b[3] - b[1]) + pad * 2 + 2
        spr = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        sd = ImageDraw.Draw(spr)
        ox, oy = pad - b[0], pad - b[1]
        if shadow:
            sdx, sdy, scol = shadow
            (sd.multiline_text if multi else sd.text)((ox + self._len(sdx), oy + self._len(sdy)), s, font=f, fill=rgb(scol) + (255,),
                                                       stroke_width=stroke, stroke_fill=(rgb(outline) + (255,)) if stroke else None,
                                                       **({"spacing": sp, "align": align} if multi else {}))
        (sd.multiline_text if multi else sd.text)((ox, oy), s, font=f, fill=rgb(color) + (255,), stroke_width=stroke,
                                                   stroke_fill=(rgb(outline) + (255,)) if stroke else None,
                                                   **({"spacing": sp, "align": align} if multi else {}))
        if rot:
            spr = spr.rotate(rot, resample=Image.BICUBIC, expand=True)
        w2, h2 = spr.size
        hx = {"l": 0.0, "m": 0.5, "r": 1.0}[anchor[0]]
        hy = {"a": 0.0, "m": 0.5, "d": 1.0}[anc[1]]
        self._blit(spr, px - w2 * hx, py - h2 * hy, alpha)

    def image(self, img, x, y, w=None, h=None, anchor="mm", alpha=1.0, rot=0.0):
        """Draw a picture (a file path or a PIL image) at logical size w x h (keep the aspect ratio by giving only one of them)."""
        if isinstance(img, str):
            key = img
            im = _IMG_CACHE.get(key)
            if im is None:
                im = _cache_put(_IMG_CACHE, key, Image.open(img).convert("RGBA"), 24)
        else:
            im = img.convert("RGBA")
        iw, ih = im.size
        if w is None and h is None:
            w = iw
        if w is None:
            w = h * iw / float(ih)
        if h is None:
            h = w * ih / float(iw)
        pw, ph = max(1, int(self._len(w))), max(1, int(self._len(h)))
        spr = im.resize((pw, ph), Image.BILINEAR if pw < iw else Image.BICUBIC)
        if rot:
            spr = spr.rotate(rot, resample=Image.BICUBIC, expand=True)
        w2, h2 = spr.size
        px, py = self._pt(x, y)
        hx = {"l": 0.0, "c": 0.5, "m": 0.5, "r": 1.0}.get(anchor[0], 0.5)
        hy = {"t": 0.0, "a": 0.0, "c": 0.5, "m": 0.5, "b": 1.0, "d": 1.0}.get(anchor[1] if len(anchor) > 1 else "m", 0.5)
        self._blit(spr, px - w2 * hx, py - h2 * hy, alpha)

    # ---- internals ----
    def _blit(self, spr, x0, y0, alpha=1.0):
        x0, y0 = int(round(x0)), int(round(y0))
        if alpha < 1.0:
            a = spr.getchannel("A").point(lambda v: int(v * alpha))
            spr = spr.copy()
            spr.putalpha(a)
        W, H = self.im.size
        sx0, sy0 = max(0, -x0), max(0, -y0)
        sx1, sy1 = min(spr.width, W - x0), min(spr.height, H - y0)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        if (sx0, sy0, sx1, sy1) != (0, 0, spr.width, spr.height):
            spr = spr.crop((sx0, sy0, sx1, sy1))
        self.im.paste(spr, (x0 + sx0, y0 + sy0), spr)

    def _alpha_sprite(self, x0, y0, w, h, paint, alpha):
        sw, sh = max(1, int(round(w))), max(1, int(round(h)))
        spr = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        paint(ImageDraw.Draw(spr), (sw, sh))
        self._blit(spr, x0, y0, alpha)

    def to_image(self):
        """The finished frame at output resolution (RGB)."""
        im = self.im.convert("RGB") if self.im.mode != "RGB" else self.im
        if self.ss > 1:
            return im.reduce(self.ss)
        return im


class _Mode:
    def __init__(self, c, world):
        self.c, self.world = c, world

    def __enter__(self):
        self.prev = self.c.world
        self.c.world = self.world
        return self.c

    def __exit__(self, *a):
        self.c.world = self.prev


class _Parallax:
    def __init__(self, c, fx, fy, fz):
        self.c, self.fx, self.fy, self.fz = c, fx, fy, fz

    def __enter__(self):
        cam = self.c.cam
        self.saved = (cam.x, cam.y, cam.zoom)
        cam.x = self.c.W / 2.0 + (cam.x - self.c.W / 2.0) * self.fx
        cam.y = self.c.H / 2.0 + (cam.y - self.c.H / 2.0) * self.fy
        cam.zoom = 1.0 + (cam.zoom - 1.0) * self.fz
        return self.c

    def __exit__(self, *a):
        cam = self.c.cam
        cam.x, cam.y, cam.zoom = self.saved


# ======================================================================================
# sound: synthesised effects, music and a mixer (no sound files needed)
# ======================================================================================
SR = 44100
_NOTE = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}


def note_freq(name):
    """Frequency of a note name like 'A4', 'C#3', 'Eb2' (A4 = 440 Hz)."""
    m = re.fullmatch(r"([A-Ga-g])([#bB]?)(-?\d)", name.strip())
    if not m:
        raise ValueError("bad note name %r (use e.g. 'A4')" % name)
    key = m.group(1).upper() + ("B" if m.group(2) in ("b", "B") else m.group(2))
    semis = _NOTE[key] + (int(m.group(3)) - 4) * 12 - 9
    return 440.0 * 2 ** (semis / 12.0)


def _buf(n):
    return array.array("f", [0.0]) * n


def _wave(kind, ph):
    if kind == "sine":
        return math.sin(ph)
    x = (ph / (2 * math.pi)) % 1.0
    if kind == "square":
        return 1.0 if x < 0.5 else -1.0
    if kind == "saw":
        return 2.0 * x - 1.0
    if kind == "tri":
        return 4.0 * abs(x - 0.5) - 1.0
    raise ValueError("wave must be sine, square, saw or tri")


def _lowpass(buf, alpha):
    y = 0.0
    out = _buf(len(buf))
    for i, x in enumerate(buf):
        y += alpha * (x - y)
        out[i] = y
    return out


class Mixer:
    """A stereo mix bus. Add sounds at times (seconds), then save a WAV or hand it to Video (video.sound(...)).
    m = Mixer(10); m.add(sfx.punch(), at=2.0, vol=0.9, pan=-0.3); m.save('mix.wav')"""

    def __init__(self, duration):
        self.n = int(max(0.1, duration) * SR) + SR // 2
        self.l = _buf(self.n)
        self.r = _buf(self.n)

    @property
    def duration(self):
        return self.n / float(SR)

    def add(self, snd, at=0.0, vol=1.0, pan=0.0):
        start = int(at * SR)
        if start >= self.n or not len(snd):
            return
        if start < 0:
            snd = snd[-start:]
            start = 0
        end = min(self.n, start + len(snd))
        lg, rg = vol * min(1.0, 1.0 - pan), vol * min(1.0, 1.0 + pan)
        L, R = self.l, self.r
        for i in range(end - start):
            s = snd[i]
            L[start + i] += s * lg
            R[start + i] += s * rg

    def peak(self):
        return max(max(map(abs, self.l)), max(map(abs, self.r)))

    def save(self, path, length=None):
        """Write a 16-bit stereo WAV. Quiet mixes stay as they are; loud ones are scaled down so they never clip."""
        n = min(self.n, int((length if length else self.duration) * SR))
        pk = self.peak()
        g = 0.92 / pk if pk > 0.92 else 1.0
        out = array.array("h", [0]) * (n * 2)
        L, R = self.l, self.r
        for i in range(n):
            a, b = L[i] * g, R[i] * g
            out[2 * i] = int(max(-1.0, min(1.0, a)) * 32767)
            out[2 * i + 1] = int(max(-1.0, min(1.0, b)) * 32767)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(out.tobytes() if sys.byteorder == "little" else _swap(out))
        return path


def _swap(a):
    b = array.array("h", a)
    b.byteswap()
    return b.tobytes()


class _Sfx:
    """Synthesised sound effects. Each method returns a mono sample buffer: m.add(sfx.punch(), at=1.5)."""

    def __init__(self):
        self.rng = random.Random(11)

    def tone(self, freq=440.0, dur=0.2, wave="sine", vol=0.5, decay=5.0, sweep=None, attack=0.004):
        n = int(dur * SR)
        out = _buf(n)
        ph = 0.0
        for i in range(n):
            t = i / float(SR)
            f = freq if sweep is None else freq + (sweep - freq) * (t / dur)
            ph += 2 * math.pi * f / SR
            env = min(1.0, t / attack) * math.exp(-decay * t / dur)
            out[i] = _wave(wave, ph) * vol * env
        return out

    def noise(self, dur=0.1, vol=0.5, decay=6.0):
        n = int(dur * SR)
        out = _buf(n)
        r = self.rng
        for i in range(n):
            out[i] = (r.random() * 2 - 1) * vol * math.exp(-decay * i / float(n))
        return out

    @staticmethod
    def _sum(*parts):
        n = max(len(p) for p in parts)
        out = _buf(n)
        for p in parts:
            for i in range(len(p)):
                out[i] += p[i]
        return out

    def punch(self, power=1.0):
        return self._sum(self.tone(180, 0.16, "sine", 0.9 * power, 7, sweep=55), _lowpass(self.noise(0.07, 0.8 * power, 9), 0.35))

    def hit(self, power=1.0):
        return self._sum(self.tone(240, 0.12, "tri", 0.6 * power, 8, sweep=70), self.noise(0.09, 0.55 * power, 10), self.tone(90, 0.2, "sine", 0.7 * power, 6, sweep=40))

    def kick(self, power=1.0):
        return self._sum(self.tone(130, 0.22, "sine", 1.0 * power, 6, sweep=42), _lowpass(self.noise(0.05, 0.5 * power, 12), 0.4))

    def snare(self, power=1.0):
        return self._sum(self.noise(0.16, 0.7 * power, 6), self.tone(190, 0.1, "tri", 0.35 * power, 9))

    def hat(self, power=1.0, open_=False):
        d = 0.18 if open_ else 0.04
        n = self.noise(d, 0.35 * power, 7)
        return array.array("f", (n[i] - (n[i - 1] if i else 0.0) for i in range(len(n))))     # crude high-pass

    def whoosh(self, dur=0.3, vol=0.6):
        n = int(dur * SR)
        out = _buf(n)
        r = self.rng
        y = 0.0
        for i in range(n):
            u = i / float(n)
            a = 0.04 + 0.5 * math.sin(math.pi * u) ** 2
            y += a * ((r.random() * 2 - 1) - y)
            out[i] = y * vol * math.sin(math.pi * u) ** 1.5 * 2.2
        return out

    def ko(self):
        boom = self._sum(self.tone(120, 1.0, "sine", 1.0, 4, sweep=26), _lowpass(self.noise(0.9, 0.7, 4), 0.12))
        echo = _buf(len(boom) + int(0.35 * SR))
        for i in range(len(boom)):
            echo[i] += boom[i]
            echo[i + int(0.18 * SR)] += boom[i] * 0.35
            echo[i + int(0.35 * SR)] += boom[i] * 0.15
        return echo

    def explosion(self, dur=1.2):
        return self._sum(_lowpass(self.noise(dur, 0.9, 3.5), 0.18), self.tone(90, dur, "sine", 0.9, 3.5, sweep=24))

    def bell(self, freq=880.0, dur=1.0, vol=0.5):
        return self._sum(*[self.tone(freq * m, dur, "sine", vol * a, d) for m, a, d in ((1.0, 1.0, 4), (2.76, 0.5, 6), (5.4, 0.25, 9))])

    def ding(self, freq=1320.0):
        return self.tone(freq, 0.35, "sine", 0.5, 7)

    def pop(self):
        return self.tone(700, 0.08, "sine", 0.6, 7, sweep=200)

    def click(self):
        return self.tone(1800, 0.02, "square", 0.3, 9)

    def coin(self):
        a, b = self.tone(988, 0.07, "square", 0.3, 3), self.tone(1319, 0.28, "square", 0.3, 6)
        out = _buf(len(a) + len(b))
        for i in range(len(a)):
            out[i] += a[i]
        for i in range(len(b)):
            out[i + len(a)] += b[i]
        return out

    def error(self):
        return self._sum(self.tone(180, 0.25, "saw", 0.35, 3), self.tone(185, 0.25, "square", 0.2, 3))

    def laser(self, dur=0.25):
        return self.tone(1600, dur, "saw", 0.3, 5, sweep=200)

    def step(self, vol=0.35):
        return _lowpass(self.noise(0.06, vol, 9), 0.25)

    def crowd(self, dur=2.0, vol=0.3):
        n = int(dur * SR)
        out = _lowpass(self.noise(dur, vol, 0.0), 0.08)
        for i in range(n):
            u = i / float(n)
            out[i] *= min(1.0, u * 6) * min(1.0, (1 - u) * 3) * 3.0
        return out

    def riser(self, dur=1.5, vol=0.4):
        n = int(dur * SR)
        out = _buf(n)
        r = self.rng
        y = 0.0
        for i in range(n):
            u = i / float(n)
            y += (0.02 + 0.6 * u) * ((r.random() * 2 - 1) - y)
            out[i] = y * vol * u * 2
        return out

    def blip(self, freq=660.0, dur=0.08):
        return self.tone(freq, dur, "square", 0.25, 4)


sfx = _Sfx()


class _Music:
    """Looping-free background music made from synthesised drums, bass and pads. Returns a mono buffer: video.sound(music.beat(...), at=0)."""
    STYLES = ("fight", "chill", "8bit", "epic")

    def beat(self, bpm=120, bars=4, style="fight", key="A", seed=1, vol=0.5):
        if style not in self.STYLES:
            raise ValueError("style must be one of %s" % ", ".join(self.STYLES))
        spb = 60.0 / bpm
        m = Mixer(bars * 4 * spb)
        rnd = random.Random(seed)
        root = note_freq(key + "2")
        prog = [0, -4, 3, -2]                                  # i - VI - III - VII in the minor key
        kick, snare, hat, hat_o = sfx.kick(0.9), sfx.snare(0.6), sfx.hat(0.5), sfx.hat(0.5, True)
        scale = [0, 3, 5, 7, 10, 12]
        for bar in range(bars):
            r0 = root * 2 ** (prog[bar % 4] / 12.0)
            for b in range(4):
                t = (bar * 4 + b) * spb
                if style == "fight":
                    if b in (0, 2):
                        m.add(kick, t, 0.9)
                    if b == 2:
                        m.add(kick, t + spb * 0.75, 0.6)
                    if b in (1, 3):
                        m.add(snare, t, 0.8)
                    for e in range(2):
                        m.add(hat_o if (b == 3 and e == 1) else hat, t + e * spb / 2, 0.5 if e == 0 else 0.3)
                    for e in range(2):
                        f = r0 * (2 if (b + e) % 4 == 3 else 1)
                        m.add(sfx.tone(f, spb * 0.45, "saw", 0.22, 3), t + e * spb / 2, 0.8)
                elif style == "chill":
                    if b in (0, 2):
                        m.add(kick, t, 0.6)
                    if b in (1, 3):
                        m.add(snare, t, 0.35)
                    m.add(hat, t + spb / 2, 0.35)
                    if b == 0:
                        for k in (0, 3, 7):
                            m.add(sfx.tone(r0 * 2 * 2 ** (k / 12.0), spb * 4, "sine", 0.18, 1.2, attack=0.15), t)
                    if b in (0, 2):
                        m.add(sfx.tone(r0, spb * 1.8, "sine", 0.4, 2.5), t)
                elif style == "8bit":
                    for s16 in range(4):
                        n = scale[(bar + b * 2 + s16 + rnd.randrange(2)) % len(scale)]
                        m.add(sfx.tone(r0 * 4 * 2 ** (n / 12.0), spb / 4 * 0.9, "square", 0.14, 3), t + s16 * spb / 4)
                    m.add(sfx.tone(r0, spb * 0.9, "tri", 0.4, 2), t)
                    if b in (0, 2):
                        m.add(kick, t, 0.6)
                    if b in (1, 3):
                        m.add(sfx.noise(0.1, 0.4, 7), t)
                    m.add(sfx.noise(0.03, 0.2, 5), t + spb / 2)
                else:                                          # epic
                    if b == 0:
                        for k in (0, 7, 12, 15):
                            m.add(sfx.tone(r0 * 2 * 2 ** (k / 12.0), spb * 4, "saw", 0.09, 0.8, attack=0.4), t)
                        m.add(kick, t, 1.0)
                    if b == 2:
                        m.add(kick, t, 0.8)
                    if b in (1, 3):
                        m.add(sfx.tone(95, 0.3, "sine", 0.6, 5, sweep=60), t, 0.8)
                    for s16 in range(4):
                        n = scale[(s16 * 2 + b) % len(scale)]
                        m.add(sfx.tone(r0 * 4 * 2 ** (n / 12.0), spb / 4 * 0.9, "tri", 0.12, 3), t + s16 * spb / 4)
        mono = _buf(m.n)
        for i in range(m.n):
            mono[i] = (m.l[i] + m.r[i]) * 0.5 * vol
        return mono[: int(bars * 4 * spb * SR)]


music = _Music()


# ======================================================================================
# Video: scenes, transitions, render to MP4, automatic checks
# ======================================================================================
QUALITY = {
    "draft": dict(scale=0.375, ss=1, fps=15, crf=29, preset="ultrafast"),       # fast preview, 480x270
    "standard": dict(scale=2 / 3.0, ss=2, fps=30, crf=22, preset="veryfast"),    # 854x480, the default
    "hd": dict(scale=1.0, ss=2, fps=60, crf=20, preset="veryfast"),              # 1280x720
    "fhd": dict(scale=1.5, ss=2, fps=60, crf=19, preset="veryfast"),             # 1920x1080
}


def ffmpeg_path():
    return shutil.which("ffmpeg")


def _have_libx264():
    exe = ffmpeg_path()
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return False
    return "libx264" in out


def check_requirements():
    """What is installed: {'pillow': bool, 'ffmpeg': path or None, 'libx264': bool, 'ok': bool, 'fix': install hint}."""
    info = {"pillow": Image is not None, "ffmpeg": ffmpeg_path(), "python": sys.version.split()[0], "version": __version__}
    info["libx264"] = _have_libx264()
    info["ok"] = bool(info["pillow"] and info["ffmpeg"])
    fix = []
    if not info["pillow"]:
        fix.append("pkg install python-pillow   (Termux)   |   pip install pillow")
    if not info["ffmpeg"]:
        fix.append("pkg install ffmpeg   (Termux)   |   sudo apt install ffmpeg")
    info["fix"] = fix
    return info


def frame_stats(small, prev_small=None):
    """Cheap per-frame numbers from a small grayscale image: brightness, contrast and the change from the previous frame."""
    st = ImageStat.Stat(small)
    diff = ImageStat.Stat(ImageChops.difference(small, prev_small)).mean[0] if prev_small is not None else None
    return st.mean[0], st.stddev[0], diff


class Scene:
    def __init__(self, duration, draw, name=None, fade_in=0.0, fade_out=0.0, transition=None, trans_dur=0.5):
        self.duration, self.draw, self.name = float(duration), draw, name or getattr(draw, "__name__", "scene")
        self.fade_in, self.fade_out = float(fade_in), float(fade_out)
        self.transition = transition or "cut"
        self.trans_dur = float(trans_dur)
        self.start = 0.0
        try:
            ps = list(inspect.signature(draw).parameters.values())
            self.argc = 2 if any(p.kind == p.VAR_POSITIONAL for p in ps) else len(ps)
        except (TypeError, ValueError):
            self.argc = 2

    @property
    def end(self):
        return self.start + self.duration


_OVERLAP = ("crossfade", "slide_left", "slide_right", "slide_up", "slide_down", "wipe_left", "wipe_right", "zoom")


class Video:
    """A video made of scenes. v = Video(1280, 720, fps=30); v.scene(4.0, my_draw_function); v.render().

    Coordinates are always in the width x height you give here (1280x720 by default). quality ('draft', 'standard', 'hd', 'fhd') only changes
    the output resolution, frame rate and encoder effort, never your drawing code. The environment variable LUMO_VIDEO_QUALITY overrides it."""

    def __init__(self, width=1280, height=720, fps=30, quality=None, bg="#000000", seed=0, title=None):
        self.w, self.h, self.fps, self.bg, self.seed, self.title = int(width), int(height), int(fps), bg, seed, title
        self.quality = quality or "standard"
        self.scenes = []
        self.sounds = []
        self._fonts_ok = None

    # ---- building ----
    def scene(self, duration, draw, name=None, fade_in=0.0, fade_out=0.0, transition=None, trans_dur=0.5):
        """Add a scene: draw(c, t) is called for every frame with the Canvas and the seconds since the scene began.
        transition (how this scene follows the previous one): 'cut', 'fade', 'crossfade', 'slide_left/right/up/down', 'wipe_left/right', 'zoom'."""
        sc = Scene(duration, draw, name, fade_in, fade_out, transition, trans_dur)
        return self.add(sc)

    def add(self, sc):
        """Add a ready-made scene object (anything with .duration and .draw(c, t), such as a Fight)."""
        if not hasattr(sc, "transition"):
            sc.transition, sc.trans_dur, sc.fade_in, sc.fade_out = "cut", 0.5, 0.0, 0.0
        prev = self.scenes[-1] if self.scenes else None
        ov = min(sc.trans_dur, prev.duration, sc.duration) if prev and sc.transition in _OVERLAP else 0.0
        sc.start = (prev.end - ov) if prev else 0.0
        self.scenes.append(sc)
        if hasattr(sc, "on_add"):
            sc.on_add(self)
        return sc

    def sound(self, snd, at=0.0, vol=1.0, pan=0.0):
        """Add a sound effect or music buffer (see sfx and music) at a time in seconds."""
        self.sounds.append((snd, at, vol, pan))

    @property
    def duration(self):
        return max([s.end for s in self.scenes] or [0.0])

    # ---- one frame ----
    def _geometry(self, q):
        spec = QUALITY[q]
        pw = max(2, int(round(self.w * spec["scale"] / 2.0)) * 2)
        ph = max(2, int(round(self.h * spec["scale"] / 2.0)) * 2)
        return pw, ph, spec["ss"], min(self.fps, spec["fps"])

    def _canvas(self, sc, T, frame, geo, fps):
        pw, ph, ss, _ = geo
        c = Canvas(self.w, self.h, pw, ph, ss, self.bg)
        c.t, c.T, c.frame, c.fps, c.seed = T - sc.start, T, frame, fps, self.seed
        return c

    def _draw_scene(self, sc, T, frame, geo, fps):
        c = self._canvas(sc, T, frame, geo, fps)
        local = max(0.0, T - sc.start)
        if getattr(sc, "argc", 2) == 1:
            sc.draw(c)
        else:
            sc.draw(c, local)
        fi = sc.fade_in + (sc.trans_dur / 2.0 if sc.transition == "fade" else 0.0)
        fo = sc.fade_out
        nxt = self._next(sc)
        if nxt is not None and nxt.transition == "fade":
            fo = max(fo, nxt.trans_dur / 2.0)
        if fi > 0 and local < fi:
            c.tint("#000000", 1.0 - local / fi)
        if fo > 0 and local > sc.duration - fo:
            c.tint("#000000", (local - (sc.duration - fo)) / fo)
        return c

    def _next(self, sc):
        i = self.scenes.index(sc)
        return self.scenes[i + 1] if i + 1 < len(self.scenes) else None

    def frame_at(self, T, quality=None, fps=None):
        """The frame at time T as a PIL image (RGB), without any encoding. Handy for checking a look: v.frame_at(2.5).save('look.png')."""
        if Image is None:
            raise RuntimeError("Pillow is not installed: pkg install python-pillow  (or: pip install pillow)")
        if not self.scenes:
            raise RuntimeError("the video has no scenes yet: call v.scene(duration, draw_function)")
        q = quality or self.quality
        geo = self._geometry(q)
        fps = fps or geo[3]
        T = clamp(T, 0.0, max(0.0, self.duration - 1e-6))
        frame = int(round(T * fps))
        active = [s for s in self.scenes if s.start <= T < s.end] or [self.scenes[-1]]
        if len(active) == 1:
            return self._draw_scene(active[0], T, frame, geo, fps).to_image()
        a, b = active[0], active[-1]
        ia = self._draw_scene(a, T, frame, geo, fps).to_image()
        ib = self._draw_scene(b, T, frame, geo, fps).to_image()
        return _blend(ia, ib, clamp((T - b.start) / max(1e-6, b.trans_dur)), b.transition)

    def save_frame(self, T, path, quality=None):
        self.frame_at(T, quality).save(path)
        return path

    # ---- audio ----
    def _audio_file(self, tmpdir, duration):
        if not self.sounds or os.environ.get("LUMO_VIDEO_NOAUDIO"):
            return None
        m = Mixer(duration)
        for snd, at, vol, pan in self.sounds:
            m.add(snd, at, vol, pan)
        return m.save(os.path.join(tmpdir, "audio.wav"), length=duration)

    # ---- checks without encoding ----
    def dry_run(self, frames=8, quality="draft"):
        """Draw a few frames spread over the video (no ffmpeg) and return the same checks render() reports. Use it to test quickly."""
        n = max(2, frames)
        geo = self._geometry(quality)
        prev, stats = None, []
        for i in range(n):
            T = self.duration * i / float(n - 1) if n > 1 else 0.0
            small = self.frame_at(T, quality).convert("L").resize((48, 27), Image.BOX)
            stats.append(frame_stats(small, prev))
            prev = small
        return _qa(stats, self.duration, bool(self.sounds), sampled=True)

    # ---- render ----
    def render(self, path=None, quality=None, progress=True):
        """Render the whole video to an MP4 (H.264 yuv420p + AAC, plays in every player). Returns a report dict and prints it as one
        'LUMO_VIDEO_REPORT {...}' line. The path: $LUMO_VIDEO_OUT if set, else the path you pass, else videos/<script name>.mp4."""
        if Image is None:
            raise RuntimeError("Pillow is not installed: pkg install python-pillow  (or: pip install pillow)")
        if not self.scenes:
            raise RuntimeError("the video has no scenes yet: call v.scene(duration, draw_function) before v.render()")
        q = os.environ.get("LUMO_VIDEO_QUALITY") or quality or self.quality
        if q not in QUALITY:
            raise ValueError("quality must be one of: %s" % ", ".join(QUALITY))
        out = os.path.abspath(os.environ.get("LUMO_VIDEO_OUT") or path or _default_out())      # the environment wins: the render_video tool sets it when you ask for a path
        os.makedirs(os.path.dirname(out), exist_ok=True)
        geo = self._geometry(q)
        pw, ph, ss, fps = geo
        total = max(1, int(math.ceil(self.duration * fps - 1e-9)))
        ff = ffmpeg_path()
        t0 = time.time()
        if not ff and os.environ.get("LUMO_VIDEO_REQUIRE_FFMPEG"):
            raise RuntimeError("ffmpeg is not installed: pkg install ffmpeg  (Termux)  |  sudo apt install ffmpeg")
        tmp = tempfile.mkdtemp(prefix="lumovideo_")
        try:
            gif = ff is None
            if gif:
                out = os.path.splitext(out)[0] + ".gif"
                print("  ! ffmpeg is not installed, writing a GIF instead (no sound). For a real MP4: pkg install ffmpeg", flush=True)
            audio = None if gif else self._audio_file(tmp, self.duration)
            proc = None
            if not gif:
                enc = ["-c:v", "libx264", "-preset", QUALITY[q]["preset"], "-crf", str(QUALITY[q]["crf"])] if _have_libx264() else ["-c:v", "mpeg4", "-q:v", "4"]
                cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (pw, ph), "-r", str(fps), "-i", "-"]
                if audio:
                    cmd += ["-i", audio]
                cmd += enc + ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", "%.3f" % self.duration]
                if audio:
                    cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "44100"]
                cmd.append(out)
                errf = open(os.path.join(tmp, "ffmpeg.log"), "wb")
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errf)
            frames, stats, prev, last_print = [], [], None, 0.0
            for i in range(total):
                T = i / float(fps)
                img = self.frame_at(T, q, fps)
                small = img.convert("L").resize((48, 27), Image.BOX)
                stats.append(frame_stats(small, prev))
                prev = small
                if proc is not None:
                    try:
                        proc.stdin.write(img.tobytes())
                    except (BrokenPipeError, OSError):
                        break
                else:
                    frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=128))
                if progress and (time.time() - last_print > 0.5 or i == total - 1):
                    last_print = time.time()
                    el = last_print - t0
                    rate = (i + 1) / max(el, 1e-6)
                    sys.stdout.write("\r  rendering %3d%% · frame %d/%d · %.1f fps · ~%ds left   " % (100 * (i + 1) // total, i + 1, total, rate, (total - i - 1) / max(rate, 1e-6)))
                    sys.stdout.flush()
            if progress:
                sys.stdout.write("\n")
            if proc is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
                code = proc.wait()
                errf.close()
                if code != 0 or not os.path.exists(out) or os.path.getsize(out) < 100:
                    log = open(os.path.join(tmp, "ffmpeg.log"), "rb").read().decode("utf-8", "replace")[-1500:]
                    raise RuntimeError("ffmpeg failed (exit %s): %s" % (code, log.strip() or "no message"))
            else:
                frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        rep = {"file": out, "format": "gif" if gif else "mp4", "width": pw, "height": ph, "fps": fps, "frames": total, "duration": round(total / float(fps), 2),
               "quality": q, "audio": bool(audio), "size_kb": int(os.path.getsize(out) / 1024), "render_s": round(time.time() - t0, 1),
               "qa": _qa(stats, self.duration, bool(audio))}
        print("LUMO_VIDEO_REPORT " + json.dumps(rep), flush=True)
        return rep


def _qa(stats, duration, has_audio, sampled=False):
    n = len(stats)
    bright = [s[0] for s in stats]
    k = max(1, int(round(n * 0.04))) if n >= 5 else 0                      # fades to and from black are normal at the very start and end
    core = stats[k:n - k] if n - 2 * k >= 1 else stats
    blank = sum(1 for s in core if s[1] < 1.5)
    diffs = [s[2] for s in stats if s[2] is not None]
    frozen = sum(1 for d in diffs if d < 0.05)
    motion = sum(diffs) / len(diffs) if diffs else 0.0
    qa = {"blank_frames": blank, "frozen_ratio": round(frozen / float(len(diffs)), 2) if diffs else 0.0, "motion": round(motion, 2),
          "brightness": round(sum(bright) / n, 1) if n else 0.0, "dark_frames": sum(1 for s in core if s[0] < 8), "sampled": sampled, "warnings": []}
    w = qa["warnings"]
    if blank:
        w.append("%d frame(s) show a flat colour (nothing drawn): check scene timing and that every scene draws something" % blank)
    if diffs and qa["frozen_ratio"] > 0.5 and duration > 2 and not sampled:
        w.append("more than half of the frames do not change: add motion or shorten the video")
    if diffs and motion < 0.05 and duration > 1:
        w.append("almost no motion between frames")
    if n and qa["brightness"] < 6:
        w.append("the picture is almost black: check colours and that the background is drawn")
    if duration < 0.5:
        w.append("the video is shorter than half a second")
    return qa


def _default_out():
    main = sys.modules.get("__main__")
    name = os.path.splitext(os.path.basename(getattr(main, "__file__", "") or "video"))[0] or "video"
    return os.path.join("videos", name + ".mp4")


def _blend(a, b, p, kind):
    w, h = a.size
    if kind == "crossfade":
        return Image.blend(a, b, p)
    if kind.startswith("slide_"):
        d = kind.split("_")[1]
        out = Image.new("RGB", (w, h))
        dx = int(w * p) * (-1 if d == "left" else 1 if d == "right" else 0)
        dy = int(h * p) * (-1 if d == "up" else 1 if d == "down" else 0)
        out.paste(a, (dx, dy))
        out.paste(b, (dx + (w if d == "left" else -w if d == "right" else 0), dy + (h if d == "up" else -h if d == "down" else 0)))
        return out
    if kind.startswith("wipe_"):
        mask = Image.new("L", (w, h), 0)
        edge = int(w * p) if kind.endswith("right") else int(w * (1 - p))
        ImageDraw.Draw(mask).rectangle([0, 0, edge, h] if kind.endswith("right") else [edge, 0, w, h], fill=255)
        return Image.composite(b, a, mask)
    if kind == "zoom":
        z = 1.0 + 0.35 * p
        cw, ch = int(w / z), int(h / z)
        zoomed = a.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2)).resize((w, h), Image.BILINEAR)
        return Image.blend(zoomed, b, p)
    return b


class Timeline:
    """Name the parts of a scene once, then ask 'how far along is this part?'.
    tl = Timeline(); tl.add('title', 0, 1.5); tl.add('bars', 1.2, 4); ... p = tl.p('title', t)  # 0..1 progress, held at 0 or 1 outside"""

    def __init__(self):
        self.items = {}

    def add(self, name, start, dur):
        self.items[name] = (float(start), float(start) + float(dur))
        return self

    def p(self, name, t):
        a, b = self.items[name]
        return clamp((t - a) / (b - a)) if b > a else 1.0

    def active(self, name, t):
        a, b = self.items[name]
        return a <= t < b

    @property
    def end(self):
        return max(b for a, b in self.items.values())


# ======================================================================================
# Stickman: skeleton, poses, moves
# ======================================================================================
# A pose is a dict of angles in degrees. Limbs: 0 = hanging straight down, 90 = pointing forward, 180 = straight up, negative = backward.
#   lean: torso lean (+ forward)  head: head tilt  lua/lfa: far (rear) upper arm / forearm  rua/rfa: near (lead) upper arm / forearm
#   lth/lsh: far thigh / shin  rth/rsh: near thigh / shin  roll: rotate the whole body (+ forward)  hx: hip shift forward (px)
#   y: hip height above the ground (px; if missing the lowest foot stands on the ground)  lift: extra height (jumps)
_BASE_POSE = dict(lean=6, head=0, lua=30, lfa=120, rua=50, rfa=130, lth=-30, lsh=8, rth=35, rsh=-5, roll=0, hx=0, lift=0)
POSES = {
    "guard": {},
    "idle": dict(lean=3, lua=14, lfa=40, rua=22, rfa=48, lth=-12, lsh=3, rth=14, rsh=-3),
    "crouch": dict(lean=22, lua=40, lfa=130, rua=60, rfa=140, lth=-55, lsh=55, rth=62, rsh=-45, hx=-6),
    "jab_wind": dict(lean=3, rua=24, rfa=150, lua=36, lfa=126),
    "jab": dict(lean=14, rua=90, rfa=92, lua=36, lfa=126, rth=42, rsh=-8, lth=-34, lsh=6, hx=8),
    "cross_wind": dict(lean=-4, lua=26, lfa=150, lth=-36, lsh=10, hx=-6),
    "cross": dict(lean=24, lua=92, lfa=94, rua=62, rfa=132, lth=-44, lsh=24, rth=40, rsh=-12, hx=14),
    "upper_wind": dict(lean=14, lua=15, lfa=60, rua=45, rfa=125, lth=-50, lsh=46, rth=55, rsh=-35, hx=-6),
    "uppercut": dict(lean=2, lua=150, lfa=172, rua=48, rfa=128, lth=-18, lsh=0, rth=22, rsh=-4, hx=10),
    "kick_chamber": dict(lean=-10, rth=88, rsh=8, lth=-6, lsh=0, lua=40, lfa=100, rua=55, rfa=125),
    "kick_front": dict(lean=-12, rth=92, rsh=92, lth=-6, lsh=0, lua=50, lfa=110, rua=60, rfa=130, hx=6),
    "round_chamber": dict(lean=-16, rth=-4, rsh=-6, lth=82, lsh=14, lua=65, lfa=150, rua=70, rfa=150),
    "round_kick": dict(lean=-34, rth=-2, rsh=-4, lth=96, lsh=92, lua=72, lfa=150, rua=84, rfa=165, hx=4),
    "sweep_wind": dict(lean=22, rth=40, rsh=-8, lth=-58, lsh=60, lua=20, lfa=60, rua=30, rfa=80),
    "sweep": dict(lean=28, lth=-10, lsh=2, rth=70, rsh=76, lua=-10, lfa=40, rua=60, rfa=110, y=44),
    "flying": dict(lean=-18, rth=60, rsh=82, lth=86, lsh=40, lua=70, lfa=120, rua=100, rfa=130, lift=70),
    "block": dict(lean=14, lua=64, lfa=165, rua=70, rfa=170, lth=-34, lsh=14, rth=38, rsh=-10),
    "duck": dict(lean=26, lua=40, lfa=140, rua=55, rfa=145, lth=-62, lsh=66, rth=70, rsh=-56, hx=-4),
    "dodge": dict(lean=-18, head=-6, lua=28, lfa=105, rua=40, rfa=120, lth=-24, lsh=2, rth=20, rsh=-14, hx=-10),
    "hit_head": dict(lean=-22, head=-26, lua=70, lfa=70, rua=60, rfa=40, lth=-30, lsh=6, rth=26, rsh=-4, hx=-10),
    "hit_body": dict(lean=30, head=14, lua=16, lfa=50, rua=20, rfa=70, lth=-30, lsh=10, rth=36, rsh=-10, hx=-4),
    "stagger": dict(lean=-8, head=-8, lua=60, lfa=40, rua=30, rfa=20, lth=-38, lsh=14, rth=20, rsh=-24, hx=-6),
    "fall": dict(lean=-40, head=-20, lua=120, lfa=100, rua=140, rfa=120, lth=-20, lsh=10, rth=50, rsh=20, roll=-40, lift=24),
    "lying": dict(lean=0, head=0, lua=-50, lfa=-70, rua=-30, rfa=-60, lth=-6, lsh=0, rth=14, rsh=-14, roll=-90, y=7),
    "kneel": dict(lean=14, lua=20, lfa=70, rua=36, rfa=80, lth=-80, lsh=90, rth=86, rsh=-6, y=34),
    "victory": dict(lean=-6, head=-10, lua=162, lfa=176, rua=150, rfa=170, lth=-18, lsh=4, rth=20, rsh=-4),
    "taunt": dict(lean=-8, head=-8, lua=20, lfa=40, rua=130, rfa=60, lth=-20, lsh=4, rth=20, rsh=-4),
    "bow": dict(lean=40, head=10, lua=10, lfa=30, rua=14, rfa=30, lth=-8, lsh=0, rth=10, rsh=0),
    "jump": dict(lean=0, lua=60, lfa=140, rua=70, rfa=150, lth=-30, lsh=50, rth=40, rsh=60, lift=60),
}
for _k in list(POSES):
    POSES[_k] = dict(_BASE_POSE, **POSES[_k])

_NUM_KEYS = ("lean", "head", "lua", "lfa", "rua", "rfa", "lth", "lsh", "rth", "rsh", "roll", "hx", "lift")
_LIMBS = dict(thigh=40.0, shin=40.0, torso=56.0, neck=7.0, head=15.0, upper=30.0, fore=28.0)


def resolve_pose(p, scale=1.0):
    """A pose given by name or dict -> a complete pose with a numeric hip height 'y' (px at scale 1)."""
    q = dict(POSES[p]) if isinstance(p, str) else dict(_BASE_POSE, **p)
    if "y" not in q:
        drop = max(_LIMBS["thigh"] * math.cos(math.radians(q["lth"])) + _LIMBS["shin"] * math.cos(math.radians(q["lsh"])),
                   _LIMBS["thigh"] * math.cos(math.radians(q["rth"])) + _LIMBS["shin"] * math.cos(math.radians(q["rsh"])))
        q["y"] = drop + q.get("lift", 0.0)
    return q


def blend_pose(a, b, t, easing="in_out_cubic"):
    e = ease(t, easing)
    out = {k: a[k] + (b[k] - a[k]) * e for k in _NUM_KEYS + ("y",)}
    return out


class Move:
    """A scripted action: keyframed poses over time plus what it does to the opponent when it lands."""

    def __init__(self, name, dur, keys, hit=None, reach=0, dmg=0, kind="body", limb="hand_r", snd="punch", lunge=0, knock=26, launch=False, travel=0):
        self.name, self.dur, self.hit, self.reach, self.dmg, self.kind, self.limb, self.snd = name, dur, hit, reach, dmg, kind, limb, snd
        self.lunge, self.knock, self.launch, self.travel = lunge, knock, launch, travel
        self.keys = [(k[0], resolve_pose(k[1]), k[2] if len(k) > 2 else "in_out_cubic") for k in keys]

    def pose_at(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        for i in range(1, len(ks)):
            if t < ks[i][0]:
                a, b = ks[i - 1], ks[i]
                return blend_pose(a[1], b[1], (t - a[0]) / (b[0] - a[0]), b[2])
        return ks[-1][1]

    def offset(self, t):
        """Forward body travel (px) at time t into the move: a lunge toward the hit and back."""
        if not self.lunge and not self.travel:
            return 0.0
        peak = self.hit if self.hit else self.dur * 0.5
        if self.travel:                                             # flying moves keep going until the end
            return self.travel * ease(t / max(self.dur, 1e-6), "in_out_quad")
        if t <= peak:
            return self.lunge * ease(t / peak, "out_quad")
        return self.lunge * (1 - ease((t - peak) / max(self.dur - peak, 1e-6), "in_out_quad"))


MOVES = {m.name: m for m in [
    Move("jab", 0.40, [(0, "guard"), (0.07, "jab_wind"), (0.15, "jab", "out_quad"), (0.24, "jab"), (0.40, "guard")], hit=0.15, reach=74, dmg=6, kind="head", limb="hand_r", snd="punch", lunge=14, knock=18),
    Move("cross", 0.52, [(0, "guard"), (0.10, "cross_wind"), (0.20, "cross", "out_quad"), (0.30, "cross"), (0.52, "guard")], hit=0.20, reach=84, dmg=9, kind="head", limb="hand_l", snd="punch", lunge=22, knock=30),
    Move("uppercut", 0.62, [(0, "guard"), (0.14, "upper_wind"), (0.26, "uppercut", "out_quad"), (0.38, "uppercut"), (0.62, "guard")], hit=0.26, reach=66, dmg=12, kind="head", limb="hand_l", snd="hit", lunge=12, knock=34, launch=True),
    Move("front_kick", 0.66, [(0, "guard"), (0.14, "kick_chamber"), (0.26, "kick_front", "out_quad"), (0.38, "kick_front"), (0.66, "guard")], hit=0.26, reach=100, dmg=10, kind="body", limb="foot_r", snd="kick", lunge=12, knock=40),
    Move("round_kick", 0.80, [(0, "guard"), (0.22, "round_chamber"), (0.34, "round_kick", "out_quad"), (0.46, "round_kick"), (0.80, "guard")], hit=0.34, reach=104, dmg=14, kind="head", limb="foot_l", snd="kick", lunge=16, knock=60),
    Move("sweep", 0.64, [(0, "guard"), (0.13, "sweep_wind"), (0.25, "sweep", "out_quad"), (0.40, "sweep"), (0.64, "guard")], hit=0.25, reach=92, dmg=7, kind="legs", limb="foot_r", snd="kick", lunge=10, knock=30),
    Move("flying_kick", 0.95, [(0, "guard"), (0.16, "crouch"), (0.34, "flying", "out_quad"), (0.58, "flying"), (0.80, "kick_chamber"), (0.95, "guard")], hit=0.5, reach=112, dmg=16, kind="body", limb="foot_l", snd="kick", travel=120, knock=70, launch=True),
    Move("block", 0.55, [(0, "guard"), (0.08, "block"), (0.40, "block"), (0.55, "guard")], kind="body"),
    Move("duck", 0.55, [(0, "guard"), (0.10, "duck"), (0.40, "duck"), (0.55, "guard")]),
    Move("dodge", 0.50, [(0, "guard"), (0.10, "dodge"), (0.30, "dodge"), (0.50, "guard")], travel=0),
    Move("taunt", 1.00, [(0, "guard"), (0.15, "taunt"), (0.50, "taunt"), (0.65, "taunt"), (1.0, "guard")]),
    Move("bow", 1.00, [(0, "guard"), (0.30, "bow"), (0.65, "bow"), (1.0, "guard")]),
    Move("jump", 0.70, [(0, "guard"), (0.12, "crouch"), (0.30, "jump", "out_quad"), (0.50, "jump"), (0.70, "guard")]),
    # reactions
    Move("hit_head", 0.50, [(0, "guard"), (0.05, "hit_head", "out_quad"), (0.18, "hit_head"), (0.50, "guard")]),
    Move("hit_body", 0.50, [(0, "guard"), (0.05, "hit_body", "out_quad"), (0.18, "hit_body"), (0.50, "guard")]),
    Move("stagger", 0.70, [(0, "guard"), (0.08, "stagger", "out_quad"), (0.30, "stagger"), (0.70, "guard")]),
    Move("blocked", 0.40, [(0, "block"), (0.06, "block"), (0.40, "block")]),
    Move("launch", 0.85, [(0, "guard"), (0.06, "hit_head", "out_quad"), (0.26, {**POSES["fall"], "lift": 90, "roll": -30}, "out_quad"), (0.56, "fall", "in_quad"), (0.85, "lying", "out_quad")]),
    Move("knockdown", 0.80, [(0, "guard"), (0.06, "hit_head", "out_quad"), (0.34, "fall", "in_out_quad"), (0.80, "lying", "out_bounce")]),
    Move("getup", 1.00, [(0, "lying"), (0.45, "kneel", "in_out_quad"), (1.0, "guard", "out_quad")]),
    Move("victory", 1.40, [(0, "guard"), (0.25, "victory", "out_back"), (1.40, "victory")]),
]}


def _walk_pose(phase, run=False):
    """Walk or run cycle: phase in cycles (1.0 = one full stride)."""
    s = math.sin(phase * 2 * math.pi)
    c = math.cos(phase * 2 * math.pi)
    A = 42.0 if run else 26.0
    bend = 70.0 if run else 30.0
    p = dict(_BASE_POSE)
    p["rth"] = A * s + 6
    p["lth"] = -A * s + 6
    p["rsh"] = p["rth"] - bend * max(0.0, c) * 1.0
    p["lsh"] = p["lth"] - bend * max(0.0, -c) * 1.0
    p["lean"] = 16 if run else 8
    p["rua"] = (-A * 1.2 * s + 30) if run else (-A * 0.9 * s + 22)
    p["lua"] = (A * 1.2 * s + 30) if run else (A * 0.9 * s + 22)
    p["rfa"] = p["rua"] + (80 if run else 30)
    p["lfa"] = p["lua"] + (80 if run else 30)
    return resolve_pose(p)


class Stick:
    """A stickman. Stick('RYU', color='#4aa3ff', headband='#ffffff', gloves='#ff3b3b').
    You rarely draw it yourself: Fight does it. Direct use: stick.draw(c, x, ground, facing, pose, t) with pose a name from POSES or a dict."""

    def __init__(self, name="FIGHTER", color="#4aa3ff", scale=1.0, line=8.0, headband=None, gloves=None, outline=True, belt=None, max_hp=100.0, weapon=None):
        self.name, self.color, self.scale, self.line, self.headband, self.gloves, self.outline, self.belt, self.max_hp = \
            name, color, scale, line, headband, gloves, outline, belt, float(max_hp)
        if weapon not in (None, "sword", "staff", "knife"):
            raise ValueError("weapon must be None, 'sword', 'staff' or 'knife' (weapons are cosmetic: the same strikes play)")
        self.weapon = weapon

    def joints(self, x, ground, facing, pose, t=0.0):
        """World positions of the joints for a resolved pose: hip, chest, neck, head, hand_l/hand_r, foot_l/foot_r, elbow/knee points."""
        q = pose if "y" in pose else resolve_pose(pose)
        L, s = _LIMBS, self.scale
        r = math.radians(q["roll"])
        cr, sr = math.cos(r), math.sin(r)

        def loc(lx, ly):                                              # local (y up, x forward) -> world
            rx, ry = lx * cr + ly * sr, -lx * sr + ly * cr
            return (x + facing * (q["hx"] + rx) * s, ground - (q["y"] + ry) * s)

        def vec(ang, ln, base):
            a = math.radians(ang)
            return (base[0] + math.sin(a) * ln, base[1] - math.cos(a) * ln)
        hip = (0.0, 0.0)
        lean = math.radians(q["lean"])
        sh = (math.sin(lean) * L["torso"], math.cos(lean) * L["torso"])
        ha = math.radians(q["lean"] + q["head"])
        head = (sh[0] + math.sin(ha) * (L["neck"] + L["head"]), sh[1] + math.cos(ha) * (L["neck"] + L["head"]))
        J = {"hip": hip, "chest": sh, "head": head}
        for side in ("l", "r"):
            e = vec(q[side + "ua"], L["upper"], sh)
            h = vec(q[side + "fa"], L["fore"], e)
            k = vec(q[side + "th"], L["thigh"], hip)
            f = vec(q[side + "sh"], L["shin"], k)
            fa = math.radians(q[side + "sh"])
            toe = (f[0] + math.cos(fa) * 11.0, f[1] + math.sin(fa) * 11.0)
            J.update({"elbow_" + side: e, "hand_" + side: h, "knee_" + side: k, "foot_" + side: f, "toe_" + side: toe})
        return {k: loc(*v) for k, v in J.items()}

    def draw(self, c, x, ground, facing, pose, t=0.0, trail=None, alpha=1.0):
        """Draw the figure standing at x on the ground line. trail: list of earlier poses (resolved) drawn as pale afterimages. Returns the joints."""
        q = pose if isinstance(pose, dict) and "y" in pose else resolve_pose(pose)
        s = self.scale
        col, dark = rgb(self.color), shade(self.color, -0.38)
        edge = shade(self.color, -0.85)
        lw = self.line * s
        # shadow on the ground
        h = q["y"] + q.get("lift", 0) * 0
        sw = (34 - min(14.0, max(0.0, (q["y"] - 76) * 0.25))) * s
        c.ellipse(x + facing * q["hx"] * s * 0.5, ground + 3, sw, 7 * s, fill=(0, 0, 0), alpha=0.35)
        if trail:
            for tp, k in trail:
                jt = self.joints(x, ground, facing, tp, t)
                ghost = mix(self.color, "#ffffff", 0.55)
                for a, b in (("hip", "chest"), ("elbow_r", "hand_r"), ("chest", "elbow_r"), ("hip", "knee_r"), ("knee_r", "foot_r"),
                             ("chest", "elbow_l"), ("elbow_l", "hand_l"), ("hip", "knee_l"), ("knee_l", "foot_l")):
                    c.line(jt[a][0], jt[a][1], jt[b][0], jt[b][1], mix(ghost, "#000000", k), lw * 0.55)
        J = self.joints(x, ground, facing, q, t)

        def limb(a, b, d, width, color):
            pts = [J[a], J[b], J[d]]
            if self.outline:
                c.polyline(pts, edge, width + 4 * s)
            c.polyline(pts, color, width)

        def seg(a, b, width, color):
            if self.outline:
                c.line(J[a][0], J[a][1], J[b][0], J[b][1], edge, width + 4 * s)
            c.line(J[a][0], J[a][1], J[b][0], J[b][1], color, width)
        # far limbs, torso, near limbs, head
        limb("chest", "elbow_l", "hand_l", lw * 0.92, dark)
        limb("hip", "knee_l", "foot_l", lw * 1.0, dark)
        seg("foot_l", "toe_l", lw * 0.9, dark)
        seg("hip", "chest", lw * 1.15, col)
        limb("hip", "knee_r", "foot_r", lw * 1.0, col)
        seg("foot_r", "toe_r", lw * 0.9, col)
        if self.belt:
            bx, by = J["hip"]
            c.circle(bx, by, lw * 0.75, fill=self.belt)
        hr = _LIMBS["head"] * s
        hx, hy = J["head"]
        if self.outline:
            c.circle(hx, hy, hr + 2.5 * s, fill=edge)
        c.circle(hx, hy, hr, fill=col)
        ex = hx + facing * hr * 0.42
        c.circle(ex, hy - hr * 0.12, max(1.6, hr * 0.14), fill="#ffffff")
        if self.headband:
            by = hy - hr * 0.42
            c.line(hx - facing * hr * 0.95, by, hx + facing * hr * 0.95, by, self.headband, 4 * s, cap=False)
            sway = math.sin(t * 9.0) * 5 * s
            for i, off in enumerate((0.0, 7.0)):
                c.polyline([(hx - facing * hr * 0.95, by), (hx - facing * (hr + 14 * s), by + off * s + sway), (hx - facing * (hr + 28 * s), by + off * s * 1.8 + sway * 1.6)],
                           self.headband, 3.2 * s)
        limb("chest", "elbow_r", "hand_r", lw * 0.92, col)
        for side in ("l", "r"):
            gx, gy = J["hand_" + side]
            if self.gloves:
                if self.outline:
                    c.circle(gx, gy, 9.5 * s, fill=edge)
                c.circle(gx, gy, 7.5 * s, fill=self.gloves)
            else:
                c.circle(gx, gy, 4.2 * s, fill=col if side == "r" else dark)
        if self.weapon:
            ex, ey = J["elbow_r"]
            hx2, hy2 = J["hand_r"]
            dx, dy = hx2 - ex, hy2 - ey
            n = math.hypot(dx, dy) or 1.0
            ux, uy = dx / n, dy / n
            ln = {"sword": 66.0, "staff": 124.0, "knife": 28.0}[self.weapon] * s
            tip, base = (hx2 + ux * ln, hy2 + uy * ln), (hx2 - ux * 12 * s, hy2 - uy * 12 * s)
            blade = "#e8eef7" if self.weapon != "staff" else "#b9843f"
            c.line(base[0], base[1], tip[0], tip[1], edge, 8 * s)
            c.line(base[0], base[1], tip[0], tip[1], blade, 4.5 * s)
            if self.weapon != "staff":
                c.line(hx2 - uy * 9 * s, hy2 + ux * 9 * s, hx2 + uy * 9 * s, hy2 - ux * 9 * s, "#caa24a", 5 * s)
        return J


# ======================================================================================
# Stage: backgrounds for characters (parallax, drawn in world coordinates)
# ======================================================================================
class Stage:
    """A procedural background with depth. Stage('dojo' | 'city_night' | 'sunset' | 'arena' | 'forest' | 'plain'). Fight draws it for you;
    to use it in your own scene call stage.draw(c, t) after c.camera(...). Everything is deterministic for a given seed."""
    KINDS = ("dojo", "city_night", "sunset", "arena", "forest", "plain")

    def __init__(self, kind="dojo", width=1280, height=720, ground=None, seed=3):
        if kind not in self.KINDS:
            raise ValueError("stage must be one of: %s" % ", ".join(self.KINDS))
        self.kind, self.W, self.H, self.g = kind, width, height, ground or int(height * 0.78)
        r = random.Random(seed)
        self.stars = [(r.uniform(-300, width + 300), r.uniform(0, self.g * 0.65), r.uniform(1.0, 2.6), r.random()) for _ in range(80)]

        def skyline(n, lo, hi, wmin, wmax):
            out, x = [], -700.0
            while x < width + 900:
                w = r.uniform(wmin, wmax)
                h = r.uniform(lo, hi)
                out.append((x, w, h, [(r.random() < 0.38) for _ in range(int(w // 22) * int(h // 30))]))
                x += w + r.uniform(0, 14)
            return out
        self.far = skyline(0, 120, 330, 70, 150)
        self.near = skyline(0, 160, 420, 110, 210)
        self.crowd = [(x, r.uniform(0.85, 1.15), r.choice(("#2a2f45", "#33283d", "#243a4a", "#3d3030", "#2e3a2a"))) for x in range(-600, width + 800, 26)]
        self.trees = [(r.uniform(-700, width + 900), r.uniform(0.8, 1.5), r.random()) for _ in range(26)]
        self.clouds = [(r.uniform(-500, width + 700), r.uniform(50, self.g * 0.45), r.uniform(120, 300), r.uniform(0.2, 0.6)) for _ in range(9)]

    # ---- helpers ----
    def _floor(self, c, top, bottom, line=None, planks=None):
        g = self.g
        c.rect(-3000, g, 7000, 900, fill=top)
        c.rect(-3000, g + 70, 7000, 900, fill=bottom)
        if line:
            c.line(-3000, g, 4000, g, line, 4, cap=False)
        if planks:
            for dy, w in ((26, 2), (58, 2), (102, 3), (170, 3), (260, 4)):
                c.line(-3000, g + dy, 4000, g + dy, planks, w, cap=False)

    def draw(self, c, t=0.0):
        getattr(self, "_" + self.kind)(c, t)

    # ---- kinds ----
    def _plain(self, c, t):
        c.background("#1a2236", "#2c3a5e")
        self._floor(c, "#2f3b57", "#252f47", "#7f93c4")

    def _dojo(self, c, t):
        g = self.g
        c.background("#3a2a22", "#6b4a35")
        with c.parallax(0.45):
            for x in range(-700, 2000, 200):                                       # shoji panels
                c.rect(x, g - 340, 190, 330, fill="#e9dcc0", outline="#5b3c28", width=5)
                for gx in range(1, 4):
                    c.line(x + gx * 47.5, g - 340, x + gx * 47.5, g - 10, "#5b3c28", 3, cap=False)
                for gy in range(1, 5):
                    c.line(x, g - 340 + gy * 66, x + 190, g - 340 + gy * 66, "#5b3c28", 3, cap=False)
            c.rect(-700, g - 360, 2700, 24, fill="#4a2f20")
        with c.parallax(0.62):
            c.rect(560, g - 330, 150, 210, fill="#a52a2a", outline="#3a1c14", width=5)             # banner
            c.circle(635, g - 225, 46, fill="#f5e9d0")
            c.line(595, g - 250, 675, g - 200, "#a52a2a", 10)
            for lx in (240, 1000):
                c.line(lx, g - 360, lx, g - 300, "#3a1c14", 4)
                c.glow(lx, g - 270, 90, "#ffb347", 0.9)
                c.rect(lx - 22, g - 300, 44, 60, fill="#d9432b", outline="#3a1c14", width=3, radius=10)
        self._floor(c, "#b07a4a", "#8a5c36", "#4a2f20", "#7d5330")

    def _city_night(self, c, t):
        g = self.g
        c.background("#0b1030", "#3a2a63")
        with c.parallax(0.05, 0.05):
            for x, y, r_, ph in self.stars:
                a = 0.55 + 0.45 * math.sin(t * 2.0 + ph * 6.28)
                c.circle(x, y, r_ * a, fill=mix("#0b1030", "#ffffff", 0.35 + 0.5 * a))
            c.glow(980, 120, 150, "#cfd8ff", 0.55)
            c.circle(980, 120, 44, fill="#f3f1e6")
        for par, blds, col, win in ((0.25, self.far, "#171a3a", "#ffd98a"), (0.5, self.near, "#0e1028", "#8be9fd")):
            with c.parallax(par, 0.5):
                for x, w, h, lit in blds:
                    c.rect(x, g - h, w, h + 40, fill=col)
                    cols = int(w // 22)
                    for i, on in enumerate(lit):
                        if on:
                            c.rect(x + 6 + (i % cols) * 22, g - h + 12 + (i // cols) * 30, 11, 14, fill=win)
        with c.parallax(0.8):
            for nx, col in ((180, "#ff2fb4"), (700, "#18e6ff"), (1180, "#ffe14a")):
                c.glow(nx, g - 235, 110, col, 0.9)
                c.rect(nx - 55, g - 260, 110, 44, fill=col, radius=8)
        self._floor(c, "#161a2e", "#0f1222", "#3f4a86")
        for lx in range(-1200, 2800, 420):
            c.rect(lx - 3, g - 210, 6, 214, fill="#0b0d1a")
            c.glow(lx, g - 214, 95, "#ffd98a", 0.8)
            c.circle(lx, g - 214, 7, fill="#fff2c8")
        for x in range(-1200, 2800, 160):
            c.rect(x, g + 112, 80, 8, fill="#c7a93b")

    def _sunset(self, c, t):
        g = self.g
        c.background("#2b1a55", "#ff9a5a")
        with c.parallax(0.03, 0.03):
            c.glow(640, g - 40, 460, "#ffb347", 0.9)
            c.circle(640, g - 40, 120, fill="#ffe1a8")
        for x, y, w, a in self.clouds:
            with c.parallax(0.12):
                c.ellipse(x, y, w, 14, fill=mix("#ff9a5a", "#ffd9b0", a))
        for par, col, amp, off in ((0.2, "#6a3d7a", 130, 0), (0.4, "#3f2257", 170, 90)):
            with c.parallax(par, 0.3):
                pts = [(-900, g + 10)]
                for i in range(0, 34):
                    x = -900 + i * 90
                    pts.append((x, g - amp * (0.5 + 0.5 * noise(i * 0.55 + off, 5)) - 30))
                pts.append((2500, g + 10))
                c.poly(pts, fill=col)
        self._floor(c, "#2a1b3a", "#1d1228", "#ffb347")

    def _arena(self, c, t):
        g = self.g
        c.background("#06070d", "#1a1d33")
        with c.parallax(0.35, 0.3):
            for row, (y, sc) in enumerate(((g - 200, 1.0), (g - 130, 1.25))):
                for x, h, col in self.crowd:
                    xx = x + (row * 13)
                    bob = math.sin(t * 5 + xx * 0.05) * 3 * (1 if row else 0.5)
                    c.circle(xx, y - 22 * h * sc + bob, 11 * sc, fill=col)
                    c.rect(xx - 13 * sc, y - 12 * sc + bob, 26 * sc, 60 * sc, fill=col, radius=8)
        for sx, col in ((250, "#8be9fd"), (640, "#ffffff"), (1030, "#ff9bd5")):
            with c.parallax(0.5, 0.2):
                c.glow(sx, g - 60, 260, col, 0.35)
        self._floor(c, "#20253f", "#171a30", "#8be9fd")
        with c.parallax(1.0):
            for px in (-150, 1430):
                c.rect(px - 10, g - 190, 20, 200, fill="#c9d1ff")
            for i, ry in enumerate((g - 150, g - 95, g - 40)):
                c.line(-140, ry, 1420, ry, ("#ff4d6d", "#ffffff", "#ff4d6d")[i], 6, cap=False)

    def _forest(self, c, t):
        g = self.g
        c.background("#173a2c", "#7fb685")
        c.glow(900, 120, 380, "#fff6c9", 0.6)
        for par, col, tc in ((0.3, "#1f4d3a", "#16382a"), (0.55, "#173e2e", "#102c21")):
            with c.parallax(par, 0.3):
                for x, sc, ph in self.trees:
                    xx = x * (1.0 if par < 0.5 else 0.8) + ph * 60
                    c.rect(xx - 10 * sc, g - 220 * sc, 20 * sc, 230 * sc, fill=tc)
                    c.circle(xx, g - 260 * sc, 78 * sc, fill=col)
                    c.circle(xx - 50 * sc, g - 215 * sc, 54 * sc, fill=col)
                    c.circle(xx + 52 * sc, g - 220 * sc, 58 * sc, fill=col)
        self._floor(c, "#4b7a3d", "#365a2c", "#2c4a23")
        for x in range(-1200, 2800, 70):
            h = 8 + (x * 7 % 17)
            c.line(x, g + 4, x - 4, g - h, "#5f9a4a", 3, cap=False)


# ======================================================================================
# Fight: a choreographed (or automatic) stickman fight with hit effects, camera, sound and health bars
# ======================================================================================
class _Warp:
    """Maps video time <-> fight time so hits can freeze for a few frames and the knock-out can run in slow motion."""

    def __init__(self, specs, s_end):
        segs, s, v = [], 0.0, 0.0
        for kind, s0, a, b in sorted(specs, key=lambda x: x[1]):
            if s0 < s - 1e-9:
                continue
            if s0 > s:
                segs.append((v, v + (s0 - s), s, s0))
                v += s0 - s
            if kind == "freeze":                                  # fight time stands still for 'a' video seconds
                segs.append((v, v + a, s0, s0))
                v += a
                s = s0
            else:                                                 # slow: from s0 to a, at rate b
                dur = (a - s0) / max(b, 0.01)
                segs.append((v, v + dur, s0, a))
                v += dur
                s = a
        if s < s_end:
            segs.append((v, v + (s_end - s), s, s_end))
            v += s_end - s
        self.segs, self.v_end, self.s_end = segs, v, max(s, s_end)

    def sim(self, v):
        for v0, v1, s0, s1 in self.segs:
            if v < v1:
                return s0 if s1 == s0 or v1 == v0 else s0 + (s1 - s0) * (v - v0) / (v1 - v0)
        return self.s_end + (v - self.v_end)

    def vid(self, s):
        for v0, v1, s0, s1 in self.segs:
            if s1 == s0:
                if abs(s - s0) < 1e-9:
                    return v0
            elif s < s1:
                return v0 + (s - s0) / (s1 - s0) * (v1 - v0)
        return self.v_end + (s - self.s_end)


class Fight:
    """Two stickmen, a stage and a script. Use it by hand or let the director write the fight:

        a, b = Stick('BLUE', '#4aa3ff'), Stick('RED', '#ff5252')
        f = Fight(a, b, stage='city_night')
        f.auto(duration=14, winner='a')            # a believable fight that ends in a K.O.
        v = Video(1280, 720); v.add(f); v.render()

    By hand (times are in seconds of fight time):
        f.walk('a', to=520, at=0.5); f.attack('a', 'jab', at=2.0); f.attack('b', 'cross', at=2.8, hit=False)
        f.block('b', at=3.4); f.attack('a', 'round_kick', at=4.0, finisher=True); f.victory('a', at=5.5); f.text(4.3, 'K.O.')
    Moves: jab cross uppercut front_kick round_kick sweep flying_kick. Other actions: block dodge duck taunt bow jump victory."""

    def __init__(self, a, b, stage="dojo", width=1280, height=720, ground=None, a_x=None, b_x=None, title=None, music=None, hud=True, seed=3, trails=True):
        self.f = [a, b]
        self.W, self.H = width, height
        self.ground = ground or int(height * 0.78)
        self.stage = stage if isinstance(stage, Stage) else Stage(stage, width, height, self.ground, seed)
        cx = width / 2.0
        self.x0 = [cx - 300.0 if a_x is None else float(a_x), cx + 300.0 if b_x is None else float(b_x)]
        self.title, self.music, self.hud, self.trails = title, music, hud, trails
        self.t_end = 0.0
        self.start = 0.0
        self.seed = seed
        self._acts = [[], []]
        self._disp = []
        self._attacks = []
        self._texts = []
        self._warps = []
        self._zooms = []
        self._sounds = []
        self._ko = None
        self._compiled = False
        self.winner = None
        self.extra = None            # optional hook extra(c, t): draw your own props in world coordinates, after the fighters

    # ---- who ----
    def _i(self, who):
        if who in (0, 1):
            return int(who)
        if isinstance(who, str):
            w = who.lower()
            if w in ("a", "left", "1", self.f[0].name.lower()):
                return 0
            if w in ("b", "right", "2", self.f[1].name.lower()):
                return 1
        for i, s in enumerate(self.f):
            if who is s:
                return i
        raise ValueError("unknown fighter %r: use 'a', 'b', a Stick or its name" % (who,))

    def _touch(self, t):
        self.t_end = max(self.t_end, t)
        self._compiled = False

    # ---- scripting ----
    def walk(self, who, to=None, by=None, at=0.0, dur=None, speed=150.0):
        """Walk (speed under 260 px/s) or run (faster) to an x position, or by a distance. Needs no pose: the walk cycle is automatic."""
        i = self._i(who)
        self._disp.append(dict(i=i, t0=at, dur=dur, speed=speed, to=to, by=by, ease="in_out_sine"))
        self._touch(at + (dur or 0.5))

    def run(self, who, to=None, by=None, at=0.0, dur=None):
        self.walk(who, to, by, at, dur, speed=360.0)

    def gap(self, at, gap=84.0, dur=0.45):
        """Bring both fighters to fighting distance around their midpoint."""
        self._disp.append(dict(i=None, t0=at, dur=dur, gap=gap, ease="in_out_sine"))
        self._touch(at + dur)

    def _act(self, i, name, at, prio, dur=None, hold=False, shift=0.0):
        m = MOVES[name]
        d = dur if dur is not None else m.dur
        self._acts[i].append(dict(t0=at, t1=float("inf") if hold else at + d, move=name, prio=prio, shift=shift))
        self._touch(at + d)

    def attack(self, who, move, at, hit=True, dmg=None, finisher=False):
        """Start a move. hit=False makes it miss (the opponent dodges); a block the opponent has scheduled around the impact absorbs it.
        finisher=True knocks the opponent out. Returns the attack record (its 'dmg' can still be changed)."""
        i = self._i(who)
        if move not in MOVES or not MOVES[move].hit:
            raise ValueError("unknown attack %r; choose one of: %s" % (move, ", ".join(k for k, m in MOVES.items() if m.hit)))
        m = MOVES[move]
        rec = dict(i=i, move=move, t0=at, hit=hit, dmg=float(m.dmg if dmg is None else dmg), finisher=finisher)
        self._attacks.append(rec)
        self._act(i, move, at, 2)
        self._touch(at + m.dur)
        return rec

    def block(self, who, at, dur=0.55):
        self._acts[self._i(who)].append(dict(t0=at, t1=at + dur, move="block", prio=1, shift=0.0))
        self._touch(at + dur)

    def dodge(self, who, at, back=34.0):
        i = self._i(who)
        self._act(i, "dodge", at, 1)
        self._disp.append(dict(i=i, t0=at + 0.04, dur=0.22, by=-back, away=True, ease="out_quad"))
        self._disp.append(dict(i=i, t0=at + 0.34, dur=0.2, by=back * 0.8, away=True, ease="in_out_sine"))

    def duck(self, who, at):
        self._act(self._i(who), "duck", at, 1)

    def taunt(self, who, at):
        self._act(self._i(who), "taunt", at, 1)

    def bow(self, who, at):
        self._act(self._i(who), "bow", at, 1)

    def jump(self, who, at):
        self._act(self._i(who), "jump", at, 1)

    def victory(self, who, at):
        self._act(self._i(who), "victory", at, 1, hold=True)
        self._touch(at + 1.4)

    def text(self, at, s, dur=1.0, size=150, color="#ffffff", style="pop", y=None):
        """Big caption in the middle of the screen. style: 'pop' (scales in), 'slam' (drops in with a shake), 'fade'."""
        self._texts.append(dict(t0=at, t1=at + dur, s=s, size=size, color=color, style=style, y=y))
        self._touch(at + dur)

    def freeze(self, at, dur=0.08):
        """Hold the picture for a few frames (hit stop). Hits already do this; use it for extra emphasis."""
        self._warps.append(("freeze", at, dur, 0))

    def slowmo(self, at, dur, rate=0.3):
        """Play 'dur' seconds of fight time at 'rate' speed (0.3 = slow motion)."""
        self._warps.append(("slow", at, at + dur, rate))
        self._touch(at + dur)

    def zoom(self, at, dur=0.8, amount=0.25):
        """Punch the camera in by 'amount' (0.25 = 25 percent) and back out."""
        self._zooms.append((at, dur, amount))
        self._touch(at + dur)

    def sound(self, at, snd, vol=1.0, pan=0.0):
        self._sounds.append((at, snd, vol, pan))

    # ---- the director ----
    def auto(self, duration=14.0, winner="a", seed=1, intro=True, finisher=None):
        """Write a complete fight: walk-in, exchanges (combos, blocks, dodges and counters), a finishing blow, K.O. in slow motion, a winner banner.
        The winner lands more and bigger hits; the loser's health reaches zero exactly on the finishing blow."""
        rnd = random.Random(seed)
        w = self._i(winner)
        l = 1 - w
        wn, ln = self.f[w].name, self.f[l].name
        self.winner = w
        t = 0.0
        if intro:
            self.text(0.3, "READY?", 0.9, 110, "#ffffff", "pop")
            self.text(1.5, "FIGHT!", 0.9, 170, "#ffd166", "slam")
            self.sound(1.5, sfx.bell(660, 1.0, 0.4), 0.8)
            self.gap(0.9, 86.0, 1.5)
            t = 2.5
        else:
            self.gap(0.0, 86.0, 0.3)
            t = 0.5
        ko_t = max(t + 1.5, duration - 3.6)
        combos = [["jab", "cross"], ["jab", "jab", "cross"], ["front_kick"], ["jab", "cross", "round_kick"], ["sweep", "uppercut"], ["cross", "front_kick"],
                  ["jab", "front_kick"], ["round_kick"], ["uppercut"], ["jab", "cross", "uppercut"]]
        won, lost = [], []
        guard = 0
        while t < ko_t - 1.7 and guard < 40:
            guard += 1
            atk = w if rnd.random() < 0.62 else l
            dfd = 1 - atk
            chain = rnd.choice(combos)
            if atk == l:
                chain = chain[:rnd.choice((1, 2))]
            plan = rnd.choices(["land", "block", "dodge"], [5, 2, 1.6] if atk == w else [1.4, 3, 3])[0]
            tt = t
            first_impact = None
            for k, mv in enumerate(chain):
                m = MOVES[mv]
                ok = plan == "land" or (k > 0 and plan == "block") or (k > 0 and plan == "dodge")
                if k == 0 and plan == "dodge":
                    rec = self.attack(atk, mv, tt, hit=False)
                    self.dodge(dfd, tt + m.hit - 0.28)
                    counter = rnd.choice(["jab", "cross", "front_kick"])
                    rec2 = self.attack(dfd, counter, tt + m.hit + 0.25, hit=True)
                    (won if dfd == w else lost).append(rec2)
                    tt = tt + m.hit + 0.25 + MOVES[counter].dur
                    break
                rec = self.attack(atk, mv, tt, hit=True)
                if k == 0 and plan == "block":
                    self.block(dfd, tt + m.hit - 0.3, 0.7)
                    rec["blocked_plan"] = True
                if not (k == 0 and plan == "block"):
                    (won if atk == w else lost).append(rec)
                tt += m.dur * (0.78 if k < len(chain) - 1 else 1.0)
            t = tt + rnd.uniform(0.15, 0.4)
            self.gap(tt - 0.05, 86.0, 0.38)
            if rnd.random() < 0.25 and t < ko_t - 2.5:
                mover = rnd.choice((0, 1))
                self.taunt(mover, t) if rnd.random() < 0.5 else self.jump(mover, t)
                t += 0.9
        fm = finisher or rnd.choice(["round_kick", "uppercut", "flying_kick", "cross"])
        fk = MOVES[fm]
        if fm == "flying_kick":
            self.gap(ko_t - 1.2, 150.0, 0.6)
        else:
            self.gap(ko_t - 0.7, 86.0, 0.5)
        frec = self.attack(w, fm, ko_t, hit=True, finisher=True)
        self.victory(w, ko_t + 2.0)
        self.text(ko_t + fk.hit + 0.15, "K.O.", 1.5, 220, "#ff5252", "slam")
        self.text(ko_t + 2.3, "%s WINS!" % wn, 1.2, 100, "#ffd166", "pop", y=self.H * 0.3)
        self.t_end = max(self.t_end, duration)
        # balance the health bars: the winner takes some damage, the loser ends on exactly zero with the finishing blow
        def scale(recs, total):
            base = sum(r["dmg"] for r in recs if not r.get("blocked_plan"))
            if base > 0:
                k = clamp(total / base, 0.5, 2.6)
                for r in recs:
                    r["dmg"] *= k
        scale([r for r in lost], rnd.uniform(28, 55))
        scale([r for r in won if r is not frec], 100.0 - 24.0)
        frec["dmg"] = 100.0
        return self

    # ---- compile: resolve hits, positions, effects ----
    def _active(self, i, s):
        best = None
        for a in self._acts[i]:
            if a["t0"] <= s < a["t1"] and (best is None or (a["prio"], a["t0"]) >= (best["prio"], best["t0"])):
                best = a
        return best

    def _x_at(self, i, s):
        segs = self._xs[i]
        k = bisect.bisect_right(segs[0], s) - 1
        if k < 0:
            return self.x0[i]
        t0, t1, a, b, e = segs[1][k]
        return b if s >= t1 else a + (b - a) * ease((s - t0) / max(t1 - t0, 1e-6), e)

    def _compile(self):
        if self._compiled:
            return
        ko_i = None
        # 1. outcome of every attack, in the order the blows land
        events = []
        for rec in sorted(self._attacks, key=lambda r: r["t0"] + MOVES[r["move"]].hit):
            m = MOVES[rec["move"]]
            ts = rec["t0"] + m.hit
            att, tgt = rec["i"], 1 - rec["i"]
            if ko_i == tgt or ko_i == att and ts > self._ko[1]:
                rec["result"] = "none"
                continue
            if not rec["hit"]:
                rec["result"] = "miss"
            else:
                st = self._active(tgt, ts)
                if st and st["move"] in ("block", "duck") and st["prio"] == 1 and not rec["finisher"]:
                    rec["result"] = "blocked"
                elif st and st["move"] == "dodge":
                    rec["result"] = "miss"
                else:
                    rec["result"] = "hit"
            rec["ts"] = ts
            if rec["result"] == "hit":
                if rec["finisher"]:
                    ko_i = tgt
                    self._ko = (tgt, ts)
                    rec["_finish"] = True
                    self._acts[tgt].append(dict(t0=ts, t1=float("inf"), move="launch" if m.launch else "knockdown", prio=3, shift=0.0))
                else:
                    kind = {"head": "hit_head", "body": "hit_body", "legs": "stagger"}[m.kind]
                    self._acts[tgt].append(dict(t0=ts, t1=ts + MOVES[kind].dur, move=kind, prio=3, shift=0.0))
                self._disp.append(dict(i=tgt, t0=ts, dur=0.28, by=m.knock * (1.7 if rec["finisher"] else 1.0), away=True, ease="out_quad"))
            elif rec["result"] == "blocked":
                self._acts[tgt].append(dict(t0=ts, t1=ts + 0.4, move="blocked", prio=3, shift=0.0))
                self._disp.append(dict(i=tgt, t0=ts, dur=0.2, by=m.knock * 0.35, away=True, ease="out_quad"))
            events.append(rec)
        # 2. positions: every move of every fighter in time order, each starting where the previous one ended
        xs = [[[], []], [[], []]]
        pos = list(self.x0)
        self._xs = [([], []), ([], [])]

        def push(i, t0, t1, a, b, e):
            self._xs[i][0].append(t0)
            self._xs[i][1].append((t0, t1, a, b, e))
        for i in (0, 1):
            self._xs[i][0].append(-1e9)
            self._xs[i][1].append((-1e9, -1e9, self.x0[i], self.x0[i], "linear"))
        att_dir = lambda i: 1.0 if self.f[1 - i] is not None and pos[1 - i] >= pos[i] else -1.0
        arena = (60.0, self.W - 60.0)
        for d in sorted(self._disp, key=lambda d: d["t0"]):
            t0 = d["t0"]
            cur = [self._x_at(0, t0), self._x_at(1, t0)]
            if d["i"] is None:                                         # both to fighting distance
                mid = (cur[0] + cur[1]) / 2.0
                mid = clamp(mid, arena[0] + d["gap"], arena[1] - d["gap"])
                sgn = 1.0 if cur[1] >= cur[0] else -1.0
                for j, off in ((0, -sgn), (1, sgn)):
                    push(j, t0, t0 + d["dur"], cur[j], mid + off * d["gap"] / 2.0, d["ease"])
                continue
            i = d["i"]
            toward = 1.0 if cur[1 - i] >= cur[i] else -1.0
            if d.get("to") is not None:
                target = d["to"]
            elif d.get("by") is not None:
                target = cur[i] + d["by"] * (-toward if d.get("away") and d["by"] > 0 else toward if d.get("away") else 1.0)
                if d.get("away") and d["by"] < 0:                       # negative 'by' with away = step back (away from the opponent)
                    target = cur[i] + d["by"] * toward
            else:
                target = cur[i]
            target = clamp(target, arena[0], arena[1])
            dur = d["dur"] if d.get("dur") else max(0.15, abs(target - cur[i]) / max(d.get("speed", 150.0), 1.0))
            push(i, t0, t0 + dur, cur[i], target, d["ease"])
            self._touch(t0 + dur)
        # 3. facing, sampled finely so a fighter turns only when the other one really passes
        self._fstep = 1.0 / 60.0
        n = int(self.t_end / self._fstep) + 3
        self._face = [[1.0] * n, [-1.0] * n]
        cur = [1.0, -1.0]
        for k in range(n):
            s = k * self._fstep
            xa, xb = self._x_at(0, s), self._x_at(1, s)
            if abs(xb - xa) > 14:
                cur = [1.0, -1.0] if xb > xa else [-1.0, 1.0]
            self._face[0][k], self._face[1][k] = cur
        # 4. effects, health, sounds
        self._fx, self._shakes, self._hp, self._popups = [], [], [[], []], []
        cache = {}

        def snd(name, power=1.0):
            key = (name, round(power, 1))
            if key not in cache:
                cache[key] = getattr(sfx, name)(power) if name in ("punch", "hit", "kick") else getattr(sfx, name)()
            return cache[key]
        for rec in events:
            m = MOVES[rec["move"]]
            ts, att, tgt = rec["ts"], rec["i"], 1 - rec["i"]
            if rec["result"] == "none":
                continue
            self._sounds.append((rec["t0"] + max(0.0, m.hit - 0.1), sfx.whoosh(0.22, 0.45), 0.7, 0.0))
            if rec["result"] == "miss":
                continue
            pa = self._pose(att, ts)
            J = self.f[att].joints(self._x_at(att, ts) + self._off(att, ts), self.ground, self._facing(att, ts), pa[0])
            hx, hy = J[m.limb]
            heavy = rec["dmg"] >= 11 or rec["finisher"]
            if rec["result"] == "hit":
                self._fx.append(dict(kind="spark", s=ts, x=hx, y=hy, heavy=heavy, dir=self._facing(att, ts)))
                self._popups.append(dict(s=ts, x=hx, y=hy - 40, text="-%d" % round(rec["dmg"]), heavy=heavy))
                self._hp[tgt].append((ts, rec["dmg"]))
                if rec["finisher"]:
                    left = self.f[tgt].max_hp - sum(d for (te, d) in self._hp[tgt])
                    if left > 0:
                        self._hp[tgt].append((ts, left))
                self._shakes.append((ts, min(18.0, 3.0 + rec["dmg"] * 0.55) * (1.5 if rec["finisher"] else 1.0)))
                self._sounds.append((ts, snd(m.snd, 0.7 + rec["dmg"] / 22.0), 0.95, 0.0))
                hold = 0.05 + min(0.08, rec["dmg"] * 0.004)
                if rec["finisher"]:
                    hold = 0.16
                    self._warps.append(("slow", ts + 0.05, ts + 1.05, 0.28))
                    self._zooms.append((ts, 1.6, 0.3))
                    self._fx.append(dict(kind="ring", s=ts, x=hx, y=hy))
                    self._sounds.append((ts + 0.04, snd("ko"), 0.9, 0.0))
                    self._fx.append(dict(kind="flash", s=ts))
                    self._fx.append(dict(kind="dust", s=ts + 0.4, x=self._x_at(tgt, ts + 0.4), y=self.ground))
                    if getattr(self.stage, "kind", "") == "arena":
                        self._sounds.append((ts + 0.5, sfx.crowd(2.6, 0.35), 0.8, 0.0))
                self._warps.append(("freeze", ts, hold, 0))
            else:
                self._fx.append(dict(kind="block", s=ts, x=hx, y=hy, dir=self._facing(att, ts)))
                self._sounds.append((ts, snd("punch", 0.4), 0.7, 0.0))
                self._sounds.append((ts, sfx.click(), 0.9, 0.0))
                self._hp[tgt].append((ts, rec["dmg"] * 0.12))
                self._shakes.append((ts, 2.5))
                self._warps.append(("freeze", ts, 0.03, 0))
        # walking sounds
        for i in (0, 1):
            for (t0, t1, a, b, e) in self._xs[i][1]:
                if t0 > -1e8 and abs(b - a) > 20 and (t1 - t0) > 0.25:
                    st = t0 + 0.1
                    while st < t1 - 0.05:
                        self._sounds.append((st, sfx.step(0.5), 0.35, -0.25 if i == 0 else 0.25))
                        st += 0.3 if abs(b - a) / (t1 - t0) < 260 else 0.2
        self._warp = _Warp(self._warps, self.t_end)
        self._events = events
        self._compiled = True

    # ---- poses at a fight time ----
    def _facing(self, i, s):
        k = int(clamp(s / self._fstep, 0, len(self._face[i]) - 1))
        return self._face[i][k]

    def _off(self, i, s):
        a = self._active(i, s)
        if a and a["move"] in MOVES:
            return MOVES[a["move"]].offset(s - a["t0"]) * self._facing(i, s)
        return 0.0

    def _pose(self, i, s):
        """(resolved pose, name of what it is doing)."""
        a = self._active(i, s)
        if a:
            if self._ko and self._ko[0] == i and s >= self._ko[1] and a["move"] in ("knockdown", "launch"):
                pass
            return MOVES[a["move"]].pose_at(s - a["t0"]), a["move"]
        if self._ko and self._ko[0] == i and s >= self._ko[1]:
            return POSES["lying"] and resolve_pose("lying"), "lying"
        x1, x0 = self._x_at(i, s + 0.03), self._x_at(i, s - 0.03)
        vel = (x1 - x0) / 0.06
        if abs(vel) > 14:
            sgn = self._facing(i, s)
            fwd = vel * sgn > 0
            run = abs(vel) > 260
            phase = self._x_at(i, s) * sgn / (84.0 if run else 56.0)
            pose = _walk_pose(phase if fwd else -phase, run)
            return pose, "run" if run else "walk"
        b = math.sin(s * 3.2 + i)
        p = dict(POSES["guard"])
        p["lean"] += b * 1.5
        p["rua"] += b * 2.5
        p["lua"] -= b * 2.0
        p["y"] = resolve_pose(p)["y"] + b * 1.2
        return p, "idle"

    # ---- camera ----
    def _camera(self, v, s):
        xs, zs = 0.0, 0.0
        n = 6
        for k in range(n):
            ss = s + (k - (n - 1) / 2.0) * 0.12
            xa, xb = self._x_at(0, ss), self._x_at(1, ss)
            xs += (xa + xb) / 2.0
            zs += abs(xb - xa)
        xs, dist = xs / n, zs / n
        zoom = clamp(1050.0 / (dist + 330.0), 1.08, 1.75)
        for (t0, dur, amt) in self._zooms:
            vv = v - self._warp.vid(t0)
            if 0 <= vv < dur:
                zoom *= 1.0 + amt * math.sin(math.pi * vv / dur) ** 1.5
        cy = self.ground - 150.0 / zoom * 0.9 - 20.0
        shake = 0.0
        for (ts, amp) in self._shakes:
            vv = v - self._warp.vid(ts)
            if 0 <= vv < 0.5:
                shake += amp * math.exp(-vv * 9.0)
        return xs, cy, zoom, min(shake, 26.0)

    def summary(self):
        """What the script will show, as numbers, so you can check a choreography without watching it: video length, landed / blocked / missed
        attacks per fighter, health left at the end and who is knocked out. print(fight.summary())."""
        self._compile()
        hits, blocked, missed = [0, 0], [0, 0], [0, 0]
        for r in self._attacks:
            res = r.get("result")
            if res == "hit":
                hits[r["i"]] += 1
            elif res == "blocked":
                blocked[r["i"]] += 1
            elif res == "miss":
                missed[r["i"]] += 1
        end = self.t_end + 5.0
        return {"duration": round(self.duration, 2), "hits": hits, "blocked": blocked, "missed": missed,
                "hp": [round(self._hp_at(i, end), 1) for i in (0, 1)], "ko": self.f[self._ko[0]].name if self._ko else None,
                "names": [self.f[0].name, self.f[1].name]}

    @property
    def duration(self):
        self._compile()
        return max(1.0, self._warp.v_end)

    @property
    def end(self):
        return self.start + self.duration

    def on_add(self, video):
        """Called by Video.add: puts the fight's sound effects (and music) on the video's sound track."""
        self._compile()
        base = getattr(self, "start", 0.0)
        for (s, buf, vol, pan) in self._sounds:
            video.sound(buf, base + self._warp.vid(s), vol, pan)
        if self.music:
            style = self.music if self.music in _Music.STYLES else "fight"
            bpm = {"fight": 128, "epic": 100, "8bit": 140, "chill": 90}[style]
            bars = int(math.ceil(self.duration / (4 * 60.0 / bpm)))
            video.sound(music.beat(bpm, bars, style, vol=0.9), base, 0.32)

    # ---- drawing ----
    def draw(self, c, v):
        self._compile()
        s = self._warp.sim(v)
        cx, cy, zoom, shake = self._camera(v, s)
        c.camera(cx, cy, zoom, shake=shake)
        self.stage.draw(c, v)
        order = [0, 1]
        acts = [self._pose(i, s) for i in (0, 1)]
        if acts[1][1] in MOVES and MOVES[acts[1][1]].hit and not (acts[0][1] in MOVES and MOVES[acts[0][1]].hit):
            order = [0, 1]
        elif acts[0][1] in MOVES and MOVES[acts[0][1]].hit and not (acts[1][1] in MOVES and MOVES[acts[1][1]].hit):
            order = [1, 0]
        for i in order:
            pose, what = acts[i]
            x = self._x_at(i, s) + self._off(i, s)
            fc = self._facing(i, s)
            trail = None
            if self.trails and what in MOVES and MOVES[what].hit:
                lt = s - MOVES[what].hit
                a = self._active(i, s)
                local = s - a["t0"]
                if abs(local - MOVES[what].hit) < 0.22:
                    trail = [(MOVES[what].pose_at(max(0.0, local - d)), 0.55 + d * 3) for d in (0.05, 0.1)]
            self.f[i].draw(c, x, self.ground, fc, pose, v, trail=trail)
        if self.extra is not None:
            self.extra(c, v)
        for fx in self._fx:
            e = v - self._warp.vid(fx["s"])
            if e < -1e-6:
                continue
            self._draw_fx(c, fx, e)
        for p in self._popups:
            e = v - self._warp.vid(p["s"])
            if 0 <= e < 0.9:
                c.text(p["text"], p["x"], p["y"] - 70 * ease(e / 0.9, "out_cubic"), 54 if p["heavy"] else 40, "#ffd166" if p["heavy"] else "#ffffff",
                       outline="#000000", outline_w=4, alpha=clamp(1.6 - e / 0.6))
        c.vignette(0.35)
        with c.screen():
            if self.hud:
                self._draw_hud(c, v, s)
            for tx in self._texts:
                self._draw_text(c, tx, s, v)

    def _draw_fx(self, c, fx, e):
        k = fx["kind"]
        if k == "spark" and e < 0.3:
            u = e / 0.3
            big = 1.5 if fx["heavy"] else 1.0
            c.glow(fx["x"], fx["y"], (60 + 90 * (1 - u)) * big, "#ffd166", 0.9 * (1 - u))
            for j in range(9 if fx["heavy"] else 6):
                a = (j / (9.0 if fx["heavy"] else 6.0)) * math.pi * 2 + fx["s"] * 3.7
                r0, r1 = (14 + 80 * u) * big, (30 + 150 * u) * big
                c.line(fx["x"] + math.cos(a) * r0, fx["y"] + math.sin(a) * r0, fx["x"] + math.cos(a) * r1, fx["y"] + math.sin(a) * r1,
                       mix("#ffffff", "#ffb347", u), max(1.5, 8 * (1 - u) * big))
            if u < 0.4:
                c.circle(fx["x"], fx["y"], 26 * big * (1 - u / 0.4) + 6, fill="#ffffff")
        elif k == "block" and e < 0.28:
            u = e / 0.28
            c.arc(fx["x"] + fx["dir"] * 12, fx["y"], 30 + 40 * u, -70 if fx["dir"] > 0 else 110, 70 if fx["dir"] > 0 else 250, "#8be9fd", max(1.5, 8 * (1 - u)))
        elif k == "ring" and e < 0.55:
            u = e / 0.55
            c.circle(fx["x"], fx["y"], 30 + 170 * ease(u, "out_cubic"), outline="#ffffff", width=max(1.0, 10 * (1 - u)))
        elif k == "dust" and e < 0.8:
            u = e / 0.8
            for j in range(7):
                a = (j - 3) * 0.55
                c.circle(fx["x"] + math.sin(a) * 90 * u + (j % 2) * 8, fx["y"] - 10 - 40 * u * (0.5 + (j % 3) * 0.25), 16 * (1 - u * 0.6) + 4, fill=mix("#cdbb9d", "#ffffff", 0.2 * (1 - u)))
        elif k == "flash" and e < 0.25:
            c.tint("#ffffff", 0.5 * (1 - e / 0.25))

    def _hp_at(self, i, s):
        mx = self.f[i].max_hp
        lost = 0.0
        for (te, d) in self._hp[i]:
            lost += d * ease((s - te) / 0.18, "out_quad") if s > te else 0.0
        return max(0.0, mx - lost)

    def _draw_hud(self, c, v, s):
        W = c.W
        bw, bh, y = 470.0, 26.0, 52.0
        for i in (0, 1):
            st = self.f[i]
            hp = self._hp_at(i, s) / st.max_hp
            chip = self._hp_at(i, max(0.0, s - 0.55)) / st.max_hp
            x0 = 40.0 if i == 0 else W - 40.0 - bw
            c.rect(x0 - 5, y - 5, bw + 10, bh + 10, fill="#0b0d14", radius=8)
            c.rect(x0, y, bw, bh, fill="#2a2f45", radius=5)
            colr = "#3ddc84" if hp > 0.5 else "#ffb020" if hp > 0.25 else "#ff4d4d"
            for frac, col in ((chip, "#fff2b3"), (hp, colr)):
                w = bw * clamp(frac)
                if w > 1:
                    c.rect(x0 if i == 0 else x0 + bw - w, y, w, bh, fill=col, radius=5)
            c.text(st.name, x0 + (0 if i == 0 else bw), y + bh + 22, 28, st.color, anchor="la" if i == 0 else "ra", outline="#000000", outline_w=3)
        if self.title:
            c.text(self.title, W / 2, y + 12, 30, "#ffffff", outline="#000000", outline_w=3)

    def _draw_text(self, c, tx, s, v):
        if not (tx["t0"] <= s < tx["t1"]):
            return
        u = (s - tx["t0"]) / max(tx["t1"] - tx["t0"], 1e-6)
        e = s - tx["t0"]
        y = tx["y"] if tx["y"] is not None else c.H * 0.42
        scale, alpha, jx = 1.0, 1.0, 0.0
        if tx["style"] == "pop":
            scale = ease(e / 0.28, "out_back")
        elif tx["style"] == "slam":
            scale = 1.0 + 1.6 * (1 - ease(e / 0.18, "out_cubic"))
            jx = (noise(e * 40, 9) * 14) * (1 - ease(e / 0.5, "out_quad"))
        left = tx["t1"] - s
        if left < 0.3:
            alpha = clamp(left / 0.3)
        c.text(tx["s"], c.W / 2 + jx, y, tx["size"], tx["color"], outline="#000000", outline_w=max(4, tx["size"] / 16.0), scale=scale, alpha=alpha,
               shadow=(0, tx["size"] / 20.0, "#000000"))


# ======================================================================================
# components for explainers, titles and data videos
# ======================================================================================
class Typewriter:
    """Text that types itself. tw = Typewriter('Hello world', start=0.5, cps=22); tw.draw(c, t, x, y, size=60, color='white')"""

    def __init__(self, text, start=0.0, cps=22.0):
        self.text, self.start, self.cps = text, start, cps

    def shown(self, t):
        return self.text[:max(0, int((t - self.start) * self.cps))]

    @property
    def end(self):
        return self.start + len(self.text) / self.cps

    def draw(self, c, t, x, y, size=60, color="white", anchor="la", cursor=True, **kw):
        s = self.shown(t)
        c.text(s + ("|" if cursor and int(t * 2) % 2 == 0 and t < self.end + 1.5 else ""), x, y, size, color, anchor=anchor, **kw)


class Particles:
    """Deterministic particle bursts that need no state: every particle is a formula of time, so scrubbing and re-rendering give the same frames.
    p = Particles(seed=1); p.burst(at=1.0, x=640, y=360, n=40, speed=300, color='#ffd166'); in your scene: p.draw(c, t)."""

    def __init__(self, seed=1, gravity=600.0):
        self.seed, self.g, self.bursts = seed, gravity, []

    def burst(self, at, x, y, n=30, speed=260.0, life=1.0, color="#ffd166", size=6.0, spread=360.0, angle=-90.0):
        r = random.Random(self.seed * 7919 + len(self.bursts))
        ps = []
        for _ in range(n):
            a = math.radians(angle + r.uniform(-spread / 2, spread / 2))
            sp = speed * r.uniform(0.35, 1.0)
            ps.append((math.cos(a) * sp, math.sin(a) * sp, r.uniform(0.6, 1.0) * life, r.uniform(0.6, 1.4) * size))
        self.bursts.append((at, x, y, color, ps))

    def draw(self, c, t):
        for at, x, y, color, ps in self.bursts:
            e = t - at
            if e < 0:
                continue
            for vx, vy, life, size in ps:
                if e > life:
                    continue
                u = e / life
                px, py = x + vx * e, y + vy * e + 0.5 * self.g * e * e
                c.circle(px, py, max(0.5, size * (1 - u)), fill=mix(color, "#000000", 0.5 * u))


class BarChart:
    """Animated horizontal bar chart. BarChart([('Python', 82), ('Go', 55)], colors=PALETTES['neon']).draw(c, t, x=160, y=200, w=900, h=360, start=0.5, dur=1.6)"""

    def __init__(self, data, colors=None, maximum=None, label_size=34, fmt="{:.0f}"):
        self.data, self.colors = data, colors or PALETTES["neon"]
        self.max = maximum or max(v for _, v in data)
        self.label_size, self.fmt = label_size, fmt

    def draw(self, c, t, x, y, w, h, start=0.0, dur=1.5, stagger=0.15):
        n = len(self.data)
        row = h / float(n)
        for i, (label, val) in enumerate(self.data):
            u = ease((t - start - i * stagger) / dur, "out_cubic")
            bw = (w - 220) * (val / float(self.max)) * u
            cy = y + row * i + row / 2
            c.text(label, x + 200, cy, self.label_size, "#e8ecf6", anchor="rm")
            c.rect(x + 220, cy - row * 0.32, w - 220, row * 0.64, fill="#262c42", radius=10)
            if bw > 1:
                c.rect(x + 220, cy - row * 0.32, bw, row * 0.64, fill=self.colors[i % len(self.colors)], radius=10)
            c.text(self.fmt.format(val * u), x + 220 + max(bw, 0) + 14, cy, self.label_size * 0.9, "#ffffff", anchor="lm")


class Subtitles:
    """Timed captions: Subtitles([(0.5, 3.0, 'Hello'), (3.2, 6.0, 'second line')]).draw(c, t). Fades in and out, with a dark box for contrast."""

    def __init__(self, cues, size=40, y=None):
        self.cues, self.size, self.y = cues, size, y

    def draw(self, c, t):
        for a, b, s in self.cues:
            if a <= t < b:
                al = clamp(min((t - a) / 0.2, (b - t) / 0.2))
                with c.screen():
                    y = self.y if self.y is not None else c.H - 90
                    wrapped = c.wrap(s, self.size, c.W * 0.8)
                    tw, th = c.text_size(wrapped, self.size)
                    c.rect(c.W / 2, y, tw + 50, th + 28, fill="#000000", radius=14, anchor="c", alpha=0.55 * al)
                    c.text(wrapped, c.W / 2, y, self.size, "#ffffff", alpha=al)
                return


# ======================================================================================
# command line: python lumovideo.py --check | --selftest | --version
# ======================================================================================
def _selftest(render=True):
    v = Video(1280, 720, fps=24, quality="draft")

    def draw(c, t):
        c.background("#101626", "#243b6b")
        c.circle(200 + 880 * ease(t / 1.0, "in_out_cubic"), 360, 60, fill="#ffd166")
        c.text("lumovideo %s" % __version__, 640, 160, 70, "#ffffff", scale=ease(t / 0.4, "out_back"))
    v.scene(1.0, draw)
    v.sound(sfx.ding(), 0.1)
    rep = v.dry_run(4)
    if render and ffmpeg_path():
        out = os.path.join(tempfile.mkdtemp(prefix="lumoselftest_"), "selftest.mp4")
        rep = v.render(out, progress=False)
        shutil.rmtree(os.path.dirname(out), ignore_errors=True)
        return {"rendered": True, "report": rep}
    return {"rendered": False, "qa": rep}


def _main(argv):
    if "--version" in argv:
        print(__version__)
    elif "--selftest" in argv:
        res = _selftest(render="--no-render" not in argv)
        print(json.dumps(res, default=str)[:600])
        qa = res.get("qa") or res["report"]["qa"]
        return 1 if qa["blank_frames"] else 0
    else:
        print(json.dumps(check_requirements(), indent=2))
        return 0 if check_requirements()["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
