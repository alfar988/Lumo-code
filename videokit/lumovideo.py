"""lumovideo: 2D video for Lumo Code.

Pillow draws every frame (60 fps, motion blur, several CPU cores at once), ffmpeg turns the frames into an MP4 (H.264 + AAC) that plays
everywhere. One file, no other dependencies (numpy is not needed). Typical script:

    from lumovideo import *
    v = Video(1280, 720)                         # coordinates are always 1280x720, whatever the output quality; fps follows the quality
    def intro(c, t):
        c.background("#101626", "#243b6b")
        c.text("Hello", 640, 360, 120, "white", outline="#000000", outline_w=6, scale=ease(t / 0.6, "out_back"))
    v.scene(3.0, intro, fade_out=0.4)
    v.render()                                   # videos/<script name>.mp4, or $LUMO_VIDEO_OUT

Main parts: ease/Keys (timing), Canvas (drawing, camera), sfx/music/Mixer (sound: synthesised effects, sound files, free sounds from the
internet), Video (scenes, render, checks), Stick/Fight/Stage (stickman characters and fights), Typewriter/Particles/BarChart/Subtitles
(components), play_hints/open_video (how to watch the result).
"""

__version__ = "1.1.0"

import array
import bisect
import collections
import concurrent.futures
import hashlib
import inspect
import ipaddress
import json
import math
import multiprocessing
import os
import random
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import wave

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat
except ImportError:                      # the render step explains how to install it
    Image = ImageChops = ImageDraw = ImageFont = ImageStat = None

__all__ = [
    "Video", "Scene", "Canvas", "Keys", "Spring", "ease", "lerp", "clamp", "remap", "tween", "noise", "pulse", "EASINGS",
    "rgb", "mix", "shade", "PALETTES", "font", "Mixer", "sfx", "music", "note_freq", "Stick", "Fight", "Stage", "POSES", "MOVES",
    "Typewriter", "Particles", "BarChart", "Subtitles", "Timeline", "check_requirements", "ffmpeg_path", "find_font", "frame_stats",
    "play_hints", "open_video", "load_sound", "find_sounds", "fetch_sound", "sound_credits", "SOUND_DIR",
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
# sound: synthesised effects (many families, every call can sound different), sound files, free sounds from the internet,
# music and a mixer. No sound files are needed: everything below is generated.
# ======================================================================================
SR = 44100
SOUND_DIR = "sounds"                           # where downloaded or loaded sound files live (relative to the workspace; LUMO_SOUNDS_DIR overrides)
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
    return array.array("f", [0.0]) * max(0, int(n))


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


# ---- small DSP toolbox (pure Python; every function returns a new buffer) ----
def _lowpass(buf, alpha):
    y = 0.0
    out = _buf(len(buf))
    for i, x in enumerate(buf):
        y += alpha * (x - y)
        out[i] = y
    return out


def _lp_a(fc):
    rc = 1.0 / (2 * math.pi * max(20.0, fc))
    return (1.0 / SR) / (rc + 1.0 / SR)


def _highpass(buf, fc):
    rc = 1.0 / (2 * math.pi * max(20.0, fc))
    a = rc / (rc + 1.0 / SR)
    out = _buf(len(buf))
    y = xp = 0.0
    for i, x in enumerate(buf):
        y = a * (y + x - xp)
        xp = x
        out[i] = y
    return out


def _biquad_coef(kind, freq, q):
    w0 = 2 * math.pi * min(max(freq, 20.0), SR * 0.45) / SR
    cw, sw = math.cos(w0), math.sin(w0)
    al = sw / (2.0 * max(q, 0.1))
    if kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
    elif kind == "hp":
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
    else:                                                         # "bp": constant peak gain
        b0, b1, b2 = al, 0.0, -al
    a0 = 1 + al
    return b0 / a0, b1 / a0, b2 / a0, -2 * cw / a0, (1 - al) / a0


def _biquad(buf, kind, freq, q=0.8, freq_end=None):
    """Resonant filter: kind 'lp', 'hp' or 'bp'. With freq_end the centre frequency glides (whooshes, sweeps)."""
    n = len(buf)
    out = _buf(n)
    x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2, a1, a2 = _biquad_coef(kind, freq, q)
    step = 48 if freq_end is not None else n + 1
    for i in range(n):
        if freq_end is not None and i % step == 0:
            f = freq * (freq_end / float(freq)) ** (i / float(max(1, n)))
            b0, b1, b2, a1, a2 = _biquad_coef(kind, f, q)
        x = buf[i]
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x
        y2, y1 = y1, y
        out[i] = y
    return out


def _soft(buf, drive=1.5):
    """Soft saturation: adds weight and bite to hits without hard clipping."""
    k = 1.0 / math.tanh(drive)
    out = _buf(len(buf))
    th = math.tanh
    for i, x in enumerate(buf):
        out[i] = th(drive * x) * k
    return out


def _pitch(buf, ratio):
    """Play faster (ratio > 1: higher and shorter) or slower: linear resampling."""
    if abs(ratio - 1.0) < 1e-3 or len(buf) < 4:
        return buf
    n = int((len(buf) - 1) / ratio)
    out = _buf(n)
    for i in range(n):
        p = i * ratio
        j = int(p)
        f = p - j
        out[i] = buf[j] * (1 - f) + buf[j + 1] * f
    return out


def _peak(buf, target=0.8):
    pk = max(map(abs, buf)) if len(buf) else 0.0
    if pk < 1e-9:
        return buf
    g = target / pk
    out = _buf(len(buf))
    for i, x in enumerate(buf):
        out[i] = x * g
    return out


def _scale(buf, g):
    out = _buf(len(buf))
    for i, x in enumerate(buf):
        out[i] = x * g
    return out


def _shape(buf, attack=0.002, tau=None, release=0.004):
    """Envelope: linear attack, exponential decay (time constant tau seconds), linear release at the very end."""
    n = len(buf)
    out = _buf(n)
    na, nr = max(1, int(attack * SR)), max(1, int(release * SR))
    inv = 1.0 / (tau * SR) if tau else 0.0
    for i in range(n):
        e = min(1.0, i / float(na)) * math.exp(-i * inv) * min(1.0, (n - i) / float(nr))
        out[i] = buf[i] * e
    return out


def _layers(*parts):
    """Mix buffers: each part is (buffer, delay in seconds, gain)."""
    n = max(int(d * SR) + len(b) for b, d, g in parts)
    out = _buf(n)
    for b, d, g in parts:
        s = int(d * SR)
        for i in range(len(b)):
            out[s + i] += b[i] * g
    return out


def _concat(*parts):
    """Put buffers one after another: each part is (buffer, gap in seconds before it)."""
    out = _buf(0)
    for b, gap in parts:
        out = out + _buf(gap * SR) + b
    return out


def _reverb(buf, room=0.5, wet=0.28, tail=0.7):
    """A small Schroeder reverb: four combs and two all-pass filters. Makes booms, gongs and thunder sound like they happen in a place."""
    n = len(buf) + int(tail * SR)
    src = _buf(n)
    src[:len(buf)] = buf
    acc = _buf(n)
    for d_ms, g in ((29.7, 0.77), (37.1, 0.75), (41.1, 0.73), (43.7, 0.71)):
        d = int(d_ms * SR / 1000.0)
        gg = min(0.9, g * (0.82 + 0.3 * room))
        comb = _buf(n)
        for i in range(n):
            comb[i] = src[i] + (comb[i - d] * gg if i >= d else 0.0)
        for i in range(n):
            acc[i] += comb[i] * 0.25
    for d_ms, g in ((5.0, 0.7), (1.7, 0.7)):
        d = int(d_ms * SR / 1000.0)
        ap = _buf(n)
        for i in range(n):
            xd = acc[i - d] if i >= d else 0.0
            yd = ap[i - d] if i >= d else 0.0
            ap[i] = -g * acc[i] + xd + g * yd
        acc = ap
    out = _buf(n)
    for i in range(n):
        out[i] = (src[i] if i < len(buf) else 0.0) * (1 - wet * 0.5) + acc[i] * wet * 2.0
    return out


def _echo(buf, delay=0.18, gain=0.4, taps=3):
    out = _buf(len(buf) + int(delay * SR * taps))
    for k in range(taps + 1):
        s = int(k * delay * SR)
        g = gain ** k
        for i in range(len(buf)):
            out[s + i] += buf[i] * g
    return out


def _fade(buf, fin=0.0, fout=0.0):
    n = len(buf)
    out = array.array("f", buf)
    ni, no = int(fin * SR), int(fout * SR)
    for i in range(min(ni, n)):
        out[i] *= i / float(ni)
    for i in range(min(no, n)):
        out[n - 1 - i] *= i / float(no)
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
        seg = end - start
        lg, rg = vol * min(1.0, 1.0 - pan), vol * min(1.0, 1.0 + pan)
        if lg:
            self.l[start:end] = array.array("f", [a + s * lg for a, s in zip(self.l[start:end], snd[:seg])])
        if rg:
            self.r[start:end] = array.array("f", [a + s * rg for a, s in zip(self.r[start:end], snd[:seg])])

    def peak(self):
        return max(max(map(abs, self.l)), max(map(abs, self.r)))

    def save(self, path, length=None):
        """Write a 16-bit stereo WAV. Quiet mixes stay as they are; loud ones are scaled down so they never clip."""
        n = min(self.n, int((length if length else self.duration) * SR))
        pk = self.peak()
        g = 0.92 / pk if pk > 0.92 else 1.0
        k = 32767 * g
        out = array.array("h", [0]) * (n * 2)
        out[0::2] = array.array("h", [int(max(-32767.0, min(32767.0, x * k))) for x in self.l[:n]])
        out[1::2] = array.array("h", [int(max(-32767.0, min(32767.0, x * k))) for x in self.r[:n]])
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


_FORMANTS = {"a": (800, 1150, 2800), "o": (500, 900, 2600), "u": (330, 800, 2400), "e": (520, 1800, 2600), "i": (300, 2300, 3000), "uh": (620, 1150, 2500)}

SFX_CATEGORIES = {
    "fight": ["punch", "hit", "kick", "slap", "thud", "smash", "crack", "block", "clang", "slash", "whoosh", "swing", "ko"],
    "movement": ["step", "slide", "land", "jump", "fall", "cloth"],
    "voice": ["kiai", "grunt", "pain", "gasp", "laugh"],
    "crowd": ["crowd", "cheer", "applause", "ooh"],
    "cinematic": ["boom", "impact", "riser", "downer", "stinger", "heartbeat", "gong", "taiko", "drum_roll", "cymbal", "rimshot", "explosion"],
    "nature": ["wind", "thunder", "rain", "fire", "drip", "splash"],
    "interface": ["ding", "bell", "coin", "pop", "click", "blip", "error", "laser", "success", "fail", "powerup", "zap", "select", "notify"],
    "machine": ["beep", "alarm", "engine", "camera", "key", "snare", "hat"],
    "cartoon": ["boing", "whistle", "bonk", "honk", "trombone", "squeak"],
    "weapon": ["gunshot", "rifle", "pistol", "reload", "shell"],
    "creature": ["groan", "roar", "zombie_death"],
}


class _Sfx:
    """Synthesised sound effects, over eighty of them (see sfx.names() and SFX_CATEGORIES). Each method returns a mono sample buffer:
    v.sound(sfx.punch(), at=1.5) or v.sfx("punch", 1.5). Calling the same effect again gives a slightly different take (pitch, noise, length),
    so ten punches never sound like one sample; variant=N gives the same take every time. power (0.5 to 1.5) is how hard, vol how loud.
    Real recordings: sfx.file("sounds/punch.wav") loads a sound file, sfx.net("punch") fetches a free one from the internet (cached)."""

    def __init__(self):
        self.rng = random.Random(11)
        self._n = {}

    # ---- plumbing ----
    def _v(self, name, variant=None):
        if variant is None:
            k = self._n.get(name, 0)
            self._n[name] = k + 1
        else:
            k = int(variant)
        return random.Random("lumo-sfx:%s:%d" % (name, k)), k

    @staticmethod
    def _rn(r, dur, vol=1.0, tau=None):
        a = array.array("f", [(r.random() * 2 - 1) * vol for _ in range(int(dur * SR))])
        return _shape(a, 0.0005, tau, 0.002) if tau else a

    @staticmethod
    def _sum(*parts):
        n = max(len(p) for p in parts)
        out = _buf(n)
        for p in parts:
            for i in range(len(p)):
                out[i] += p[i]
        return out

    @staticmethod
    def _out(buf, level=0.85, power=1.0, ratio=1.0):
        """Final touch: pitch change, peak level that grows with power."""
        return _pitch(_peak(buf, level * min(1.3, 0.55 + 0.5 * power)), ratio)

    def names(self):
        return sorted(n for names in SFX_CATEGORIES.values() for n in names)

    def get(self, name, *args, **kw):
        """An effect by name: sfx.get('punch', power=1.2). Raises a ValueError that lists the names when it does not exist."""
        fn = getattr(self, name, None) if name in self.names() else None
        if fn is None:
            raise ValueError("no sound effect %r. Available: %s" % (name, ", ".join(self.names())))
        return fn(*args, **kw)

    # ---- basic building blocks (the original eight-bit style API) ----
    def tone(self, freq=440.0, dur=0.2, wave="sine", vol=0.5, decay=5.0, sweep=None, attack=0.004, curve="lin"):
        n = int(dur * SR)
        out = _buf(n)
        ph = 0.0
        two_pi = 2 * math.pi
        for i in range(n):
            t = i / float(SR)
            if sweep is None:
                f = freq
            elif curve == "exp":
                f = freq * (sweep / float(freq)) ** (t / dur)
            else:
                f = freq + (sweep - freq) * (t / dur)
            ph += two_pi * f / SR
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

    # ---- fight and impact ----
    def punch(self, power=1.0, variant=None):
        r, k = self._v("punch", variant)
        th = self.tone(r.uniform(150, 215), 0.17, "sine", 1.0, 6.5, sweep=r.uniform(46, 62), curve="exp")
        slap = _biquad(self._rn(r, 0.1, 1.0, 0.022), "bp", r.uniform(900, 1700), 0.9)
        click = _highpass(self._rn(r, 0.006, 1.0, 0.002), 2500)
        out = _soft(_peak(_layers((th, 0, 0.9), (slap, 0, 1.1), (click, 0, 0.5)), 0.9), 1.0 + 0.7 * power)
        return self._out(out, 0.9, power, r.uniform(0.95, 1.06))

    def hit(self, power=1.0, variant=None):
        r, k = self._v("hit", variant)
        th = self.tone(r.uniform(210, 270), 0.13, "tri", 1.0, 8, sweep=r.uniform(60, 80), curve="exp")
        sub = self.tone(r.uniform(85, 100), 0.22, "sine", 1.0, 6, sweep=40, curve="exp")
        nz = _biquad(self._rn(r, 0.12, 1.0, 0.03), "lp", r.uniform(1800, 3200), 0.7)
        out = _soft(_layers((th, 0, 0.7), (sub, 0, 0.9), (nz, 0, 0.8)), 1.0 + 0.6 * power)
        return self._out(out, 0.9, power, r.uniform(0.94, 1.07))

    def kick(self, power=1.0, variant=None):
        r, k = self._v("kick", variant)
        th = self.tone(r.uniform(120, 145), 0.24, "sine", 1.0, 6, sweep=r.uniform(38, 46), curve="exp")
        whap = _biquad(self._rn(r, 0.07, 1.0, 0.016), "bp", r.uniform(700, 1200), 0.8)
        return self._out(_soft(_layers((th, 0, 1.0), (whap, 0, 0.5)), 1.4), 0.9, power, r.uniform(0.96, 1.05))

    def slap(self, power=1.0, variant=None):
        r, k = self._v("slap", variant)
        nz = _biquad(self._rn(r, 0.08, 1.0, 0.016), "bp", r.uniform(2200, 3200), 0.7)
        tn = self.tone(r.uniform(900, 1200), 0.05, "sine", 0.6, 7, sweep=400, curve="exp")
        return self._out(_layers((nz, 0, 1.0), (tn, 0, 0.5)), 0.8, power, r.uniform(0.95, 1.08))

    def thud(self, power=1.0, variant=None):
        r, k = self._v("thud", variant)
        th = self.tone(r.uniform(80, 100), 0.26, "sine", 1.0, 5, sweep=r.uniform(38, 46), curve="exp")
        nz = _biquad(self._rn(r, 0.08, 1.0, 0.02), "lp", 600, 0.7)
        return self._out(_layers((th, 0, 1.0), (nz, 0, 0.5)), 0.85, power, r.uniform(0.95, 1.06))

    def smash(self, power=1.0, variant=None):
        r, k = self._v("smash", variant)
        a = self.punch(1.3, variant=k)
        b = self.boom(0.7, 0.7, variant=k)
        return self._out(_reverb(_layers((a, 0, 1.0), (b, 0.01, 0.8)), 0.3, 0.16, 0.25), 0.95, power, 1.0)

    def crack(self, power=1.0, variant=None):
        r, k = self._v("crack", variant)
        sn = _biquad(self._rn(r, 0.06, 1.0, 0.012), "bp", r.uniform(2400, 3600), 1.2, freq_end=1500)
        res = _layers((self.tone(r.uniform(1700, 2000), 0.06, "sine", 1.0, 8), 0, 0.6), (self.tone(r.uniform(3000, 3400), 0.04, "sine", 1.0, 8), 0, 0.4))
        th = self.tone(130, 0.1, "sine", 1.0, 8, sweep=60, curve="exp")
        return self._out(_layers((sn, 0, 1.0), (res, 0, 0.7), (th, 0.004, 0.6)), 0.85, power, r.uniform(0.96, 1.05))

    def block(self, power=1.0, variant=None):
        r, k = self._v("block", variant)
        f = r.uniform(780, 900)
        parts = [(self.tone(f * m, 0.12, "sine", 1.0, d), 0, g) for m, d, g in ((1.0, 9, 1.0), (1.62, 11, 0.6), (2.57, 14, 0.4))]
        click = _highpass(self._rn(r, 0.01, 1.0, 0.003), 3000)
        parts.append((click, 0, 0.7))
        return self._out(_layers(*parts), 0.75, power, 1.0)

    def clang(self, freq=None, dur=1.0, variant=None):
        r, k = self._v("clang", variant)
        f = freq or r.uniform(520, 760)
        parts = [(self.tone(f * m, dur * dd, "sine", 1.0, 5 + 3 * j), 0, g) for j, (m, g, dd) in enumerate(((1.0, 1.0, 1.0), (2.32, 0.6, 0.8), (4.25, 0.4, 0.6), (6.63, 0.25, 0.45), (9.38, 0.15, 0.3)))]
        parts.append((_highpass(self._rn(r, 0.03, 1.0, 0.008), 2000), 0, 0.9))
        return self._out(_reverb(_layers(*parts), 0.3, 0.12, 0.3), 0.8, 1.0, 1.0)

    def whoosh(self, dur=0.3, vol=0.6, variant=None, rise=None):
        r, k = self._v("whoosh", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * math.sin(math.pi * i / n) ** 1.5 for i in range(n)])
        up = (k % 2 == 0) if rise is None else rise
        f0, f1 = (r.uniform(350, 700), r.uniform(2400, 4200)) if up else (r.uniform(2400, 4200), r.uniform(350, 700))
        return _peak(_biquad(nz, "bp", f0, 1.0, freq_end=f1), min(1.0, vol * 1.3))

    def swing(self, power=1.0, variant=None):
        return self.whoosh(0.16 + 0.04 * power, 0.5, variant)

    def slash(self, dur=0.26, vol=0.55, variant=None):
        r, k = self._v("slash", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * (i / float(n)) ** 0.5 * math.exp(-3.0 * i / n) for i in range(n)])
        out = _highpass(_biquad(nz, "bp", r.uniform(2500, 3500), 1.4, freq_end=r.uniform(6000, 8000)), 1500)
        return _peak(out, vol)

    def ko(self, variant=None):
        r, k = self._v("ko", variant)
        boom = self._sum(self.tone(120, 1.0, "sine", 1.0, 4, sweep=26, curve="exp"), _biquad(self._rn(r, 0.9, 0.7, 0.35), "lp", 500, 0.7))
        return _peak(_reverb(boom, 0.6, 0.3, 0.6), 0.95)

    # ---- movement ----
    def step(self, vol=0.35, surface="wood", variant=None):
        r, k = self._v("step", variant)
        if surface == "dirt":
            out = _biquad(self._rn(r, 0.11, 1.0, 0.03), "lp", r.uniform(450, 700), 0.7)
        elif surface == "grass":
            out = _highpass(_biquad(self._rn(r, 0.13, 1.0, 0.04), "bp", 3500, 0.6), 1800)
        elif surface == "gravel":
            out = self._sum(*[_concat((_highpass(self._rn(r, 0.006, 1.0, 0.002), 1500), r.uniform(0, 0.07))) for _ in range(7)])
            out = _layers((out, 0, 0.8), (_biquad(self._rn(r, 0.1, 0.6, 0.03), "bp", 2200, 0.6), 0, 0.5))
        elif surface == "metal":
            f = r.uniform(900, 1300)
            out = _layers((self.tone(f, 0.18, "sine", 1.0, 7), 0, 0.5), (self.tone(f * 2.4, 0.12, "sine", 1.0, 9), 0, 0.3), (_highpass(self._rn(r, 0.012, 1.0, 0.004), 2500), 0, 0.8))
        elif surface == "sand":
            out = _biquad(self._rn(r, 0.16, 1.0, 0.07), "lp", 900, 0.6)
        elif surface == "concrete":
            out = _layers((_highpass(self._rn(r, 0.02, 1.0, 0.005), 800), 0, 0.9), (self.tone(r.uniform(110, 150), 0.06, "sine", 1.0, 8), 0, 0.6))
        else:                                                      # wood
            out = _layers((self.tone(r.uniform(130, 170), 0.09, "sine", 1.0, 7, sweep=85, curve="exp"), 0, 0.9), (_biquad(self._rn(r, 0.05, 1.0, 0.012), "lp", 1500, 0.7), 0, 0.6))
        return _peak(out, min(1.0, vol * 1.6))

    def slide(self, dur=0.35, vol=0.4, variant=None):
        r, k = self._v("slide", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * min(1.0, i / (0.08 * SR)) * min(1.0, (n - i) / (0.15 * SR)) for i in range(n)])
        return _peak(_biquad(nz, "bp", r.uniform(900, 1300), 0.8, freq_end=r.uniform(500, 800)), min(1.0, vol * 1.5))

    def land(self, power=1.0, variant=None):
        r, k = self._v("land", variant)
        th = self.tone(r.uniform(90, 120), 0.18, "sine", 1.0, 6, sweep=45, curve="exp")
        dust = _biquad(self._rn(r, 0.14, 1.0, 0.04), "lp", 900, 0.7)
        return self._out(_layers((th, 0, 1.0), (dust, 0, 0.6)), 0.8, power, r.uniform(0.95, 1.06))

    def jump(self, vol=0.4, variant=None):
        return _peak(_layers((self.whoosh(0.18, 0.5, variant, rise=True), 0, 0.8), (self.land(0.5, variant), 0.0, 0.3)), min(1.0, vol * 1.6))

    def fall(self, power=1.0, variant=None):
        r, k = self._v("fall", variant)
        a = self.tone(r.uniform(75, 90), 0.4, "sine", 1.0, 4, sweep=34, curve="exp")
        b = _biquad(self._rn(r, 0.3, 1.0, 0.09), "lp", 700, 0.7)
        c = self.thud(0.5, variant=k)
        return self._out(_layers((a, 0, 1.0), (b, 0, 0.7), (c, 0.2, 0.5)), 0.9, power, 1.0)

    def cloth(self, dur=0.25, vol=0.25, variant=None):
        r, k = self._v("cloth", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * (0.5 + 0.5 * math.sin(i / SR * r.uniform(40, 60))) * math.sin(math.pi * i / n) for i in range(n)])
        return _peak(_biquad(nz, "bp", 2400, 0.5), min(1.0, vol * 1.6))

    # ---- voices (simple formant synthesis: cartoon grunts, not speech) ----
    def _voice(self, r, vowel, dur, f0, f1=None, vol=0.7, vib=0.0, breath=0.15):
        f1 = f0 if f1 is None else f1
        n = int(dur * SR)
        src = _buf(n)
        ph = 0.0
        for i in range(n):
            u = i / float(n)
            f = (f0 + (f1 - f0) * u) * (1 + vib * math.sin(2 * math.pi * 5.8 * i / SR) + (r.random() - 0.5) * 0.01)
            ph += f / SR
            ph -= int(ph)
            src[i] = (1.0 - 2.0 * ph) * 0.9 + (r.random() * 2 - 1) * breath
        fo = _FORMANTS[vowel]
        out = _layers(*[(_biquad(src, "bp", fq, q), 0, g) for fq, q, g in zip(fo, (6, 8, 10), (1.0, 0.7, 0.35))])
        return _peak(_shape(out, 0.012, dur * 0.9, 0.03), vol)

    def kiai(self, vol=0.7, variant=None):
        r, k = self._v("kiai", variant)
        f = r.uniform(230, 300)
        return self._voice(r, "a", 0.3, f, f * 0.78, vol, 0.01, 0.3)

    def grunt(self, vol=0.6, variant=None):
        r, k = self._v("grunt", variant)
        f = r.uniform(95, 135)
        return self._voice(r, "uh", 0.2, f, f * 0.75, vol, 0.0, 0.25)

    def pain(self, vol=0.65, variant=None):
        r, k = self._v("pain", variant)
        f = r.uniform(260, 340)
        return self._voice(r, "o", 0.38, f, f * 0.5, vol, 0.03, 0.2)

    def gasp(self, vol=0.4, variant=None):
        r, k = self._v("gasp", variant)
        n = int(0.32 * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * (i / float(n)) ** 1.5 * math.exp(-2.0 * i / n) for i in range(n)])
        return _peak(_biquad(nz, "bp", 1500, 0.7), vol)

    def laugh(self, vol=0.5, variant=None):
        r, k = self._v("laugh", variant)
        f = r.uniform(200, 260)
        return _concat(*[(self._voice(r, "a", 0.1, f * (1 - 0.03 * j), f * (0.95 - 0.03 * j), vol, 0.02, 0.2), 0.0 if j == 0 else 0.07) for j in range(4)])

    # ---- crowd ----
    def crowd(self, dur=2.0, vol=0.3):
        n = int(dur * SR)
        out = _lowpass(self.noise(dur, vol, 0.0), 0.08)
        for i in range(n):
            u = i / float(n)
            out[i] *= min(1.0, u * 6) * min(1.0, (1 - u) * 3) * 3.0
        return out

    def cheer(self, dur=2.2, vol=0.4, variant=None):
        r, k = self._v("cheer", variant)
        n = int(dur * SR)
        lfo = [r.uniform(5, 9) for _ in range(3)]
        nz = array.array("f", [(r.random() * 2 - 1) * (0.6 + 0.2 * (math.sin(i / SR * lfo[0]) + math.sin(i / SR * lfo[1]) + math.sin(i / SR * lfo[2]))) * min(1.0, i / (0.25 * SR)) * min(1.0, (n - i) / (0.6 * SR)) for i in range(n)])
        out = _layers((_biquad(nz, "bp", 900, 0.6), 0, 1.0), (_biquad(nz, "bp", 2100, 0.7), 0, 0.6))
        return _peak(out, vol)

    def applause(self, dur=2.5, vol=0.35, variant=None):
        r, k = self._v("applause", variant)
        parts = []
        for _ in range(int(dur * 70)):
            t = r.random() * dur
            dens = min(1.0, t / (0.5 * dur) + 0.3) * min(1.0, (dur - t) / 0.8 + 0.2)
            if r.random() < dens:
                parts.append((_biquad(self._rn(r, 0.014, r.uniform(0.4, 1.0), 0.004), "bp", r.uniform(1500, 3200), 1.0), t, 1.0))
        return _peak(_layers(*parts), vol) if parts else _buf(int(dur * SR))

    def ooh(self, dur=1.0, vol=0.3, variant=None):
        r, k = self._v("ooh", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * math.sin(math.pi * i / n) ** 1.3 for i in range(n)])
        return _peak(_biquad(nz, "bp", 380, 1.8, freq_end=520), vol)

    # ---- cinematic ----
    def boom(self, dur=1.5, vol=0.9, variant=None):
        r, k = self._v("boom", variant)
        out = self._sum(self.tone(r.uniform(62, 78), dur, "sine", 1.0, 3.5, sweep=28, curve="exp"), _biquad(self._rn(r, dur * 0.7, 0.6, dur * 0.18), "lp", 300, 0.7))
        return _peak(_reverb(out, 0.5, 0.22, 0.5), vol)

    def impact(self, power=1.0, variant=None):
        r, k = self._v("impact", variant)
        b = self.boom(1.0, 0.9, variant=k)
        h = self.punch(1.4, variant=k)
        ring = self.tone(r.uniform(900, 1300), 0.6, "sine", 0.25, 6)
        return self._out(_layers((b, 0, 1.0), (h, 0.0, 0.9), (ring, 0.0, 0.5)), 0.95, power, 1.0)

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

    def downer(self, dur=1.2, vol=0.4):
        out = self.riser(dur, vol)
        out.reverse()
        return out

    def stinger(self, dur=1.6, vol=0.5, variant=None):
        r, k = self._v("stinger", variant)
        root = r.uniform(100, 130)
        parts = [(self.tone(root * m, dur, "saw", 1.0, 2.5, attack=0.25), 0, g) for m, g in ((1.0, 1.0), (1.189, 0.8), (1.414, 0.7), (1.498, 0.5), (2.0, 0.4))]
        return _peak(_biquad(_layers(*parts), "lp", 1800, 0.8, freq_end=500), vol)

    def heartbeat(self, beats=3, bpm=70, vol=0.7):
        gap = 60.0 / bpm
        one = _layers((self.tone(62, 0.16, "sine", 1.0, 6, sweep=40, curve="exp"), 0, 1.0), (self.tone(54, 0.16, "sine", 1.0, 6, sweep=36, curve="exp"), 0.17, 0.75))
        return _peak(_layers(*[(one, i * gap, 1.0) for i in range(int(beats))]), vol)

    def gong(self, dur=2.8, vol=0.7, variant=None):
        r, k = self._v("gong", variant)
        f = r.uniform(95, 125)
        parts = [(self.tone(f * m, dur * dd, "sine", 1.0, 3 + j, attack=0.01), 0, g) for j, (m, g, dd) in enumerate(((1.0, 1.0, 1.0), (1.52, 0.7, 0.9), (2.01, 0.6, 0.8), (2.77, 0.45, 0.65), (3.9, 0.3, 0.5), (5.3, 0.2, 0.4)))]
        parts.append((_biquad(self._rn(r, 0.25, 1.0, 0.08), "bp", 900, 0.5), 0, 0.5))
        return _peak(_reverb(_layers(*parts), 0.6, 0.25, 0.8), vol)

    def taiko(self, power=1.0, variant=None):
        r, k = self._v("taiko", variant)
        out = _layers((self.tone(r.uniform(95, 110), 0.5, "sine", 1.0, 4, sweep=48, curve="exp"), 0, 1.0), (_biquad(self._rn(r, 0.08, 1.0, 0.02), "lp", 1200, 0.7), 0, 0.8))
        return self._out(_reverb(_soft(out, 1.3), 0.4, 0.15, 0.3), 0.9, power, 1.0)

    def drum_roll(self, dur=1.5, vol=0.5, variant=None):
        r, k = self._v("drum_roll", variant)
        parts, t = [], 0.0
        while t < dur:
            parts.append((self.snare(0.5 + 0.8 * t / dur, variant=int(t * 100)), t, 0.35 + 0.65 * t / dur))
            t += 0.055
        return _peak(_layers(*parts), vol)

    def cymbal(self, dur=1.6, vol=0.45, variant=None):
        r, k = self._v("cymbal", variant)
        return _peak(_highpass(self._rn(r, dur, 1.0, dur * 0.3), 5500), vol)

    def rimshot(self, vol=0.6):
        return _peak(_concat((self.snare(0.8, variant=1), 0.0), (self.kick(0.8, variant=1), 0.22), (self.cymbal(0.9, 0.6, variant=2), 0.2)), vol)

    def explosion(self, dur=1.2, variant=None):
        r, k = self._v("explosion", variant)
        out = self._sum(_biquad(self._rn(r, dur, 0.9, dur * 0.28), "lp", r.uniform(500, 900), 0.7), self.tone(90, dur, "sine", 0.9, 3.5, sweep=24, curve="exp"),
                        _highpass(self._rn(r, dur * 0.5, 0.3, dur * 0.12), 2500))
        return _peak(_reverb(out, 0.5, 0.2, 0.45), 0.95)

    # ---- nature ----
    def wind(self, dur=3.0, vol=0.3, variant=None):
        r, k = self._v("wind", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * (0.55 + 0.45 * math.sin(i / SR * 1.7 + k)) * min(1.0, i / (0.5 * SR)) * min(1.0, (n - i) / (0.6 * SR)) for i in range(n)])
        return _peak(_biquad(nz, "bp", 350, 1.2, freq_end=800), vol)

    def thunder(self, dur=3.0, vol=0.8, variant=None):
        r, k = self._v("thunder", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * min(1.0, i / (0.25 * SR)) * math.exp(-1.6 * i / n) * (0.7 + 0.3 * math.sin(i / SR * 9.0)) for i in range(n)])
        return _peak(_reverb(_biquad(nz, "lp", 260, 0.7), 0.6, 0.2, 0.6), vol)

    def rain(self, dur=3.0, vol=0.25, variant=None):
        r, k = self._v("rain", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * min(1.0, i / (0.4 * SR)) * min(1.0, (n - i) / (0.5 * SR)) for i in range(n)])
        return _peak(_layers((_highpass(nz, 3000), 0, 1.0), (_biquad(nz, "bp", 6500, 0.6), 0, 0.5)), vol)

    def fire(self, dur=2.0, vol=0.25, variant=None):
        r, k = self._v("fire", variant)
        n = int(dur * SR)
        base = _biquad(array.array("f", [(r.random() * 2 - 1) * 0.5 for _ in range(n)]), "lp", 700, 0.7)
        crackles = [(_highpass(self._rn(r, 0.01, r.uniform(0.4, 1.0), 0.003), 2000), r.random() * (dur - 0.05), 1.0) for _ in range(int(dur * 14))]
        return _peak(_layers((base, 0, 0.6), *crackles), vol)

    def drip(self, variant=None):
        r, k = self._v("drip", variant)
        f = r.uniform(1100, 1700)
        return _peak(_layers((self.tone(f, 0.06, "sine", 1.0, 5, sweep=f * 0.55, curve="exp"), 0, 1.0), (self.tone(f * 0.5, 0.25, "sine", 0.3, 9), 0.01, 0.3)), 0.6)

    def splash(self, dur=0.5, vol=0.5, variant=None):
        r, k = self._v("splash", variant)
        n = int(dur * SR)
        nz = array.array("f", [(r.random() * 2 - 1) * math.exp(-5.0 * i / n) * min(1.0, i / (0.01 * SR)) for i in range(n)])
        return _peak(_biquad(nz, "bp", 1400, 0.6, freq_end=3200), vol)

    # ---- interface and eight-bit ----
    def bell(self, freq=880.0, dur=1.0, vol=0.5):
        return self._sum(*[self.tone(freq * m, dur, "sine", vol * a, d) for m, a, d in ((1.0, 1.0, 4), (2.76, 0.5, 6), (5.4, 0.25, 9))])

    def ding(self, freq=1320.0):
        return self.tone(freq, 0.35, "sine", 0.5, 7)

    def pop(self):
        return self.tone(700, 0.08, "sine", 0.6, 7, sweep=200)

    def click(self):
        return self.tone(1800, 0.02, "square", 0.3, 9)

    def coin(self):
        return _concat((self.tone(988, 0.07, "square", 0.3, 3), 0.0), (self.tone(1319, 0.28, "square", 0.3, 6), 0.0))

    def error(self):
        return self._sum(self.tone(180, 0.25, "saw", 0.35, 3), self.tone(185, 0.25, "square", 0.2, 3))

    def laser(self, dur=0.25):
        return self.tone(1600, dur, "saw", 0.3, 5, sweep=200)

    def blip(self, freq=660.0, dur=0.08):
        return self.tone(freq, dur, "square", 0.25, 4)

    def success(self):
        return _concat(*[(self.tone(note_freq(n), 0.11 if n != "C6" else 0.4, "square", 0.25, 4), 0.0) for n in ("C5", "E5", "G5", "C6")])

    def fail(self):
        return _concat(*[(self.tone(note_freq(n), 0.16 if n != "C3" else 0.5, "square", 0.25, 4), 0.0) for n in ("G3", "E3", "D3", "C3")])

    def powerup(self):
        return _concat(*[(self.tone(note_freq(n), 0.06, "square", 0.22, 2), 0.0) for n in ("C4", "E4", "G4", "C5", "E5", "G5", "C6")])

    def zap(self, variant=None):
        r, k = self._v("zap", variant)
        return _peak(self._sum(self.tone(2200, 0.22, "saw", 0.7, 4, sweep=120, curve="exp"), self._rn(r, 0.22, 0.3, 0.06)), 0.6)

    def select(self):
        return _concat((self.tone(880, 0.05, "square", 0.2, 3), 0.0), (self.tone(1320, 0.08, "square", 0.2, 5), 0.0))

    def notify(self):
        return _concat((self.tone(1318, 0.12, "sine", 0.4, 5), 0.0), (self.tone(1760, 0.3, "sine", 0.4, 6), 0.02))

    # ---- machines ----
    def beep(self, freq=1000.0, dur=0.15, vol=0.3):
        return _shape(self.tone(freq, dur, "square", vol, 0.0), 0.003, None, 0.01)

    def alarm(self, dur=1.5, vol=0.3):
        return _concat(*[(self.beep(800 if i % 2 == 0 else 1000, 0.22, vol), 0.0) for i in range(int(dur / 0.22))])

    def engine(self, dur=2.0, rpm=1800, vol=0.35, variant=None):
        r, k = self._v("engine", variant)
        n = int(dur * SR)
        out = _buf(n)
        ph = 0.0
        for i in range(n):
            f = (rpm / 60.0) * 2.0 * (1.0 + 0.25 * i / n)
            ph += f / SR
            ph -= int(ph)
            out[i] = (1.0 - 2.0 * ph) * 0.6 + math.sin(2 * math.pi * ph * 2) * 0.3 + (r.random() * 2 - 1) * 0.15
        return _peak(_biquad(out, "lp", 700, 0.8), vol)

    def camera(self):
        return _concat((_highpass(self.noise(0.012, 0.8, 8), 1500), 0.0), (_highpass(self.noise(0.012, 0.6, 8), 1200), 0.06))

    def key(self, variant=None):
        r, k = self._v("key", variant)
        return _peak(_layers((_highpass(self._rn(r, 0.012, 1.0, 0.003), 1800), 0, 1.0), (self.tone(r.uniform(200, 260), 0.04, "sine", 1.0, 8), 0, 0.5)), 0.4)

    def snare(self, power=1.0, variant=None):
        r, k = self._v("snare", variant)
        out = _layers((_highpass(self._rn(r, 0.17, 1.0, 0.045), 900), 0, 0.9), (self.tone(r.uniform(180, 210), 0.1, "tri", 0.8, 9), 0, 0.6))
        return self._out(out, 0.7, power, 1.0)

    def hat(self, power=1.0, open_=False, variant=None):
        r, k = self._v("hat", variant)
        return self._out(_highpass(self._rn(r, 0.2 if open_ else 0.045, 1.0, 0.07 if open_ else 0.012), 6500), 0.4, power, 1.0)

    # ---- weapons and creatures ----
    def gunshot(self, power=1.0, variant=None):
        r, k = self._v("gunshot", variant)
        crack = _highpass(self._rn(r, 0.05, 1.0, 0.009), 1200)
        body = _biquad(self._rn(r, 0.16, 1.0, 0.04), "bp", r.uniform(500, 900), 0.7)
        thump = self.tone(r.uniform(130, 170), 0.14, "sine", 1.0, 7, sweep=48, curve="exp")
        out = _soft(_layers((crack, 0, 1.0), (body, 0, 0.8), (thump, 0, 0.9)), 1.6)
        return self._out(_reverb(out, 0.35, 0.12, 0.35), 0.95, power, r.uniform(0.96, 1.05))

    def rifle(self, power=1.0, variant=None):
        k = self._v("rifle", variant)[1]
        return _pitch(self.gunshot(power, variant=100 + k), 0.86)

    def pistol(self, power=1.0, variant=None):
        k = self._v("pistol", variant)[1]
        return _pitch(self.gunshot(power * 0.8, variant=200 + k), 1.18)

    def reload(self, variant=None):
        r, k = self._v("reload", variant)
        click = lambda f: _layers((_highpass(self._rn(r, 0.012, 1.0, 0.003), 1800), 0, 1.0), (self.tone(f, 0.05, "sine", 1.0, 9), 0, 0.5))
        return _peak(_layers((click(r.uniform(900, 1100)), 0.0, 0.9), (click(r.uniform(1300, 1500)), 0.26, 1.0), (self.thud(0.4, variant=k), 0.5, 0.5), (click(r.uniform(1700, 1900)), 0.62, 1.0)), 0.7)

    def shell(self, variant=None):
        r, k = self._v("shell", variant)
        f = r.uniform(3800, 4800)
        return _peak(_layers(*[(self.tone(f * (1 + 0.03 * j), 0.07, "sine", 1.0, 9), 0.0 + j * (0.07 + 0.03 * j), 0.9 - 0.3 * j) for j in range(3)]), 0.4)

    def groan(self, dur=0.9, vol=0.5, variant=None):
        r, k = self._v("groan", variant)
        f = r.uniform(70, 95)
        return self._voice(r, "o", dur, f, f * 0.8, vol, 0.04, 0.35)

    def roar(self, vol=0.6, variant=None):
        r, k = self._v("roar", variant)
        f = r.uniform(120, 150)
        return _soft(self._voice(r, "a", 1.0, f, f * 0.8, vol, 0.03, 0.5), 1.4)

    def zombie_death(self, variant=None):
        r, k = self._v("zombie_death", variant)
        f = r.uniform(100, 125)
        return _peak(_layers((self._voice(r, "uh", 0.5, f, f * 0.5, 0.7, 0.02, 0.4), 0, 1.0), (self.thud(0.8, variant=k), 0.38, 0.6)), 0.7)

    # ---- cartoon ----
    def boing(self, dur=0.55, vol=0.5, variant=None):
        r, k = self._v("boing", variant)
        n = int(dur * SR)
        out = _buf(n)
        ph = 0.0
        base = r.uniform(180, 260)
        for i in range(n):
            u = i / float(n)
            f = base * (1.0 + 2.2 * math.exp(-4 * u) * (0.5 + 0.5 * math.sin(2 * math.pi * 9 * u)))
            ph += 2 * math.pi * f / SR
            out[i] = math.sin(ph) * math.exp(-3.5 * u) * min(1.0, i / (0.004 * SR))
        return _peak(out, vol)

    def whistle(self, up=True, dur=0.6, vol=0.4):
        a, b = (350.0, 1700.0) if up else (1700.0, 350.0)
        n = int(dur * SR)
        out = _buf(n)
        ph = 0.0
        for i in range(n):
            u = i / float(n)
            f = a * (b / a) ** u * (1 + 0.012 * math.sin(2 * math.pi * 7 * u * dur))
            ph += 2 * math.pi * f / SR
            out[i] = math.sin(ph) * min(1.0, u * 20) * min(1.0, (1 - u) * 12)
        return _peak(out, vol)

    def bonk(self, variant=None):
        r, k = self._v("bonk", variant)
        return _peak(_layers((self.tone(r.uniform(300, 360), 0.14, "square", 0.6, 6, sweep=150, curve="exp"), 0, 1.0), (_biquad(self._rn(r, 0.02, 1.0, 0.006), "bp", 1800, 1.0), 0, 0.7)), 0.7)

    def honk(self, vol=0.4):
        return _peak(_biquad(_layers((self.tone(330, 0.28, "saw", 1.0, 1.5, attack=0.01), 0, 1.0), (self.tone(349, 0.28, "saw", 1.0, 1.5, attack=0.01), 0, 0.9)), "lp", 1500, 0.8), vol)

    def squeak(self, vol=0.4, variant=None):
        r, k = self._v("squeak", variant)
        f = r.uniform(1800, 2600)
        return _peak(self.tone(f, 0.12, "sine", 1.0, 3, sweep=f * 1.5), vol)

    def trombone(self, vol=0.5):
        notes = (("D3", 0.42), ("Db3", 0.42), ("C3", 0.42), ("B2", 1.0))
        parts = []
        for j, (nm, d) in enumerate(notes):
            f = note_freq(nm)
            parts.append((_biquad(self.tone(f, d, "saw", 1.0, 0.8, sweep=f * (0.93 if j == 3 else 0.98), attack=0.04), "lp", 900, 1.2), 0.0))
        return _peak(_concat(*parts), vol)


sfx = _Sfx()


# ---- sound files and free sounds from the internet ----
class SoundError(RuntimeError):
    """A sound could not be read, found or downloaded. The message says what to do."""


UA = "LumoCode-lumovideo/%s (+https://github.com/alfar988/Lumo-code)" % __version__
_SOUND_EXT = (".wav", ".mp3", ".ogg", ".oga", ".flac", ".m4a", ".aac", ".opus")


def _sound_dir(folder=None):
    return os.path.abspath(folder or os.environ.get("LUMO_SOUNDS_DIR") or SOUND_DIR)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _read_wav(path):
    with wave.open(path, "rb") as w:
        ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        a = array.array("h")
        a.frombytes(raw[:len(raw) // 2 * 2])
        if sys.byteorder == "big":
            a.byteswap()
        vals = [x / 32768.0 for x in a]
    elif sw == 1:
        vals = [(b - 128) / 128.0 for b in raw]
    elif sw == 3:
        vals = [int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608.0 for i in range(0, len(raw) - 2, 3)]
    elif sw == 4:
        a = array.array("i")
        a.frombytes(raw[:len(raw) // 4 * 4])
        if sys.byteorder == "big":
            a.byteswap()
        vals = [x / 2147483648.0 for x in a]
    else:
        raise SoundError("unsupported WAV format (%d-bit)" % (sw * 8))
    if ch > 1:
        vals = [sum(vals[i:i + ch]) / ch for i in range(0, len(vals) - ch + 1, ch)]
    buf = array.array("f", vals)
    return buf if rate == SR else _pitch(buf, rate / float(SR))


def _decode_ffmpeg(path, start=0.0, dur=None):
    ff = ffmpeg_path()
    if not ff:
        raise SoundError("ffmpeg is needed to read %s files (Termux: pkg install ffmpeg). A .wav file works without it." % (os.path.splitext(path)[1] or "this kind of"))
    cmd = [ff, "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", "%.3f" % start]
    cmd += ["-i", path]
    if dur:
        cmd += ["-t", "%.3f" % dur]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        raise SoundError("ffmpeg could not run: %s" % e)
    if r.returncode != 0 or len(r.stdout) < 4:
        raise SoundError("ffmpeg could not read %s: %s" % (os.path.basename(path), r.stderr.decode("utf-8", "replace").strip()[-200:] or "no audio found"))
    a = array.array("h")
    a.frombytes(r.stdout[:len(r.stdout) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    return array.array("f", [x / 32768.0 for x in a])


def _trim_silence(buf):
    pk = max(map(abs, buf)) if len(buf) else 0.0
    if pk < 1e-6:
        return buf
    lo_t, hi_t = pk * 0.02, pk * 0.004
    n = len(buf)
    lo = next((i for i in range(n) if abs(buf[i]) >= lo_t), 0)
    hi = next((i for i in range(n - 1, -1, -1) if abs(buf[i]) >= hi_t), n - 1)
    return buf[max(0, lo - 220):min(n, hi + 2205)]


def load_sound(path, vol=1.0, start=0.0, dur=None, normalize=True, trim=True):
    """Read a sound file (wav always; mp3, ogg, flac, m4a ... with ffmpeg) into a mono buffer that v.sound(...) and Mixer.add(...) accept.
    start / dur pick a part in seconds, trim removes silence at both ends, normalize sets the loudest point to 90 percent, vol scales after that."""
    p = path
    if not os.path.isfile(p):
        alt = os.path.join(_sound_dir(), path)
        if not os.path.isfile(alt):
            raise SoundError("sound file not found: %s (looked in the current folder and in %s)" % (path, _sound_dir()))
        p = alt
    buf = None
    if p.lower().endswith(".wav"):
        try:
            buf = _read_wav(p)
            s0 = int(start * SR)
            buf = buf[s0:s0 + int(dur * SR)] if dur else buf[s0:]
        except (wave.Error, EOFError, SoundError):
            buf = None
    if buf is None:
        buf = _decode_ffmpeg(p, start, dur)
    if trim:
        buf = _trim_silence(buf)
    if normalize:
        buf = _peak(buf, 0.9)
    if vol != 1.0:
        buf = _scale(buf, vol)
    return _fade(buf, 0.0, 0.015)


def _write_wav(path, buf):
    a = array.array("h", [int(max(-32767.0, min(32767.0, x * 32767.0))) for x in buf])
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(a.tobytes() if sys.byteorder == "little" else _swap(a))


def _safe_url(url):
    """Only https, and never an address inside this device or network (a link must not be able to reach private services)."""
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not u.hostname:
        raise SoundError("only https:// links are allowed for downloads")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise SoundError("cannot reach %s (%s)" % (u.hostname, e))
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise SoundError("%s points to a private address; refused" % u.hostname)
    return url


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _safe_url(newurl)
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def _http_get(url, headers=None, timeout=20, max_bytes=15 * 1024 * 1024):
    _safe_url(url)
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept": "*/*"}, **(headers or {})))
    opener = urllib.request.build_opener(_SafeRedirect())
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = bytearray()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > max_bytes:
                    raise SoundError("the file is larger than %d MB; cancelled" % (max_bytes >> 20))
            return bytes(data), (resp.headers.get("Content-Type") or "")
    except SoundError:
        raise
    except urllib.error.HTTPError as e:
        raise SoundError("the server answered %s (%s)" % (e.code, urllib.parse.urlparse(url).netloc))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SoundError("no internet connection or the server is down (%s)" % (getattr(e, "reason", None) or e))


def _json_get(url, headers=None):
    data, _ = _http_get(url, headers, max_bytes=3 * 1024 * 1024)
    try:
        return json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        raise SoundError("the sound service sent something that is not JSON")


def _license_code(text):
    t = (text or "").lower()
    if "zero" in t or "cc0" in t or t.strip() == "cc0":
        return "cc0"
    if "publicdomain/mark" in t or t.strip() == "pdm":
        return "pdm"
    if "by-nc" in t or "noncommercial" in t.replace("-", "") or "by-nd" in t or "by-sa" in t:
        return "other"
    if "/by/" in t or t.strip() in ("by", "attribution"):
        return "by"
    return "other"


def _search_openverse(q, limit, max_seconds, safe):
    out = []
    for cat in ("sound_effect", ""):
        params = {"q": q, "page_size": str(min(20, max(limit * 3, 8)))}
        if safe:
            params["license"] = "cc0,pdm,by"
        if cat:
            params["category"] = cat
        js = _json_get("https://api.openverse.org/v1/audio/?" + urllib.parse.urlencode(params))
        for it in js.get("results", []) or []:
            url = it.get("url") or ""
            dur = (it.get("duration") or 0) / 1000.0
            if not url.startswith("https://") or dur > 60:
                continue
            lic = it.get("license") or ""
            out.append({"title": it.get("title") or q, "creator": it.get("creator") or "unknown", "license": ("cc-" + lic + (" " + str(it.get("license_version")) if it.get("license_version") else "")).strip() if lic else "unknown",
                        "license_code": _license_code(lic), "duration": round(dur, 2), "url": url, "page": it.get("foreign_landing_url") or it.get("url"), "source": "openverse/" + str(it.get("source") or it.get("provider") or "")})
        if out:
            break
    return out


def _search_freesound(q, limit, max_seconds, safe):
    key = os.environ.get("FREESOUND_API_KEY")
    flt = "duration:[0 TO %d]" % max(2, int(max_seconds * 3))
    if safe:
        flt += ' (license:"Creative Commons 0" OR license:"Attribution")'
    params = {"query": q, "filter": flt, "fields": "id,name,duration,license,username,previews,url", "page_size": str(min(15, max(limit * 3, 6)))}
    js = _json_get("https://freesound.org/apiv2/search/text/?" + urllib.parse.urlencode(params), {"Authorization": "Token %s" % key})
    out = []
    for it in js.get("results", []) or []:
        pv = it.get("previews") or {}
        url = pv.get("preview-hq-mp3") or pv.get("preview-hq-ogg") or pv.get("preview-lq-mp3") or ""
        if not url.startswith("https://"):
            continue
        code = _license_code(it.get("license"))
        if safe and code == "other":
            continue
        out.append({"title": it.get("name") or q, "creator": it.get("username") or "unknown", "license": {"cc0": "CC0", "by": "CC-BY"}.get(code, it.get("license") or "unknown"), "license_code": code,
                    "duration": round(float(it.get("duration") or 0), 2), "url": url, "page": it.get("url") or "https://freesound.org/", "source": "freesound"})
    return out


def find_sounds(query, limit=6, max_seconds=6.0, source="auto", safe=True):
    """Search free sound effects on the internet. Returns a list of {title, creator, license, license_code, duration, url, page, source}.
    source: 'auto' (Freesound when the FREESOUND_API_KEY environment variable is set, then Openverse), 'freesound' or 'openverse'.
    safe=True keeps only CC0, public domain and CC-BY sounds (usable in a video you publish; CC-BY needs a credit, see sound_credits())."""
    q = (query or "").strip()
    if not q:
        raise SoundError("what sound? give a few words, for example 'punch' or 'door slam'")
    if source == "auto":
        order = (["freesound"] if os.environ.get("FREESOUND_API_KEY") else []) + ["openverse"]
    elif source in ("freesound", "openverse"):
        order = [source]
    else:
        raise SoundError("source must be auto, freesound or openverse")
    errors, found = [], []
    for src in order:
        if src == "freesound" and not os.environ.get("FREESOUND_API_KEY"):
            errors.append("freesound: no FREESOUND_API_KEY set")
            continue
        try:
            found = _search_freesound(q, limit, max_seconds, safe) if src == "freesound" else _search_openverse(q, limit, max_seconds, safe)
        except SoundError as e:
            errors.append("%s: %s" % (src, e))
            continue
        if found:
            break
    if not found and errors:
        raise SoundError("; ".join(errors))
    found.sort(key=lambda it: (it["duration"] > max_seconds, it["duration"]))
    return found[:max(1, int(limit))]


def fetch_sound(item, name=None, max_seconds=6.0, folder=None):
    """Download one sound (an item from find_sounds or a direct https link to an audio file), cut it to max_seconds, convert it to a mono
    WAV in the sounds folder and write the credit line to CREDITS.txt. Returns the WAV path. A sound that is already there is reused."""
    if isinstance(item, str):
        host = urllib.parse.urlparse(item).netloc
        item = {"url": item, "title": name or os.path.splitext(os.path.basename(urllib.parse.urlparse(item).path))[0] or "sound", "creator": "unknown", "license": "unknown (check the source)", "page": item, "source": host}
    url = item.get("url") or ""
    folder = _sound_dir(folder)
    os.makedirs(folder, exist_ok=True)
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:6]
    slug = (_slug(name or item.get("title") or "sound")[:36] or "sound")
    dest = os.path.join(folder, "%s-%s.wav" % (slug, h))
    if os.path.isfile(dest):
        return dest
    data, ctype = _http_get(url)
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext not in _SOUND_EXT:
        ext = ".mp3" if "mpeg" in ctype else ".ogg" if "ogg" in ctype else ".wav" if "wav" in ctype else ".bin"
    tmpf = os.path.join(folder, ".download-%s%s" % (h, ext))
    with open(tmpf, "wb") as f:
        f.write(data)
    try:
        buf = load_sound(tmpf, dur=max_seconds, normalize=True, trim=True)
    finally:
        try:
            os.remove(tmpf)
        except OSError:
            pass
    _write_wav(dest, buf)
    line = '%s | "%s" by %s | license: %s | source: %s' % (os.path.basename(dest), item.get("title"), item.get("creator"), item.get("license"), item.get("page") or url)
    try:
        with open(os.path.join(folder, "CREDITS.txt"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    return dest


def sound_credits(folder=None):
    """The credit lines of every downloaded sound (CC-BY sounds must be credited when you publish the video)."""
    try:
        with open(os.path.join(_sound_dir(folder), "CREDITS.txt"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _read_json_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


_GUESS = {"swish": "whoosh", "swoosh": "whoosh", "footstep": "step", "footsteps": "step", "walk": "step", "door": "thud", "slam": "thud", "bang": "boom", "glass": "crack",
          "wood": "crack", "sword": "clang", "metal": "clang", "clash": "clang", "gunshot": "boom", "laser": "laser", "blast": "explosion", "bomb": "explosion",
          "clap": "applause", "scream": "pain", "yell": "kiai", "shout": "kiai", "cheering": "cheer", "water": "splash", "bubble": "pop", "storm": "thunder"}


def _sfx_net(self, query, n=3, pick=0, max_seconds=4.0, fallback=None, vol=1.0, source="auto", folder=None):
    """A real recording from the internet (free CC0 / CC-BY sounds, cached in the sounds folder so it downloads once).
    sfx.net('punch'), sfx.net('footstep gravel', pick=2) for another take. Without internet it returns a synthesised effect instead
    (fallback='punch' or a function picks which) and says so in the log, so the render never fails because of a missing connection."""
    d = _sound_dir(folder)
    key = _slug(query)
    idx_path = os.path.join(d, "index.json")
    idx = _read_json_file(idx_path)
    files = [os.path.join(d, f) for f in idx.get(key, []) if os.path.isfile(os.path.join(d, f))]
    if not files:
        try:
            files = []
            for it in find_sounds(query, limit=max(1, n), max_seconds=max_seconds, source=source):
                try:
                    files.append(fetch_sound(it, name=query, max_seconds=max_seconds, folder=d))
                except SoundError as e:
                    print("  ! skipped one sound for %r: %s" % (query, e), flush=True)
                if len(files) >= n:
                    break
            if files:
                idx[key] = [os.path.basename(f) for f in files]
                os.makedirs(d, exist_ok=True)
                with open(idx_path, "w", encoding="utf-8") as f:
                    json.dump(idx, f, indent=1)
        except SoundError as e:
            print("  ! no internet sound for %r (%s); using a synthesised effect" % (query, e), flush=True)
    if files:
        return load_sound(files[int(pick) % len(files)], vol=vol)
    if callable(fallback):
        return fallback()
    if isinstance(fallback, str) and fallback in self.names():
        return self.get(fallback)
    words = re.findall(r"[a-z]+", query.lower())
    names = self.names()
    for w in words:
        if w in names:
            return self.get(w)
        if w in _GUESS:
            return self.get(_GUESS[w])
    return self.hit(0.8)


_Sfx.net = _sfx_net
_Sfx.file = lambda self, path, vol=1.0, start=0.0, dur=None, normalize=True, trim=True: load_sound(path, vol, start, dur, normalize, trim)
_Sfx.file.__doc__ = "A sound file as a buffer: sfx.file('sounds/punch.wav'). See load_sound."



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
        kick, snare, hat, hat_o = sfx.kick(0.9, variant=0), sfx.snare(0.6, variant=0), sfx.hat(0.5, variant=0), sfx.hat(0.5, True, variant=1)
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
    "draft": dict(scale=0.375, ss=1, fps=24, crf=29, preset="ultrafast", blur=1),        # fast preview, 480x270
    "standard": dict(scale=2 / 3.0, ss=2, fps=60, crf=21, preset="veryfast", blur=1),    # 854x480, smooth 60 fps, the default
    "hd": dict(scale=1.0, ss=2, fps=60, crf=19, preset="veryfast", blur=1),              # 1280x720
    "fhd": dict(scale=1.5, ss=2, fps=60, crf=18, preset="veryfast", blur=1),             # 1920x1080
}
# blur = samples drawn per output frame and averaged (motion blur). At 60 fps one sample is enough; a script that asks for 30 fps or less
# automatically gets 3 samples so fast moves do not look choppy. Video(..., blur=N) or LUMO_VIDEO_BLUR=N overrides it.


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
    the output resolution, frame rate and encoder effort, never your drawing code. The environment variable LUMO_VIDEO_QUALITY overrides it.
    fps: leave it out for the smooth default of the quality (60 fps; draft 24). A number is an upper limit (fps=30 gives 30 fps with motion blur).
    blur: samples averaged per frame (motion blur). None = automatic, 1 = off, 3-4 = soft and filmic."""

    SHUTTER = 0.5                        # exposure as a fraction of the frame time (0.5 = the 180 degree shutter of film)

    def __init__(self, width=1280, height=720, fps=None, quality=None, bg="#000000", seed=0, title=None, blur=None):
        self.w, self.h, self.bg, self.seed, self.title = int(width), int(height), bg, seed, title
        self.fps = None if fps is None else int(fps)
        self.blur = blur
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

    def sfx(self, what, at=0.0, vol=1.0, pan=0.0, **kw):
        """Add a sound effect by name: v.sfx('punch', 1.5), v.sfx('whoosh', 0.9, vol=0.6, dur=0.4). `what` can also be a buffer.
        Names: see sfx.names(); each call sounds a little different. Returns the buffer."""
        buf = sfx.get(what, **kw) if isinstance(what, str) else what
        self.sounds.append((buf, at, vol, pan))
        return buf

    @property
    def duration(self):
        return max([s.end for s in self.scenes] or [0.0])

    # ---- one frame ----
    def _geometry(self, q):
        spec = QUALITY[q]
        pw = max(2, int(round(self.w * spec["scale"] / 2.0)) * 2)
        ph = max(2, int(round(self.h * spec["scale"] / 2.0)) * 2)
        return pw, ph, spec["ss"], (spec["fps"] if self.fps is None else max(1, min(self.fps, spec["fps"])))

    def _blur_samples(self, q, fps):
        env = os.environ.get("LUMO_VIDEO_BLUR")
        if env:
            try:
                return max(1, min(8, int(env)))
            except ValueError:
                pass
        if self.blur is not None:
            n = 3 if self.blur is True else 1 if self.blur is False else int(self.blur)
        else:
            n = QUALITY[q].get("blur", 1)
            if q != "draft" and fps <= 36:
                n = max(n, 3)                                        # 30 fps (or less) looks choppy on fast moves without blur
        return max(1, min(8, n))

    def _sample_times(self, T, fps, n):
        """The instants averaged into one frame: spread over the shutter time around T, kept inside the scene (a cut stays a hard cut)."""
        if n <= 1:
            return [T]
        span = self.SHUTTER / float(fps)
        ts = [T + ((k + 0.5) / n - 0.5) * span for k in range(n)]
        active = [s for s in self.scenes if s.start <= T < s.end]
        if len(active) == 1:
            lo, hi = active[0].start, active[0].end - 1e-6
        else:
            lo, hi = 0.0, self.duration - 1e-6
        return [min(hi, max(lo, x)) for x in ts]

    def render_frame(self, T, quality=None, fps=None, samples=None):
        """The frame at time T exactly as render() writes it (motion blur included), as a PIL image."""
        q = quality or self.quality
        geo = self._geometry(q)
        fps = fps or geo[3]
        n = samples if samples is not None else self._blur_samples(q, fps)
        imgs = [self.frame_at(x, q, fps) for x in self._sample_times(T, fps, n)]
        acc = imgs[0]
        for k in range(1, len(imgs)):
            acc = Image.blend(acc, imgs[k], 1.0 / (k + 1))
        return acc

    def _raw_frame(self, T, q, fps, samples):
        img = self.render_frame(T, q, fps, samples)
        small = img.convert("L").resize((48, 27), Image.BOX)
        return img.tobytes(), small.tobytes()

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
    def _workers(self, total, workers, q, fps):
        n = workers if workers is not None else os.environ.get("LUMO_VIDEO_WORKERS")
        try:
            n = int(n) if n not in (None, "") else None
        except ValueError:
            n = None
        if n is None:
            try:
                cpus = len(os.sched_getaffinity(0))
            except (AttributeError, OSError):
                cpus = os.cpu_count() or 1
            n = min(cpus, 4)                                         # phones get hot: four cores are plenty
        if n < 2 or total < 48 or "fork" not in multiprocessing.get_all_start_methods():
            return 1
        return min(n, 8)

    def _stable(self, q, fps):
        """True when drawing the same time twice gives the same picture (no hidden state), which parallel rendering needs."""
        try:
            T = self.duration * 0.37
            a = self.render_frame(T, q, fps, 1).tobytes()
            self.render_frame(self.duration * 0.71, q, fps, 1)
            return a == self.render_frame(T, q, fps, 1).tobytes()
        except Exception:
            return False

    def _iter_parallel(self, q, fps, total, samples, workers):
        _PAR["job"] = (self, q, fps, samples)
        ctx = multiprocessing.get_context("fork")
        ex = concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=ctx)
        pending, nxt = collections.deque(), 0
        try:
            while nxt < total and len(pending) < workers * 3:
                pending.append(ex.submit(_par_frame, nxt))
                nxt += 1
            while pending:
                i, raw, small, tb = pending.popleft().result()
                if tb:
                    raise _FrameError(i, tb)
                if nxt < total:
                    pending.append(ex.submit(_par_frame, nxt))
                    nxt += 1
                yield raw, small
        finally:
            try:
                for p in list(getattr(ex, "_processes", {}).values()):
                    p.terminate()
            except Exception:
                pass
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except TypeError:                                         # Python 3.8
                ex.shutdown(wait=False)
            _PAR.clear()

    def _iter_frames(self, q, fps, total, samples, workers):
        """Yield (rgb bytes, small gray bytes) for every frame, in order, using several processes when that is safe."""
        produced = 0
        if workers > 1 and self._stable(q, fps):
            try:
                for item in self._iter_parallel(q, fps, total, samples, workers):
                    produced += 1
                    yield item
                return
            except _FrameError as e:                                  # a bug in the script: show it with a normal traceback
                self._raw_frame(e.index / float(fps), q, fps, samples)
                raise RuntimeError("the animation failed on frame %d:\n%s" % (e.index, e.tb))
            except Exception as e:
                print("  ! parallel rendering stopped (%s); continuing on one core" % (str(e) or type(e).__name__), flush=True)
        for i in range(produced, total):
            yield self._raw_frame(i / float(fps), q, fps, samples)

    def render(self, path=None, quality=None, progress=True, workers=None):
        """Render the whole video to an MP4 (H.264 yuv420p + AAC, plays in every player). Returns a report dict and prints it as one
        'LUMO_VIDEO_REPORT {...}' line. The path: $LUMO_VIDEO_OUT if set, else the path you pass, else videos/<script name>.mp4.
        Several CPU cores draw frames at the same time (workers=1 or LUMO_VIDEO_WORKERS=1 turns that off)."""
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
        ff = ffmpeg_path()
        gif = ff is None
        if gif:
            fps = min(fps, 20)                                       # GIF players ignore delays under 20 ms
        total = max(1, int(math.ceil(self.duration * fps - 1e-9)))
        samples = self._blur_samples(q, fps)
        nworkers = self._workers(total, workers, q, fps)
        t0 = time.time()
        if not ff and os.environ.get("LUMO_VIDEO_REQUIRE_FFMPEG"):
            raise RuntimeError("ffmpeg is not installed: pkg install ffmpeg  (Termux)  |  sudo apt install ffmpeg")
        tmp = tempfile.mkdtemp(prefix="lumovideo_")
        proc = errf = None
        try:
            if gif:
                out = os.path.splitext(out)[0] + ".gif"
                print("  ! ffmpeg is not installed, writing a GIF instead (no sound). For a real MP4: pkg install ffmpeg", flush=True)
            audio = None if gif else self._audio_file(tmp, self.duration)
            if not gif:
                enc = ["-c:v", "libx264", "-preset", QUALITY[q]["preset"], "-crf", str(QUALITY[q]["crf"])] if _have_libx264() else ["-c:v", "mpeg4", "-q:v", "3"]
                cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (pw, ph), "-r", str(fps), "-i", "-"]
                if audio:
                    cmd += ["-i", audio]
                cmd += enc + ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", "%.3f" % self.duration]
                if audio:
                    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
                cmd.append(out)
                errf = open(os.path.join(tmp, "ffmpeg.log"), "wb")
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errf)
            frames, stats, prev, last_print, done = [], [], None, 0.0, 0
            for raw, small_raw in self._iter_frames(q, fps, total, samples, nworkers):
                small = Image.frombytes("L", (48, 27), small_raw)
                stats.append(frame_stats(small, prev))
                prev = small
                done += 1
                if proc is not None:
                    try:
                        proc.stdin.write(raw)
                    except (BrokenPipeError, OSError):
                        break
                else:
                    frames.append(Image.frombytes("RGB", (pw, ph), raw).convert("P", palette=Image.ADAPTIVE, colors=128))
                if progress and (time.time() - last_print > 0.5 or done == total):
                    last_print = time.time()
                    el = last_print - t0
                    rate = done / max(el, 1e-6)
                    sys.stdout.write("\r  rendering %3d%% · frame %d/%d · %.1f fps · ~%ds left   " % (100 * done // total, done, total, rate, (total - done) / max(rate, 1e-6)))
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
            try:
                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait()
                if errf is not None and not errf.closed:
                    errf.close()
            except Exception:
                pass
            shutil.rmtree(tmp, ignore_errors=True)
        rep = {"file": out, "format": "gif" if gif else "mp4", "width": pw, "height": ph, "fps": fps, "frames": total, "duration": round(total / float(fps), 2),
               "quality": q, "audio": bool(audio), "size_kb": int(os.path.getsize(out) / 1024), "render_s": round(time.time() - t0, 1),
               "blur": samples, "workers": nworkers, "qa": _qa(stats, self.duration, bool(audio))}
        print("LUMO_VIDEO_REPORT " + json.dumps(rep), flush=True)
        if not os.environ.get("LUMO_VIDEO_TOOL"):                       # run by hand: say how to watch it
            print(play_hints(out), flush=True)
        return rep


_PAR = {}


class _FrameError(Exception):
    def __init__(self, index, tb):
        Exception.__init__(self, "frame %d failed" % index)
        self.index, self.tb = index, tb


def _par_frame(i):
    """Runs inside a worker process (forked, so it already holds the whole video): draw frame i."""
    v, q, fps, samples = _PAR["job"]
    try:
        raw, small = v._raw_frame(i / float(fps), q, fps, samples)
        return i, raw, small, None
    except BaseException:
        return i, None, None, traceback.format_exc()


# ---- how to watch the result ----
def _is_termux():
    return bool(os.environ.get("TERMUX_VERSION")) or "com.termux" in os.environ.get("PREFIX", "") or os.path.isdir("/data/data/com.termux/files")


def _movies_dir():
    """The phone's Movies folder when Termux may write to it (after termux-setup-storage), else None."""
    home = os.path.expanduser("~")
    for p in (os.path.join(home, "storage", "movies"), "/storage/emulated/0/Movies", "/sdcard/Movies"):
        if os.path.isdir(p) and os.access(p, os.W_OK):
            return p
    return None


def play_hints(path):
    """Plain text that tells a person how to watch the video on this device (Termux, Linux, macOS, Windows)."""
    p = os.path.abspath(path)
    name = os.path.basename(p)
    q = shlex.quote(p)
    lines = ["", "  ▶ How to play: %s" % p]
    if _is_termux():
        lines.append("    1. Open it now:        termux-open %s" % q)
        if _movies_dir():
            lines.append("    2. Put it in Gallery:  cp %s %s/    (then open Gallery, Files, VLC or MX Player)" % (q, shlex.quote(_movies_dir())))
        else:
            lines.append("    2. Put it in Gallery:  termux-setup-storage   (once, tap Allow), then: cp %s ~/storage/movies/" % q)
        lines.append("    3. Inside Lumo Code:   /play %s    (opens it, or copies it to your Movies folder with /play --gallery)" % name)
    elif sys.platform == "darwin":
        lines.append("    Open it:  open %s" % q)
    elif sys.platform.startswith("win"):
        lines.append("    Open it:  start \"\" %s" % q)
    else:
        lines.append("    Open it:  xdg-open %s     (or: mpv %s / vlc %s)" % (q, q, q))
    lines.append("    Any player works (MP4 with H.264 video and AAC sound): VLC, MX Player, Google Photos, the phone Gallery.")
    return "\n".join(lines)


def open_video(path, gallery=False):
    """Try to start the device player; with gallery=True also copy the file into the phone's Movies folder.
    Returns {'ok': bool, 'via': str, 'copied': path or None, 'message': str}."""
    p = os.path.abspath(path)
    res = {"ok": False, "via": None, "copied": None, "message": ""}
    if not os.path.isfile(p):
        res["message"] = "no such file: %s" % p
        return res
    target = p
    if gallery:
        md = _movies_dir()
        if md:
            try:
                dest_dir = os.path.join(md, "Lumo")
                os.makedirs(dest_dir, exist_ok=True)
                target = os.path.join(dest_dir, os.path.basename(p))
                shutil.copyfile(p, target)
                res["copied"] = target
                scan = shutil.which("termux-media-scan")
                if scan:
                    subprocess.run([scan, target], capture_output=True, timeout=20)
            except OSError as e:
                res["message"] = "could not copy to the Movies folder (%s). " % e
                target = p
        else:
            res["message"] = "the Movies folder is not reachable: run termux-setup-storage once and allow access, then try again. "
    opener = None
    if sys.platform == "darwin":
        opener = shutil.which("open")
    elif sys.platform.startswith("win"):
        try:
            os.startfile(target)                                   # noqa: the Windows way to open a file
            res.update(ok=True, via="startfile")
            return res
        except OSError:
            opener = None
    else:
        opener = shutil.which("termux-open") or shutil.which("xdg-open")
    if opener:
        try:
            r = subprocess.run([opener, target], capture_output=True, timeout=15)
            res.update(ok=(r.returncode == 0), via=os.path.basename(opener))
            if r.returncode != 0:
                res["message"] += "the player launcher returned an error. "
        except (OSError, subprocess.SubprocessError) as e:
            res["message"] += "could not start the player (%s). " % e
    else:
        res["message"] += "no player launcher found (Termux: pkg install termux-tools). "
    if not res["ok"]:
        res["message"] += "Open the file from your Gallery or file manager: %s" % target
    return res


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
POSES.update({
    "hook_wind": dict(lean=-6, head=-4, lua=-62, lfa=-20, rua=44, rfa=138, lth=-40, lsh=14, rth=42, rsh=-10, hx=-8),
    "hook": dict(lean=24, head=6, lua=98, lfa=128, rua=46, rfa=136, lth=-48, lsh=24, rth=44, rsh=-14, hx=14),
    "elbow_wind": dict(lean=2, rua=40, rfa=140, lua=30, lfa=120, lth=-34, lsh=12, rth=38, rsh=-8, hx=-4),
    "elbow": dict(lean=22, rua=96, rfa=214, lua=40, lfa=130, lth=-40, lsh=18, rth=44, rsh=-12, hx=16),
    "knee_wind": dict(lean=14, lua=52, lfa=150, rua=64, rfa=152, lth=-30, lsh=26, rth=34, rsh=-30, hx=-6),
    "knee": dict(lean=20, lua=60, lfa=150, rua=70, rfa=150, lth=-8, lsh=0, rth=104, rsh=8, hx=12),
    "axe_wind": dict(lean=-22, lua=60, lfa=110, rua=110, rfa=140, lth=-4, lsh=0, rth=146, rsh=160, hx=-4),
    "axe": dict(lean=8, lua=40, lfa=100, rua=90, rfa=120, lth=-14, lsh=4, rth=100, rsh=98, hx=8),
    "super_wind": dict(lean=26, lua=-20, lfa=40, rua=30, rfa=110, lth=-62, lsh=70, rth=66, rsh=-60, hx=-8),
    "super": dict(lean=64, head=-10, lua=-30, lfa=-10, rua=96, rfa=98, lth=-70, lsh=-40, rth=-48, rsh=-26, lift=52),
    "recoil": dict(lean=-34, head=-24, lua=108, lfa=62, rua=122, rfa=74, lth=-22, lsh=8, rth=54, rsh=18, hx=-14, lift=6),
    "tuck": dict(lean=36, head=10, lua=40, lfa=150, rua=50, rfa=150, lth=-100, lsh=-30, rth=96, rsh=-90, lift=96, roll=-170),
    "flip_land": dict(lean=22, lua=44, lfa=140, rua=60, rfa=150, lth=-58, lsh=58, rth=64, rsh=-46, hx=-6),
})
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
    Move("hook", 0.58, [(0, "guard"), (0.12, "hook_wind"), (0.22, "hook", "out_quad"), (0.32, "hook"), (0.58, "guard")], hit=0.22, reach=78, dmg=10, kind="head", limb="hand_l", snd="punch", lunge=20, knock=36),
    Move("elbow", 0.46, [(0, "guard"), (0.07, "elbow_wind"), (0.15, "elbow", "out_quad"), (0.26, "elbow"), (0.46, "guard")], hit=0.15, reach=54, dmg=8, kind="head", limb="elbow_r", snd="hit", lunge=18, knock=22),
    Move("knee", 0.56, [(0, "guard"), (0.1, "knee_wind"), (0.2, "knee", "out_quad"), (0.32, "knee"), (0.56, "guard")], hit=0.2, reach=62, dmg=11, kind="body", limb="knee_r", snd="hit", lunge=24, knock=34),
    Move("axe_kick", 0.84, [(0, "guard"), (0.22, "axe_wind"), (0.34, "axe", "in_quad"), (0.46, "axe"), (0.84, "guard")], hit=0.34, reach=100, dmg=13, kind="head", limb="foot_r", snd="kick", lunge=10, knock=40),
    Move("superman_punch", 0.9, [(0, "guard"), (0.16, "super_wind"), (0.3, "super", "out_quad"), (0.52, "super"), (0.72, "jump", "in_out_quad"), (0.9, "guard")], hit=0.32, reach=118, dmg=15, kind="head", limb="hand_r", snd="punch", travel=96, knock=60, launch=True),
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
    Move("knockback", 0.66, [(0, "guard"), (0.05, "recoil", "out_quad"), (0.3, "recoil"), (0.66, "guard", "in_out_quad")]),
    Move("backflip", 0.78, [(0, "guard"), (0.1, "crouch"), (0.3, {**POSES["tuck"], "roll": -190}, "out_quad"), (0.52, {**POSES["tuck"], "roll": -330, "lift": 70}, "in_out_quad"),
                            (0.64, {**POSES["flip_land"], "roll": -360}, "in_quad"), (0.78, "guard", "out_quad")], travel=0),
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

    def draw(self, c, x, ground, facing, pose, t=0.0, trail=None, alpha=1.0, flash=0.0):
        """Draw the figure standing at x on the ground line. trail: list of earlier poses (resolved) drawn as pale afterimages. Returns the joints."""
        q = pose if isinstance(pose, dict) and "y" in pose else resolve_pose(pose)
        s = self.scale
        col, dark = rgb(self.color), shade(self.color, -0.38)
        edge = shade(self.color, -0.85)
        if flash > 0:                                                  # the body flashes white for a moment when it is hit
            col, dark, edge = mix(col, "#ffffff", flash), mix(dark, "#ffffff", flash * 0.8), mix(edge, "#ffffff", flash * 0.5)
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
        self.motes = [(r.uniform(0, width + 400), r.uniform(self.g * 0.15, self.g * 0.95), r.uniform(0.4, 1.4), r.uniform(0, 6.28), r.uniform(1.6, 4.2)) for _ in range(28)]

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
        self._ambient(c, t)

    def _ambient(self, c, t):
        """Slow floating specks (dust in the light, fireflies, embers) and camera flashes in the arena: the background is never quite still."""
        k = self.kind
        if k == "plain":
            return
        col = {"dojo": "#ffe2b0", "city_night": "#bcd0ff", "sunset": "#ffd9b0", "arena": "#ffffff", "forest": "#e9ff9a"}[k]
        span, top, depth = self.W + 400.0, self.g * 0.15, self.g * 0.8
        with c.parallax(0.85, 0.85):
            for (x0, y0, sp, ph, r) in self.motes:
                x = (x0 + t * 14.0 * sp) % span - 200.0 + 14.0 * math.sin(t * 0.6 + ph)
                y = top + ((y0 - top) + 10.0 * math.sin(t * 0.8 * sp + ph) - t * (5.0 if k == "forest" else 2.0) * sp) % depth
                a = 0.2 + 0.16 * math.sin(t * 1.4 + ph * 2.0)
                c.circle(x, y, r * (1.5 if k == "forest" else 1.0), fill=col, alpha=max(0.05, a))
        if k == "arena":
            for j in range(4):
                ph = (t * 0.55 + j * 0.31) % 1.0
                if ph < 0.05:
                    n = int(t * 0.55 + j * 0.31)
                    fx = (n * 397 + j * 211) % int(self.W)
                    with c.parallax(0.4, 0.3):
                        c.glow(fx, self.g - 150 - (n * 53 % 90), 60, "#ffffff", 0.9 * (1 - ph / 0.05))

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
    Moves: jab cross hook elbow uppercut knee front_kick round_kick axe_kick sweep flying_kick superman_punch. Other actions: block dodge duck taunt bow jump step victory.
    Every pose change is blended (no snapping between moves), the camera follows and punches in on hard hits, and the hits sound different each time."""

    def __init__(self, a, b, stage="dojo", width=1280, height=720, ground=None, a_x=None, b_x=None, title=None, music=None, hud=True, seed=3, trails=True,
                 voices=False, surface=None, sound_files=None):
        self.voices, self.surface = voices, surface        # voices=True adds synthesised grunts and shouts; surface = wood|concrete|dirt|grass|gravel|metal|sand (footsteps)
        self.sound_files = {k: (list(v) if isinstance(v, (list, tuple)) else [v]) for k, v in (sound_files or {}).items()}
        self._packs, self._tracks, self._flashes = {}, None, [[], []]
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

    def dodge(self, who, at, back=34.0, style=None):
        """Avoid a blow. style None = lean back, 'flip' = a backflip (a big, flashy dodge: it needs about 0.8 s)."""
        i = self._i(who)
        if style == "flip":
            self._act(i, "backflip", at, 1)
            self._disp.append(dict(i=i, t0=at + 0.08, dur=0.5, rel=True, by=-max(back, 40.0) * 2.4, ease="out_quad"))
            self._sounds.append((at + 0.12, sfx.whoosh(0.35, 0.5, variant=int(at * 10), rise=True), 0.6, 0.0))
            self._sounds.append((at + 0.66, sfx.land(0.7, variant=int(at * 10)), 0.5, 0.0))
            return
        self._act(i, "dodge", at, 1)
        self._disp.append(dict(i=i, t0=at + 0.04, dur=0.22, by=-back, away=True, ease="out_quad"))
        self._disp.append(dict(i=i, t0=at + 0.34, dur=0.2, by=back * 0.8, away=True, ease="in_out_sine"))
        self._sounds.append((at + 0.03, sfx.cloth(0.2, 0.3, variant=int(at * 10)), 0.6, 0.0))

    def duck(self, who, at):
        self._act(self._i(who), "duck", at, 1)

    def taunt(self, who, at):
        self._act(self._i(who), "taunt", at, 1)

    def bow(self, who, at):
        self._act(self._i(who), "bow", at, 1)

    def jump(self, who, at):
        self._act(self._i(who), "jump", at, 1)
        self._sounds.append((at + 0.12, sfx.jump(0.4, variant=int(at * 10)), 0.6, 0.0))
        self._sounds.append((at + 0.62, sfx.land(0.6, variant=int(at * 10)), 0.5, 0.0))

    def step(self, who, at, by=60.0, dur=0.3):
        """A short step: by > 0 toward the opponent, by < 0 away from them (footwork, retreating, pressing forward)."""
        i = self._i(who)
        self._disp.append(dict(i=i, t0=at, dur=dur, rel=True, by=float(by), ease="in_out_sine"))
        self._touch(at + dur)

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

    def use_sounds(self, **files):
        """Real recordings instead of the synthesised hits: f.use_sounds(punch=["sounds/p1.wav", "sounds/p2.wav"], kick="sounds/k.wav", whoosh=[...]).
        Keys: punch hit kick block whoosh step ko thud. Each value is a file path, a buffer, or a list of them (used in turn)."""
        for k, v in files.items():
            self.sound_files[k] = list(v) if isinstance(v, (list, tuple)) else [v]
        self._packs = {}
        self._compiled = False
        return self

    def use_internet_sounds(self, max_seconds=1.6):
        """Look for free real sound effects on the internet (CC0 / CC-BY, cached in the sounds folder) for punches, hits, kicks, blocks, whooshes and
        footsteps. Without a connection the synthesised effects stay. Credits are written to sounds/CREDITS.txt."""
        for name, q in (("punch", "punch impact"), ("hit", "body hit"), ("kick", "kick impact"), ("block", "block clang"), ("whoosh", "whoosh swing"), ("step", "footstep")):
            self.sound_files[name] = [sfx.net(q, n=3, pick=j, max_seconds=max_seconds) for j in range(3)]
        self._packs = {}
        self._compiled = False
        return self

    def _pack(self, name):
        if name not in self.sound_files:
            return None
        if name not in self._packs:
            self._packs[name] = [load_sound(x) if isinstance(x, str) else x for x in self.sound_files[name]]
        return self._packs[name]

    # ---- the director ----
    def auto(self, duration=14.0, winner="a", seed=1, intro=True, finisher=None, pace=1.0):
        """Write a complete fight: walk-in, exchanges (combos, flurries, trades of blows, blocks, dodges, backflips and counters), a finishing blow,
        K.O. in slow motion, a winner banner. The winner lands more and bigger hits; the loser's health reaches zero exactly on the finishing blow.
        pace: 1.0 normal, 1.5 frantic, 0.7 slow and tense. Another seed gives another fight."""
        rnd = random.Random(seed)
        w = self._i(winner)
        l = 1 - w
        wn = self.f[w].name
        self.winner = w
        pace = clamp(float(pace), 0.5, 2.0)
        if intro:
            self.text(0.3, "READY?", 0.9, 110, "#ffffff", "pop")
            self.text(1.5, "FIGHT!", 0.9, 170, "#ffd166", "slam")
            self.sound(1.5, sfx.bell(660, 1.0, 0.4), 0.8)
            self.sound(1.5, sfx.cymbal(1.3, 0.3, variant=1), 0.5)
            self.gap(0.9, 90.0, 1.5)
            t = 2.4
        else:
            self.gap(0.0, 90.0, 0.3)
            t = 0.5
        ko_t = max(t + 2.2, duration - 3.4)
        light = [["jab", "cross"], ["jab", "jab", "cross"], ["jab", "cross", "hook"], ["hook", "cross"], ["jab", "elbow"], ["cross", "knee"], ["jab", "hook", "cross"]]
        heavy = [["round_kick"], ["front_kick", "cross"], ["jab", "cross", "uppercut"], ["sweep", "uppercut"], ["axe_kick"], ["jab", "front_kick", "round_kick"],
                 ["hook", "uppercut"], ["knee", "elbow", "hook"], ["superman_punch"], ["cross", "round_kick"]]
        won, lost = [], []
        stun = [0.0, 0.0]                         # until when each fighter is busy reacting to a hit
        momentum = 0.64
        guard, recent = 0, []

        def note(rec, victim):
            stun[victim] = max(stun[victim], rec["t0"] + MOVES[rec["move"]].hit + 0.55)
        while t < ko_t - 0.9 and guard < 90:
            guard += 1
            atk = w if rnd.random() < momentum else l
            dfd = 1 - atk
            if atk == w:
                kinds, wts = ["land", "block", "dodge", "trade", "flurry"], [5.0, 2.2, 1.7, 1.2, 1.8]
            else:
                kinds, wts = ["land", "block", "dodge", "trade", "flurry"], [1.3, 3.0, 3.0, 0.8, 0.4]
            if len(won) + len(lost) == 0:
                kinds, wts = ["land", "flurry"], [3.0, 1.0]                  # open with a clean exchange
            kind = rnd.choices(kinds, wts)[0]
            if len(recent) >= 2 and recent[-1] == recent[-2] == kind:
                kind = "land" if kind != "land" else "block"
            recent.append(kind)
            t = max(t, stun[atk] + 0.05, stun[dfd] * (0.6 if kind == "trade" else 0.0))
            chain = list(rnd.choice(light if rnd.random() < 0.55 else heavy))
            if atk == l:
                chain = chain[:rnd.choice((1, 2))]
            if kind == "flurry":
                chain = [rnd.choice(["jab", "cross", "hook", "jab", "elbow", "knee"]) for _ in range(rnd.randint(4, 6 if atk == w else 4))]
            sp = 0.62 if kind == "flurry" else 0.78

            def est(ch):
                return sum(MOVES[x].dur * sp for x in ch[:-1]) + MOVES[ch[-1]].dur + (0.6 if ch[0] == "superman_punch" else 0.0)
            avail = ko_t - 0.7 - t
            while len(chain) > 1 and est(chain) > avail:
                chain.pop()
            if kind in ("dodge", "trade") and est(chain) + 1.1 > avail:
                kind = "land"
            if est(chain) > avail:
                chain = [x for x in chain if x != "superman_punch"][:1] or ["jab"]
                if est(chain) > avail:
                    break
            if chain[0] == "superman_punch":
                self.gap(t, 178.0, 0.45)
                t += 0.6
            tt = t
            if kind == "dodge":
                m0 = MOVES[chain[0]]
                self.attack(atk, chain[0], tt, hit=False)
                flip = rnd.random() < 0.3 and chain[0] != "superman_punch"
                self.dodge(dfd, tt + m0.hit - (0.5 if flip else 0.3), style="flip" if flip else None)
                counter = rnd.choice(["jab", "cross", "front_kick", "hook", "knee"])
                c_t = tt + m0.hit + (0.4 if flip else 0.22)
                rec2 = self.attack(dfd, counter, c_t, hit=True)
                (won if dfd == w else lost).append(rec2)
                note(rec2, atk)
                tt = c_t + MOVES[counter].dur
            elif kind == "block":
                m0 = MOVES[chain[0]]
                rec = self.attack(atk, chain[0], tt, hit=True)
                rec["blocked_plan"] = True
                self.block(dfd, tt + m0.hit - 0.3, 0.7)
                tt += m0.dur * sp
                for mv in chain[1:]:
                    rec = self.attack(atk, mv, tt, hit=True)
                    (won if atk == w else lost).append(rec)
                    note(rec, dfd)
                    tt += MOVES[mv].dur * sp
                tt = max(tt, t + m0.dur)
            elif kind == "trade":
                ma, mb = chain[0], rnd.choice(["jab", "cross", "hook", "front_kick"])
                da, db = MOVES[ma].hit, MOVES[mb].hit
                ta = t + max(0.0, db - da)
                tb = ta + da - db + rnd.uniform(-0.015, 0.015)
                ra, rb = self.attack(atk, ma, ta, hit=True), self.attack(dfd, mb, tb, hit=True)
                (won if atk == w else lost).append(ra)
                (won if dfd == w else lost).append(rb)
                note(ra, dfd)
                note(rb, atk)
                tt = max(ta + MOVES[ma].dur, tb + MOVES[mb].dur)
            else:
                for k, mv in enumerate(chain):
                    rec = self.attack(atk, mv, tt, hit=True)
                    (won if atk == w else lost).append(rec)
                    note(rec, dfd)
                    tt += MOVES[mv].dur * (sp if k < len(chain) - 1 else 1.0)
            ko_t = max(ko_t, tt + 0.8)
            t = tt + rnd.uniform(0.1, 0.34) / pace
            self.gap(tt - 0.05, rnd.uniform(82.0, 100.0), 0.34)
            if rnd.random() < 0.16 and t < ko_t - 2.6:
                mover = rnd.choice((0, 1))
                if rnd.random() < 0.5:
                    self.taunt(mover, t)
                else:
                    self.jump(mover, t)
                t += 0.9
        fm = finisher or rnd.choice(["round_kick", "uppercut", "flying_kick", "cross", "axe_kick", "superman_punch"])
        fk = MOVES[fm]
        t = max(t, stun[w] + 0.05)
        if fm in ("flying_kick", "superman_punch"):
            self.gap(ko_t - 1.2, 150.0 if fm == "flying_kick" else 178.0, 0.6)
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
                elif st and st["move"] in ("dodge", "backflip"):
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
                    if rec["dmg"] >= 10.5 and m.kind != "legs":
                        kind = "knockback"                                  # a hard hit throws the opponent back
                    self._acts[tgt].append(dict(t0=ts, t1=ts + MOVES[kind].dur, move=kind, prio=3, shift=0.0))
                self._disp.append(dict(i=tgt, t0=ts, dur=0.3, by=m.knock * (1.7 if rec["finisher"] else 1.25 if rec["dmg"] >= 10.5 else 1.0), away=True, ease="out_quad"))
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
            elif d.get("rel"):                                           # relative to the opponent: by > 0 toward, by < 0 away
                target = cur[i] + d["by"] * toward
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
        self._build_tracks()
        # 4. effects, health, sounds
        self._fx, self._shakes, self._hp, self._popups = [], [], [[], []], []
        self._flashes = [[], []]
        self._packs = {}
        counts, cache = {}, {}
        surface = self.surface or {"dojo": "wood", "arena": "wood", "city_night": "concrete", "sunset": "dirt", "forest": "grass", "plain": "concrete"}.get(getattr(self.stage, "kind", "plain"), "wood")
        deeper = [1.0, 0.86]                                          # the second fighter's voice is a little deeper

        def snd(name, power=1.0, who=None):
            """The next take of an effect: five different takes per effect in turn (or the next recorded sound when use_sounds was called)."""
            k = counts.get(name, 0)
            counts[name] = k + 1
            pk = self._pack(name)
            if pk:
                return pk[k % len(pk)]
            slot = k % 5
            key = (name, round(power, 1), slot, who)
            if key not in cache:
                if name in ("punch", "hit", "kick", "smash", "slap", "thud", "crack", "block", "fall", "land"):
                    buf = getattr(sfx, name)(power, variant=slot)
                elif name == "whoosh":
                    buf = sfx.whoosh(0.18 + 0.04 * (slot % 3), 0.5, variant=slot)
                elif name == "step":
                    buf = sfx.step(0.5, surface, variant=slot)
                elif name in ("ko", "slide", "cloth", "kiai", "grunt", "pain", "gasp"):
                    buf = getattr(sfx, name)(variant=slot)
                    if who is not None and name in ("kiai", "grunt", "pain", "gasp"):
                        buf = _pitch(buf, deeper[who])
                else:
                    buf = getattr(sfx, name)()
                cache[key] = buf
            return cache[key]
        for rec in events:
            m = MOVES[rec["move"]]
            ts, att, tgt = rec["ts"], rec["i"], 1 - rec["i"]
            if rec["result"] == "none":
                continue
            rr = random.Random(self.seed * 7919 + int(ts * 100) + att)
            pan = -0.25 if att == 0 else 0.25
            self._sounds.append((rec["t0"] + max(0.0, m.hit - 0.1), snd("whoosh"), 0.7, pan))
            if self.voices and m.dmg >= 8 and rr.random() < 0.6:
                self._sounds.append((rec["t0"] + max(0.0, m.hit - 0.14), snd("kiai" if m.dmg >= 11 else "grunt", 1.0, att), 0.5, pan))
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
                if heavy:
                    self._sounds.append((ts, snd("thud", 0.8), 0.45, 0.0))
                elif rr.random() < 0.4:
                    self._sounds.append((ts + 0.005, snd("slap", 0.7), 0.3, 0.0))
                if self.voices and rr.random() < 0.65:
                    self._sounds.append((ts + 0.03, snd("pain" if heavy else "grunt", 1.0, tgt), 0.5, -pan))
                self._flashes[tgt].append(ts)
                if heavy and not rec["finisher"]:
                    self._zooms.append((ts - 0.02, 0.5, 0.05 + min(0.06, rec["dmg"] * 0.003)))
                    self._fx.append(dict(kind="dust", s=ts + 0.1, x=self._x_at(tgt, ts + 0.1), y=self.ground, k=0.6))
                hold = 0.05 + min(0.08, rec["dmg"] * 0.004)
                if rec["finisher"]:
                    hold = 0.16
                    self._warps.append(("slow", ts + 0.05, ts + 1.05, 0.28))
                    self._zooms.append((ts, 1.6, 0.3))
                    self._fx.append(dict(kind="ring", s=ts, x=hx, y=hy))
                    self._sounds.append((ts + 0.04, snd("ko"), 0.9, 0.0))
                    self._sounds.append((ts, snd("smash", 1.2), 0.7, 0.0))
                    self._sounds.append((ts + 0.45, snd("fall", 1.0), 0.7, 0.0))
                    self._fx.append(dict(kind="flash", s=ts))
                    self._fx.append(dict(kind="dust", s=ts + 0.4, x=self._x_at(tgt, ts + 0.4), y=self.ground))
                    if getattr(self.stage, "kind", "") == "arena":
                        self._sounds.append((ts + 0.5, sfx.cheer(2.8, 0.45, variant=1), 0.8, 0.0))
                        self._sounds.append((ts + 1.2, sfx.applause(2.2, 0.3, variant=1), 0.7, 0.0))
                self._warps.append(("freeze", ts, hold, 0))
            else:
                self._fx.append(dict(kind="block", s=ts, x=hx, y=hy, dir=self._facing(att, ts)))
                self._sounds.append((ts, snd("block", 0.9), 0.8, 0.0))
                self._sounds.append((ts, snd("thud", 0.4), 0.3, 0.0))
                self._hp[tgt].append((ts, rec["dmg"] * 0.12))
                self._shakes.append((ts, 2.5))
                self._warps.append(("freeze", ts, 0.03, 0))
        # walking sounds
        for i in (0, 1):
            for (t0, t1, a, b, e) in self._xs[i][1]:
                if t0 > -1e8 and abs(b - a) > 20 and (t1 - t0) > 0.25:
                    st = t0 + 0.1
                    while st < t1 - 0.05:
                        self._sounds.append((st, snd("step"), 0.35, -0.25 if i == 0 else 0.25))
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

    _TRACK_HZ = 120.0

    def _pose_raw(self, i, s):
        """(resolved pose, name of what it is doing) straight from the script, before the transitions are blended in."""
        a = self._active(i, s)
        if a:
            return MOVES[a["move"]].pose_at(s - a["t0"]), a["move"]
        if self._ko and self._ko[0] == i and s >= self._ko[1]:
            return resolve_pose("lying"), "lying"
        x1, x0 = self._x_at(i, s + 0.03), self._x_at(i, s - 0.03)
        vel = (x1 - x0) / 0.06
        if abs(vel) > 14:
            sgn = self._facing(i, s)
            fwd = vel * sgn > 0
            run = abs(vel) > 260
            phase = self._x_at(i, s) * sgn / (84.0 if run else 56.0)
            pose = _walk_pose(phase if fwd else -phase, run)
            return pose, "run" if run else "walk"
        b = math.sin(s * 5.0 + i * 1.9)                                 # fighting stance: a light bounce on the feet
        b2 = math.sin(s * 2.5 + i)
        p = dict(POSES["guard"])
        p["lean"] += b2 * 2.0 + 1.0
        p["rua"] += b * 3.0
        p["rfa"] -= b * 3.0
        p["lua"] -= b * 2.5
        p["head"] = b2 * 1.5
        p["rth"] += b * 2.5
        p["lth"] -= b * 2.0
        p["y"] = resolve_pose(p)["y"] + b * 1.6
        return p, "idle"

    def _blend_time(self, kind, what):
        if kind == "act":
            if what in ("hit_head", "hit_body", "stagger", "blocked", "knockback", "launch", "knockdown"):
                return 0.05                                               # reactions stay snappy
            if what in MOVES and MOVES[what].hit:
                return 0.075
            return 0.09
        return 0.15                                                       # walking starts and stops

    def _build_tracks(self):
        """Sample both fighters at 120 Hz and blend every change of action (idle to attack, attack to idle, hit, walk ...) from the pose the body
        really had, so the figure never snaps from one pose to another. This is what makes the movement smooth."""
        hz = self._TRACK_HZ
        n = int((self.t_end + 8.0) * hz) + 2
        self._tracks, self._labels = [[], []], [[], []]
        for i in (0, 1):
            tr, lb = [], []
            seg, seg_t0, anchor, B, prev = None, 0.0, None, 0.1, None
            for k in range(n):
                s = k / hz
                raw, what = self._pose_raw(i, s)
                act = self._active(i, s)
                key = ("act", id(act)) if act else ("loco", what)
                if key != seg:
                    seg, seg_t0 = key, s
                    anchor, B = (prev, self._blend_time(key[0], what)) if prev is not None else (None, 0.0)
                if anchor is not None and s - seg_t0 < B:
                    pose = blend_pose(anchor, raw, (s - seg_t0) / B, "in_out_sine")
                else:
                    pose, anchor = raw, None
                tr.append(pose)
                lb.append(what)
                prev = pose
            self._tracks[i], self._labels[i] = tr, lb

    def _pose(self, i, s):
        """(resolved pose, name of what it is doing) at fight time s, smoothed."""
        tr = self._tracks[i] if self._tracks else None
        if tr is None:
            return self._pose_raw(i, s)
        f = s * self._TRACK_HZ
        k = int(f) if f > 0 else 0
        if f <= 0:
            return tr[0], self._labels[i][0]
        if k >= len(tr) - 1:
            return tr[-1], self._labels[i][-1]
        u = f - k
        a, b = tr[k], tr[k + 1]
        return {key: a[key] + (b[key] - a[key]) * u for key in a}, self._labels[i][k]

    def _swoosh(self, c, i, s):
        """A fading streak behind the hand or foot that is striking."""
        a = self._active(i, s)
        if a is None or a["move"] not in MOVES or not MOVES[a["move"]].hit:
            return
        m = MOVES[a["move"]]
        local = s - a["t0"]
        if not (m.hit - 0.17 <= local <= m.hit + 0.07):
            return
        pts = []
        for j in range(8):
            ss = s - j * 0.012
            p, _ = self._pose(i, ss)
            J = self.f[i].joints(self._x_at(i, ss) + self._off(i, ss), self.ground, self._facing(i, ss), p)
            pts.append(J[m.limb])
        col = mix("#ffffff", self.f[i].color, 0.25)
        fade = clamp(1.0 - abs(local - m.hit) / 0.17)
        for j in range(len(pts) - 1, 0, -1):
            u = 1.0 - j / 8.0
            for q in (0.0, 0.5):
                x = pts[j][0] + (pts[j - 1][0] - pts[j][0]) * q
                y = pts[j][1] + (pts[j - 1][1] - pts[j][1]) * q
                c.circle(x, y, 3.0 + 7.0 * u, fill=col, alpha=0.5 * u * fade)

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
                a = self._active(i, s)
                if a is not None and a["move"] == what:             # the label comes from the smoothed track, the action may just have ended
                    local = s - a["t0"]
                    if abs(local - MOVES[what].hit) < 0.22:
                        trail = [(MOVES[what].pose_at(max(0.0, local - d)), 0.55 + d * 3) for d in (0.05, 0.1)]
            fl = 0.0
            for te in self._flashes[i]:
                e = v - self._warp.vid(te)
                if 0 <= e < 0.16:
                    fl = max(fl, 0.8 * (1 - e / 0.16))
            self.f[i].draw(c, x, self.ground, fc, pose, v, trail=trail, flash=fl)
        if self.trails:
            for i in (0, 1):
                self._swoosh(c, i, s)
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
            kk = fx.get("k", 1.0)
            for j in range(7):
                a = (j - 3) * 0.55
                c.circle(fx["x"] + math.sin(a) * 90 * u * kk + (j % 2) * 8, fx["y"] - 10 - 40 * u * kk * (0.5 + (j % 3) * 0.25), (16 * (1 - u * 0.6) + 4) * kk,
                         fill=mix("#cdbb9d", "#ffffff", 0.2 * (1 - u)), alpha=0.9 * (1 - u * 0.6))
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
