"""Neon Pulse - desktop version (Python + pygame).

Same levels, physics and songs as the browser version: physics.py is the
reference engine, levels come from levels/levels.json, and synth.py renders
the songs.
"""

import json
import math
import os
import random

import numpy as np
import pygame

from . import synth
from .physics import CEIL, CEIL_MODES, SPEEDS, STEP, Level, Player, step

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
LEVELS_PATH = os.path.join(ROOT, "levels", "levels.json")
SAVE_PATH = os.path.join(os.path.expanduser("~"), ".neonpulse_save.json")

W, H = 1280, 720
U = H / 11.0  # pixels per block

COLORS = ["#5cff3a", "#3af0ff", "#ffe23a", "#ff5ad8", "#ff4040", "#ff9a2a", "#a45aff", "#3a7cff",
          "#ffffff", "#9aa4b8", "#2a2a2a", "#00c896", "#ff7ab0", "#c8ff3a", "#7a4a2a", "#ffd6a0"]
ORB_COLORS = {"orb_y": "#ffe23a", "orb_p": "#ff5ad8", "orb_r": "#ff4040", "orb_b": "#3ad0ff",
              "orb_g": "#3aff7c", "orb_k": "#1a1a1a"}
PAD_COLORS = {"pad_y": "#ffe23a", "pad_p": "#ff5ad8", "pad_r": "#ff4040", "pad_b": "#3ad0ff"}
PORTAL_COLORS = {"p_cube": "#3aff6e", "p_rocket": "#ff4fd8", "p_ball": "#ff5a3a", "p_saucer": "#ffa13a",
                 "p_dart": "#3ae8ff", "p_mech": "#f2f2f2", "p_crawler": "#a45aff", "p_gup": "#ffe23a",
                 "p_gdown": "#3a9cff", "p_gflip": "#3aff7c", "p_s0": "#ffa13a", "p_s1": "#3ad0ff",
                 "p_s2": "#3aff6e", "p_s3": "#ff4fd8", "p_s4": "#ff4040"}
SPEED_ARROWS = {"p_s0": -1, "p_s1": 1, "p_s2": 2, "p_s3": 3, "p_s4": 4}
FACE_COLORS = ["#3ac8ff", "#3aff7c", "#ffd23a", "#ff8a3a", "#ff3ad2", "#ff2a2a"]
DESIGNS = ["classic", "visor", "cross", "diamond", "stripes", "ring", "grin", "split", "robot", "star"]


def hexc(h):
    n = int(h[1:], 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def shade(c, f):
    return mix(c, (255, 255, 255), f) if f >= 0 else mix(c, (0, 0, 0), -f)


def ci(c):
    return tuple(max(0, min(255, int(v))) for v in c)


# ---------------------------------------------------------------- player art
def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _star(r1, r2, n=5):
    return [(math.cos(-math.pi / 2 + i * math.pi / n) * (r1 if i % 2 == 0 else r2),
             math.sin(-math.pi / 2 + i * math.pi / n) * (r1 if i % 2 == 0 else r2)) for i in range(n * 2)]


def design_shapes(d):
    """Cube face shapes in unit coordinates (-0.5..0.5, y down): (which colour, kind, data)."""
    if d == "classic":
        return [("s", "poly", _rect(-0.275, -0.275, 0.275, 0.275)), ("p", "poly", _rect(-0.15, -0.15, 0.15, 0.15))]
    if d == "visor":
        return [("s", "poly", _rect(-0.4, -0.175, 0.4, -0.025)), ("w", "poly", _rect(0.125, -0.14, 0.245, -0.06))]
    if d == "cross":
        return [("s", "poly", _rect(-0.09, -0.4, 0.09, 0.4)), ("s", "poly", _rect(-0.4, -0.09, 0.4, 0.09))]
    if d == "diamond":
        return [("s", "poly", [(0, -0.375), (0.375, 0), (0, 0.375), (-0.375, 0)])]
    if d == "stripes":
        return [("s", "poly", _rect(-0.5, i * 0.3 - 0.07, 0.5, i * 0.3 + 0.07)) for i in (-1, 0, 1)]
    if d == "ring":
        return [("s", "circle", (0, 0, 0.31)), ("p", "circle", (0, 0, 0.16))]
    if d == "grin":
        return [("s", "poly", _rect(-0.275, -0.225, -0.075, -0.025)), ("s", "poly", _rect(0.075, -0.225, 0.275, -0.025)),
                ("s", "poly", _rect(-0.275, 0.1, 0.275, 0.24)), ("s", "poly", _rect(-0.275, 0.025, -0.175, 0.165)),
                ("s", "poly", _rect(0.175, 0.025, 0.275, 0.165))]
    if d == "split":
        return [("s", "poly", [(-0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)])]
    if d == "robot":
        return [("s", "poly", _rect(-0.35, -0.25, 0.35, 0.15)), ("p", "poly", _rect(-0.25, -0.175, -0.1, -0.025)),
                ("p", "poly", _rect(0.1, -0.175, 0.25, -0.025)), ("s", "poly", _rect(-0.2, 0.15, 0.2, 0.27))]
    return [("s", "poly", _star(0.375, 0.15))]


def _xf(pts, cx, cy, s, ang, flip=1):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + (x * ca - y * flip * sa) * s, cy + (x * sa + y * flip * ca) * s) for x, y in pts]


def draw_cube(surf, cx, cy, s, ang, icon):
    p, q = hexc(icon["primary"]), hexc(icon["secondary"])
    pal = {"p": p, "s": q, "w": (255, 255, 255)}
    outline = _xf(_rect(-0.5, -0.5, 0.5, 0.5), cx, cy, s, ang)
    pygame.draw.polygon(surf, p, outline)
    for col, kind, data in design_shapes(DESIGNS[icon["design"] % len(DESIGNS)]):
        if kind == "poly":
            pygame.draw.polygon(surf, pal[col], _xf(data, cx, cy, s, ang))
        else:
            (x, y), r = _xf([(data[0], data[1])], cx, cy, s, ang)[0], data[2]
            pygame.draw.circle(surf, pal[col], (x, y), r * s)
    pygame.draw.polygon(surf, (0, 0, 0), outline, max(2, int(s * 0.07)))


def draw_player(surf, mode, cx, cy, s, ang, icon, t, flipped=False):
    p, q = hexc(icon["primary"]), hexc(icon["secondary"])
    f = -1 if flipped and mode in ("mech", "crawler", "saucer", "rocket") else 1
    lw = max(2, int(s * 0.06))
    if mode == "cube":
        draw_cube(surf, cx, cy, s, ang, icon)
    elif mode == "rocket":
        ox, oy = _xf([(-0.08, -0.22)], cx, cy, s, ang, f)[0]
        draw_cube(surf, ox, oy, s * 0.5, ang, icon)
        hull = _xf([(-0.6, -0.05), (0.55, -0.05), (0.7, 0.12), (0.35, 0.35), (-0.45, 0.35), (-0.65, 0.15)], cx, cy, s, ang, f)
        pygame.draw.polygon(surf, p, hull)
        pygame.draw.polygon(surf, (0, 0, 0), hull, lw)
        pygame.draw.polygon(surf, q, _xf(_rect(-0.35, 0.08, 0.25, 0.2), cx, cy, s, ang, f))
    elif mode == "ball":
        r = s * 0.5
        pygame.draw.circle(surf, p, (cx, cy), r)
        for a0 in (0.0, math.pi):
            pts = [(cx, cy)] + [(cx + math.cos(ang + a0 + k * math.pi / 16) * r, cy + math.sin(ang + a0 + k * math.pi / 16) * r)
                                for k in range(9)]
            pygame.draw.polygon(surf, q, pts)
        pygame.draw.circle(surf, p, (cx, cy), r * 0.35)
        pygame.draw.circle(surf, (0, 0, 0), (cx, cy), r, lw)
    elif mode == "saucer":
        dome = pygame.Rect(0, 0, s * 0.64, s * 0.64)
        dome.center = (cx, cy - s * 0.05 * f)
        pygame.draw.circle(surf, (150, 210, 235), dome.center, s * 0.32)
        draw_cube(surf, cx, cy - s * 0.14 * f, s * 0.36, ang, icon)
        disk = pygame.Rect(0, 0, s * 1.24, s * 0.4)
        disk.center = (cx, cy + s * 0.1 * f)
        pygame.draw.ellipse(surf, p, disk)
        pygame.draw.ellipse(surf, (0, 0, 0), disk, lw)
        for i in (-1, 0, 1):
            pygame.draw.circle(surf, q, (cx + i * s * 0.3, cy + s * 0.1 * f), s * 0.06)
    elif mode == "dart":
        body = _xf([(0.5, 0), (-0.45, -0.38), (-0.25, 0), (-0.45, 0.38)], cx, cy, s, ang)
        pygame.draw.polygon(surf, p, body)
        pygame.draw.polygon(surf, (0, 0, 0), body, lw)
        pygame.draw.polygon(surf, q, _xf([(0.25, 0), (-0.2, -0.16), (-0.2, 0.16)], cx, cy, s, ang))
    elif mode == "mech":
        stp = math.sin(t * 18)
        for side in (-1, 1):
            leg = _xf(_rect(-0.08, 0, 0.08, 0.42), cx + side * s * 0.15, cy + s * 0.05 * f, s, side * stp * 0.4, f)
            pygame.draw.polygon(surf, q, leg)
            pygame.draw.polygon(surf, (0, 0, 0), leg, 2)
        draw_cube(surf, cx, cy - s * 0.18 * f, s * 0.62, 0, icon)
    elif mode == "crawler":
        stp = math.sin(t * 22)
        for i in range(4):
            side = -1 if i < 2 else 1
            off = (0.12 if i % 2 else 0.32) * side
            k = (stp if i % 2 else -stp) * 0.12
            pts = [(cx + off * s, cy), (cx + (off * 1.6 + k) * s, cy + 0.2 * s * f), (cx + (off * 1.5 + k) * s, cy + 0.48 * s * f)]
            pygame.draw.lines(surf, q, False, pts, max(2, int(s * 0.09)))
        body = pygame.Rect(0, 0, s * 0.84, s * 0.6)
        body.center = (cx, cy - s * 0.12 * f)
        pygame.draw.ellipse(surf, p, body)
        pygame.draw.ellipse(surf, (0, 0, 0), body, lw)
        for ex in (-0.14, 0.14):
            pygame.draw.rect(surf, q, (cx + ex * s - s * 0.06, cy - s * 0.18 * f - s * 0.06, s * 0.12, s * 0.12))


def draw_face(surf, diff, cx, cy, r):
    if diff == 5:
        for sd in (-1, 1):
            pygame.draw.polygon(surf, (255, 42, 42), [(cx + sd * r * 0.45, cy - r * 0.7), (cx + sd * r * 0.95, cy - r * 1.35),
                                                      (cx + sd * r * 0.85, cy - r * 0.45)])
    pygame.draw.circle(surf, hexc(FACE_COLORS[diff]), (cx, cy), r)
    pygame.draw.circle(surf, (0, 0, 0), (cx, cy), r, max(2, int(r * 0.12)))
    ey = cy - r * 0.2
    for sd in (-1, 1):
        if diff >= 3:
            pygame.draw.polygon(surf, (0, 0, 0), [(cx + sd * r * 0.15, ey - r * 0.05), (cx + sd * r * 0.6, ey - r * 0.3),
                                                  (cx + sd * r * 0.55, ey + r * 0.12)])
        else:
            pygame.draw.circle(surf, (0, 0, 0), (cx + sd * r * 0.35, ey), r * 0.13)
    lw = max(2, int(r * 0.12))
    if diff <= 1:
        pygame.draw.arc(surf, (0, 0, 0), (cx - r * 0.45, cy - r * 0.35, r * 0.9, r * 0.9), math.pi * 1.15, math.pi * 1.85, lw)
    elif diff == 2:
        pygame.draw.line(surf, (0, 0, 0), (cx - r * 0.4, cy + r * 0.4), (cx + r * 0.4, cy + r * 0.4), lw)
    else:
        pygame.draw.arc(surf, (0, 0, 0), (cx - r * 0.45, cy + r * 0.3, r * 0.9, r * 0.9), math.pi * 0.2, math.pi * 0.8, lw)


# ---------------------------------------------------------------- UI helpers
class Button:
    def __init__(self, rect, label, action, color=(58, 216, 106), round_=False, font=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.color = color
        self.round = round_
        self.font = font

    def draw(self, surf, fonts, mouse):
        hover = self.rect.collidepoint(mouse)
        r = self.rect
        if self.color is None:
            self.label(surf, r)
            return
        col = shade(self.color, 0.15) if hover else self.color
        shadow = r.move(0, 6)
        if self.round:
            pygame.draw.circle(surf, (0, 0, 0), shadow.center, r.width // 2)
            pygame.draw.circle(surf, ci(col), r.center, r.width // 2)
            pygame.draw.circle(surf, ci(shade(col, -0.6)), r.center, r.width // 2, 4)
        else:
            pygame.draw.rect(surf, (0, 0, 0), shadow, border_radius=r.height // 2)
            pygame.draw.rect(surf, ci(col), r, border_radius=r.height // 2)
            pygame.draw.rect(surf, ci(shade(col, -0.6)), r, 3, border_radius=r.height // 2)
        if callable(self.label):
            self.label(surf, r)
        else:
            text(surf, fonts[self.font or "btn"], self.label, r.center, center=True, shadow=True)

    def hit(self, pos):
        return self.rect.collidepoint(pos)


def text(surf, font, s, pos, color=(255, 255, 255), center=False, shadow=False, right=False):
    img = font.render(s, True, color)
    r = img.get_rect()
    if center:
        r.center = pos
    elif right:
        r.topright = pos
    else:
        r.topleft = pos
    if shadow:
        sh = font.render(s, True, (0, 0, 0))
        surf.blit(sh, r.move(2, 3))
    surf.blit(img, r)
    return r


def panel(surf, rect, color=(8, 12, 40), alpha=200):
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(s, color + (alpha,), s.get_rect(), border_radius=22)
    pygame.draw.rect(s, (255, 255, 255, 50), s.get_rect(), 3, border_radius=22)
    surf.blit(s, rect.topleft)


def progress_bar(surf, fonts, rect, pct, practice=False):
    pygame.draw.rect(surf, (0, 0, 0), rect, border_radius=rect.height // 2)
    if pct > 0:
        fill = rect.copy()
        fill.width = max(rect.height, int(rect.width * pct / 100))
        pygame.draw.rect(surf, (47, 208, 106) if practice else (58, 140, 255), fill, border_radius=rect.height // 2)
    pygame.draw.rect(surf, (220, 220, 220), rect, 2, border_radius=rect.height // 2)
    text(surf, fonts["small"], f"{pct}%", rect.center, center=True, shadow=True)


# ---------------------------------------------------------------- the game
class Game:
    def __init__(self):
        pygame.mixer.pre_init(synth.RATE, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption("Neon Pulse")
        self.screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.fonts = {
            "logo": pygame.font.Font(None, 150),
            "title": pygame.font.Font(None, 64),
            "big": pygame.font.Font(None, 48),
            "btn": pygame.font.Font(None, 40),
            "med": pygame.font.Font(None, 32),
            "small": pygame.font.Font(None, 24),
            "world": pygame.font.Font(None, int(U * 1.25)),
        }
        for f in self.fonts.values():
            f.set_bold(True)
        with open(LEVELS_PATH) as f:
            self.data = json.load(f)
        self.levels = self.data["levels"]
        self.save = self.load_save()
        self.audio_ok = pygame.mixer.get_init() is not None
        self.sfx = {}
        if self.audio_ok:
            for name in ("death", "coin", "win", "click", "checkpoint"):
                mono = synth.effect(name)
                self.sfx[name] = pygame.mixer.Sound(buffer=np.repeat(mono, 2).tobytes())
        self.current_song = None
        self.song_bpm = 120
        self.song_start = 0
        self.apply_volumes()
        self.state = "main"
        self.selected = 0
        self.menu_t = 0.0
        self.menu_bg = hexc(self.levels[0]["colors"][0][1])
        self.menu_ground = hexc(self.levels[0]["colors"][0][2])
        self.menu_target = (self.menu_bg, self.menu_ground)
        self.g = None
        self.held = set()
        self.pressed = False
        self.toast = None
        self.buttons = []
        self.play_song(self.data["songs"]["menu"], "menu", loop=True)
        self.build_buttons()

    # ---- persistence
    def load_save(self):
        base = {"icon": {"primary": "#5cff3a", "secondary": "#3af0ff", "design": 0},
                "settings": {"music": 0.8, "sfx": 0.8, "percent": True, "auto": False},
                "levels": {}, "jumps": 0, "attempts": 0}
        try:
            with open(SAVE_PATH) as f:
                s = json.load(f)
            base.update({k: v for k, v in s.items() if k in base})
        except (OSError, ValueError):
            pass
        return base

    def persist(self):
        try:
            with open(SAVE_PATH, "w") as f:
                json.dump(self.save, f)
        except OSError:
            pass

    def stats(self, i):
        name = self.levels[i]["name"]
        return self.save["levels"].setdefault(name, {"attempts": 0, "jumps": 0, "best": 0, "practice": 0,
                                                     "done": False, "coins": 0})

    # ---- audio
    def apply_volumes(self):
        if not self.audio_ok:
            return
        pygame.mixer.music.set_volume(self.save["settings"]["music"] * 0.8)
        for s in self.sfx.values():
            s.set_volume(self.save["settings"]["sfx"])

    def play_song(self, song, name, loop=False):
        if not self.audio_ok:
            return
        if self.current_song is song and pygame.mixer.music.get_busy():
            return
        path = synth.song_path(song, name)
        pygame.mixer.music.load(path)
        pygame.mixer.music.play(-1 if loop else 0)
        self.current_song = song
        self.song_bpm = song["bpm"]
        self.song_start = pygame.time.get_ticks()

    def stop_song(self, fade=0):
        if not self.audio_ok:
            return
        if fade:
            pygame.mixer.music.fadeout(fade)
        else:
            pygame.mixer.music.stop()
        self.current_song = None

    def pulse(self):
        if not self.audio_ok or self.current_song is None:
            return 0.0
        ms = pygame.mixer.music.get_pos()
        if ms < 0:
            return 0.0
        b = ms / 1000.0 / (60.0 / self.song_bpm)
        return (1 - (b % 1)) ** 3

    def play_sfx(self, name):
        if name in self.sfx:
            self.sfx[name].play()

    # ---- menus
    def go(self, state):
        self.state = state
        self.build_buttons()
        if state in ("main", "levels", "icons", "settings"):
            self.g = None
            self.play_song(self.data["songs"]["menu"], "menu", loop=True)
        if state == "levels":
            self.select(self.selected)

    def select(self, i):
        self.selected = i % len(self.levels)
        c = self.levels[self.selected]["colors"][0]
        self.menu_target = (hexc(c[1]), hexc(c[2]))

    def build_buttons(self):
        B = []
        st = self.state
        green, blue, red = (58, 216, 106), (58, 160, 255), (255, 74, 90)
        back = Button((20, 20, 60, 60), "<", lambda: self.click(lambda: self.go("main")), green)
        if st == "main":
            B.append(Button((W // 2 - 85, 330, 170, 170), self.icon_play, lambda: self.click(lambda: self.go("levels")), green, True))
            B.append(Button((W // 2 - 240, 370, 92, 92), self.icon_kit, lambda: self.click(lambda: self.go("icons")), blue, True))
            B.append(Button((W // 2 + 148, 370, 92, 92), self.icon_gear, lambda: self.click(lambda: self.go("settings")), blue, True))
        elif st == "levels":
            B.append(back)
            B.append(Button((150, 300, 70, 110), "<", lambda: self.click(lambda: self.select(self.selected - 1)), blue))
            B.append(Button((W - 220, 300, 70, 110), ">", lambda: self.click(lambda: self.select(self.selected + 1)), blue))
            B.append(Button((W // 2 - 180, 470, 170, 60), "Play", lambda: self.start(self.selected, False), green))
            B.append(Button((W // 2 + 10, 470, 170, 60), "Practice", lambda: self.start(self.selected, True), blue))
        elif st == "icons":
            B.append(back)
            ic = self.save["icon"]
            for i in range(len(DESIGNS)):
                B.append(Button((W // 2 - 300 + i * 62, 290, 54, 54), self.design_btn(i), self.setter(ic, "design", i), None))
            for row, key in enumerate(("primary", "secondary")):
                for i, col in enumerate(COLORS):
                    B.append(Button((W // 2 - 300 + i * 38, 400 + row * 100, 32, 32), self.color_btn(col, ic[key] == col),
                                    self.setter(ic, key, col), None))
        elif st == "settings":
            B.append(back)
            s = self.save["settings"]
            for row, key in enumerate(("music", "sfx")):
                y = 250 + row * 80
                B.append(Button((W // 2 + 40, y, 60, 50), "-", self.vol(key, -0.1), blue))
                B.append(Button((W // 2 + 200, y, 60, 50), "+", self.vol(key, 0.1), blue))
            B.append(Button((W // 2 - 220, 420, 440, 50), lambda sf, r: self.toggle_label(sf, r, "Show percentage", s["percent"]),
                            self.toggle(s, "percent"), (40, 60, 120)))
            B.append(Button((W // 2 - 220, 485, 440, 50), lambda sf, r: self.toggle_label(sf, r, "Auto checkpoints", s["auto"]),
                            self.toggle(s, "auto"), (40, 60, 120)))
            B.append(Button((W // 2 - 140, 570, 280, 50), "Reset progress", self.reset_progress, red))
        elif st == "pause":
            B.append(Button((W // 2 - 190, 420, 80, 80), self.icon_play, self.resume, green, True))
            B.append(Button((W // 2 - 90, 420, 80, 80), self.icon_restart, lambda: (self.resume(), self.restart(True)), green, True))
            B.append(Button((W // 2 + 10, 420, 80, 80), self.icon_diamond, lambda: self.start(self.g.index, not self.g.practice),
                            (255, 201, 40) if self.g and self.g.practice else green, True))
            B.append(Button((W // 2 + 110, 420, 80, 80), self.icon_menu, lambda: self.click(lambda: self.go("levels")), green, True))
        elif st == "complete":
            B.append(Button((W // 2 - 100, 500, 80, 80), self.icon_restart, lambda: self.start(self.g.index, self.g.practice), green, True))
            B.append(Button((W // 2 + 20, 500, 80, 80), self.icon_menu, lambda: self.click(lambda: self.go("levels")), green, True))
        elif st == "play":
            B.append(Button((W - 64, 12, 50, 50), "II", self.pause, (30, 30, 50)))
            if self.g and self.g.practice:
                B.append(Button((18, H - 84, 66, 66), "+", lambda: self.add_cp(True), (30, 120, 60)))
                B.append(Button((96, H - 84, 66, 66), "-", self.remove_cp, (120, 40, 40)))
        self.buttons = B

    def click(self, fn):
        self.play_sfx("click")
        fn()

    def setter(self, d, key, val):
        def f():
            d[key] = val
            self.persist()
            self.play_sfx("click")
            self.build_buttons()
        return f

    def vol(self, key, delta):
        def f():
            s = self.save["settings"]
            s[key] = round(min(1.0, max(0.0, s[key] + delta)), 2)
            self.apply_volumes()
            self.persist()
            self.play_sfx("click")
        return f

    def toggle(self, d, key):
        def f():
            d[key] = not d[key]
            self.persist()
            self.play_sfx("click")
        return f

    def toggle_label(self, surf, r, label, on):
        text(surf, self.fonts["med"], ("[x] " if on else "[ ] ") + label, r.center, center=True, shadow=True)

    def reset_progress(self):
        self.save["levels"] = {}
        self.save["jumps"] = 0
        self.save["attempts"] = 0
        self.persist()
        self.toast = ("Progress reset", 1.5)
        self.play_sfx("click")

    def icon_play(self, surf, r):
        cx, cy, s = r.centerx + r.width * 0.06, r.centery, r.width * 0.3
        pygame.draw.polygon(surf, (255, 255, 255), [(cx - s * 0.8, cy - s), (cx + s, cy), (cx - s * 0.8, cy + s)])

    def icon_restart(self, surf, r):
        cx, cy, rad = r.centerx, r.centery, r.width * 0.24
        pygame.draw.arc(surf, (255, 255, 255), (cx - rad, cy - rad, rad * 2, rad * 2), 0.6, 2 * math.pi - 0.2, 6)
        tip = (cx + math.cos(0.6) * rad, cy - math.sin(0.6) * rad)
        pygame.draw.polygon(surf, (255, 255, 255), [(tip[0] - 12, tip[1] - 8), (tip[0] + 8, tip[1] - 12), (tip[0] + 4, tip[1] + 8)])

    def icon_diamond(self, surf, r):
        cx, cy, k = r.centerx, r.centery, r.width * 0.26
        pygame.draw.polygon(surf, (255, 255, 255), [(cx, cy - k), (cx + k, cy), (cx, cy + k), (cx - k, cy)])

    def icon_menu(self, surf, r):
        for i in (-1, 0, 1):
            y = r.centery + i * r.height * 0.18
            pygame.draw.line(surf, (255, 255, 255), (r.centerx - r.width * 0.22, y), (r.centerx + r.width * 0.22, y), 6)

    def icon_kit(self, surf, r):
        draw_cube(surf, r.centerx, r.centery, r.width * 0.5, 0, self.save["icon"])

    def icon_gear(self, surf, r):
        cx, cy = r.center
        for k in range(8):
            a = k * math.pi / 4
            pygame.draw.line(surf, (255, 255, 255), (cx + math.cos(a) * r.width * 0.12, cy + math.sin(a) * r.width * 0.12),
                             (cx + math.cos(a) * r.width * 0.32, cy + math.sin(a) * r.width * 0.32), 5)
        pygame.draw.circle(surf, (255, 255, 255), (cx, cy), r.width * 0.16, 4)

    def design_btn(self, i):
        def f(surf, r):
            ic = dict(self.save["icon"], design=i)
            draw_cube(surf, r.centerx, r.centery, r.width * 0.72, 0, ic)
            if self.save["icon"]["design"] == i:
                pygame.draw.rect(surf, (255, 255, 255), r.inflate(8, 8), 3, border_radius=8)
        return f

    def color_btn(self, col, sel):
        def f(surf, r):
            pygame.draw.rect(surf, hexc(col), r)
            pygame.draw.rect(surf, (0, 0, 0), r, 3)
            if sel:
                pygame.draw.rect(surf, (255, 255, 255), r.inflate(8, 8), 3)
        return f

    # ---- game flow
    def start(self, i, practice):
        self.play_sfx("click")
        data = self.levels[i]
        self.g = Run(i, data, practice, self.stats(i)["coins"])
        self.state = "play"
        self.build_buttons()
        self.restart(False)

    def restart(self, manual):
        g = self.g
        if g is None:
            return
        g.reset()
        self.held.clear()
        self.pressed = False
        if g.practice:
            g.checkpoints = []
            self.play_song(self.data["songs"]["practice"], "practice", loop=True)
        else:
            self.current_song = None
            self.play_song(g.data["song"], g.data["name"])
        s = self.stats(g.index)
        s["attempts"] += 1
        self.save["attempts"] += 1
        self.persist()
        if manual:
            self.play_sfx("click")

    def respawn(self):
        g = self.g
        if not g.checkpoints:
            self.restart(False)
            return
        cp = g.checkpoints[-1]
        g.player = cp["player"].clone()
        g.cam = list(cp["cam"])
        g.bg, g.ground, g.ceil, g.angle = cp["bg"], cp["ground"], cp["ceil"], cp["angle"]
        g.dead = False
        g.trail = []
        g.attempt += 1
        g.acc = 0.0
        self.stats(g.index)["attempts"] += 1

    def add_cp(self, manual):
        g = self.g
        if not g or not g.practice or g.dead or g.won:
            return
        g.checkpoints.append({"player": g.player.clone(), "cam": tuple(g.cam), "bg": g.bg, "ground": g.ground,
                              "ceil": g.ceil, "angle": g.angle})
        g.last_cp = g.time
        if manual:
            self.play_sfx("checkpoint")

    def remove_cp(self):
        if self.g and self.g.practice and self.g.checkpoints:
            self.g.checkpoints.pop()
            self.play_sfx("click")

    def pause(self):
        if self.g and not self.g.won:
            self.state = "pause"
            self.build_buttons()
            if self.audio_ok:
                pygame.mixer.music.pause()

    def resume(self):
        self.state = "play"
        self.build_buttons()
        if self.audio_ok:
            pygame.mixer.music.unpause()

    def die(self):
        g = self.g
        p = g.player
        g.dead = True
        g.death_timer = 0.65 if g.practice else 1.0
        g.burst(p.x + 0.5, p.y + 0.5, 34, [hexc(self.save["icon"]["primary"]), hexc(self.save["icon"]["secondary"]), (255, 255, 255)], 9, 0.8, 0.22)
        g.ring(p.x + 0.5, p.y + 0.5, hexc(self.save["icon"]["primary"]), 0.3, 3, 0.5)
        g.shake = 0.25
        self.play_sfx("death")
        pct = min(99, int(p.x / g.level.length * 100))
        s = self.stats(g.index)
        if g.practice:
            s["practice"] = max(s["practice"], pct)
        else:
            if pct > s["best"] and pct >= 1:
                self.toast = (f"New best: {pct}%", 1.4)
            s["best"] = max(s["best"], pct)
            self.stop_song(150)
        s["jumps"] += g.jumps
        self.save["jumps"] += g.jumps
        g.jumps = 0
        self.persist()

    def win(self):
        g = self.g
        p = g.player
        g.won = True
        g.win_timer = 1.6
        g.flash = 0.6
        prim = hexc(self.save["icon"]["primary"])
        for i in range(4):
            g.ring(p.x + 0.5, p.y + 0.5, (255, 255, 255) if i % 2 else prim, 0.5 + i * 0.4, 6 + i * 2, 0.8 + i * 0.15)
        g.burst(p.x + 0.5, p.y + 0.5, 60, [(255, 255, 255), (255, 226, 58), prim], 12, 1.2, 0.2)
        self.stop_song(1200)
        self.play_sfx("win")
        s = self.stats(g.index)
        s["jumps"] += g.jumps
        g.reward = ""
        if g.practice:
            s["practice"] = 100
        else:
            if not s["done"]:
                g.reward = f"+{g.data['stars']} stars"
            s["done"] = True
            s["best"] = 100
            if p.coins & ~s["coins"]:
                g.reward += ("   " if g.reward else "") + "New coins!"
            s["coins"] |= p.coins
        self.persist()

    # ---- main loop
    def run(self):
        while True:
            dt = min(0.1, self.clock.tick(120) / 1000.0)
            if not self.events():
                break
            if self.state == "play":
                self.update(dt)
            elif self.state == "complete" and self.g:
                self.g.time += dt
            self.draw(dt)
            pygame.display.flip()
        pygame.quit()

    def press(self, src):
        if src not in self.held:
            self.pressed = True
        self.held.add(src)

    def events(self):
        jump_keys = (pygame.K_SPACE, pygame.K_UP, pygame.K_w, pygame.K_RETURN)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                if self.state == "play":
                    if e.key in jump_keys:
                        self.press(e.key)
                    elif e.key in (pygame.K_ESCAPE, pygame.K_p):
                        self.pause()
                    elif e.key == pygame.K_r:
                        self.restart(True)
                    elif e.key == pygame.K_z:
                        self.add_cp(True)
                    elif e.key == pygame.K_x:
                        self.remove_cp()
                elif self.state == "pause":
                    if e.key in (pygame.K_ESCAPE, pygame.K_p, pygame.K_SPACE):
                        self.resume()
                    elif e.key == pygame.K_r:
                        self.resume()
                        self.restart(True)
                elif self.state == "levels":
                    if e.key == pygame.K_LEFT:
                        self.select(self.selected - 1)
                    elif e.key == pygame.K_RIGHT:
                        self.select(self.selected + 1)
                    elif e.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.start(self.selected, False)
                    elif e.key == pygame.K_ESCAPE:
                        self.go("main")
                elif self.state == "main":
                    if e.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.go("levels")
                    elif e.key == pygame.K_ESCAPE:
                        return False
                elif self.state == "complete":
                    if e.key in (pygame.K_SPACE, pygame.K_RETURN):
                        self.start(self.g.index, self.g.practice)
                    elif e.key == pygame.K_ESCAPE:
                        self.go("levels")
                elif e.key == pygame.K_ESCAPE:
                    self.go("main")
            elif e.type == pygame.KEYUP:
                self.held.discard(e.key)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for b in list(self.buttons):
                    if b.hit(e.pos):
                        b.action()
                        break
                else:
                    if self.state == "play":
                        self.press("mouse")
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                self.held.discard("mouse")
            elif e.type == pygame.WINDOWFOCUSLOST and self.state == "play":
                self.held.clear()
                self.pause()
        return True

    def update(self, dt):
        g = self.g
        p = g.player
        g.time += dt
        if not g.dead and not g.won:
            g.acc += dt
            steps = 0
            while g.acc >= STEP and steps < 30:
                h = bool(self.held) or self.pressed
                step(p, g.level, h, self.pressed)
                self.pressed = False
                g.acc -= STEP
                g.run_time += STEP
                steps += 1
                if p.events:
                    self.handle_events(p)
                g.update_angle(STEP)
                if p.dead:
                    self.die()
                    break
                if p.won:
                    g.run_jumps = g.jumps
                    self.win()
                    break
            if (g.practice and self.save["settings"]["auto"] and not g.dead and g.time - g.last_cp > 2.5
                    and (p.on_ground or p.mode in CEIL_MODES) and p.x > 4):
                self.add_cp(False)
        elif g.dead:
            g.death_timer -= dt
            if g.death_timer <= 0:
                if g.practice:
                    self.respawn()
                else:
                    self.restart(False)
        else:
            p.x += SPEEDS[p.speed] * dt
            g.win_timer -= dt
            if g.win_timer <= 0:
                self.state = "complete"
                self.build_buttons()
        g.update_visuals(dt, self.save["icon"])
        if self.toast:
            self.toast = (self.toast[0], self.toast[1] - dt) if self.toast[1] > 0 else None

    def handle_events(self, p):
        g = self.g
        for ev in p.events:
            if ev in ("jump", "flip", "orb"):
                g.jumps += 1
                if ev == "orb":
                    for o in g.level.near(p.x):
                        if (p.used >> o.id) & 1 and o.t.startswith("orb_") and o.id not in g.orb_hits:
                            g.orb_hits[o.id] = g.time
            elif ev == "pad":
                g.burst(p.x + 0.5, p.y, 8, [(255, 226, 58), (255, 255, 255)], 4, 0.4, 0.12)
            elif ev == "portal":
                g.ring(p.x + 0.5, p.y + 0.5, (255, 255, 255), 0.4, 2.2, 0.35)
            elif ev == "coin":
                for c in range(3):
                    if (p.coins >> c) & 1 and c not in g.coin_times:
                        g.coin_times[c] = g.time
                self.play_sfx("coin")
                g.ring(p.x + 0.5, p.y + 0.5, (255, 201, 40), 0.3, 1.8, 0.4)
            elif ev == "tele":
                g.tele_fx = (p.x, p.tele[0], p.tele[1], g.time)
        p.events.clear()

    # ---- drawing
    def draw(self, dt):
        surf = self.screen
        mouse = pygame.mouse.get_pos()
        if self.state in ("play", "pause", "complete") and self.g:
            Renderer(surf, self.g, self.save, self.fonts, self.pulse()).draw()
        else:
            self.menu_t += dt
            self.menu_bg = mix(self.menu_bg, self.menu_target[0], min(1, dt * 2))
            self.menu_ground = mix(self.menu_ground, self.menu_target[1], min(1, dt * 2))
            if self.state in ("main", "icons", "settings") and int(self.menu_t) % 6 == 0 and int(self.menu_t - dt) % 6 != 0:
                c = random.choice(self.levels)["colors"][0]
                self.menu_target = (hexc(c[1]), hexc(c[2]))
            r = Renderer(surf, None, self.save, self.fonts, self.pulse())
            r.cam = (self.menu_t * 4, -2.2)
            r.background(self.menu_bg)
            r.ground(self.menu_ground, 0)
        getattr(self, "draw_" + self.state, lambda s: None)(surf)
        for b in self.buttons:
            b.draw(surf, self.fonts, mouse)
        if self.toast:
            r = text(surf, self.fonts["med"], self.toast[0], (W // 2, 70), center=True, shadow=True)
            del r

    def draw_main(self, surf):
        t = self.menu_t
        logo = self.fonts["logo"]
        img = logo.render("NEON PULSE", True, (140, 246, 255))
        sh = logo.render("NEON PULSE", True, (10, 26, 102))
        img = pygame.transform.rotozoom(img, 3, 1)
        sh = pygame.transform.rotozoom(sh, 3, 1)
        r = img.get_rect(center=(W // 2, 190))
        surf.blit(sh, r.move(0, 8))
        surf.blit(img, r)
        stars = sum(lv["stars"] for i, lv in enumerate(self.levels) if self.stats(i)["done"])
        coins = sum(bin(self.stats(i)["coins"]).count("1") for i in range(len(self.levels)))
        done = sum(1 for i in range(len(self.levels)) if self.stats(i)["done"])
        text(surf, self.fonts["med"], f"Stars {stars}    Coins {coins}/{len(self.levels) * 3}    {done}/{len(self.levels)} levels",
             (W // 2, 545), center=True, shadow=True)
        text(surf, self.fonts["small"], "Click, Space or Up to jump  -  Esc pause  -  R restart  -  F fullscreen",
             (W // 2, H - 24), center=True, shadow=True)
        phase = t % 1.25
        h = 21 * phase - 50 * phase * phase if phase < 0.42 else 0
        ang = phase / 0.42 * math.pi if phase < 0.42 else 0
        draw_cube(surf, W * 0.18, H - (2.2 + h + 0.5) * U, U * 0.98, ang, self.save["icon"])

    def draw_levels(self, surf):
        lv = self.levels[self.selected]
        s = self.stats(self.selected)
        card = pygame.Rect(W // 2 - 330, 170, 660, 400)
        panel(surf, card, ci(shade(hexc(lv["colors"][0][2]), -0.4)), 215)
        draw_face(surf, lv["diff"], card.x + 70, card.y + 75, 40)
        text(surf, self.fonts["title"], lv["name"], (card.x + 135, card.y + 35), shadow=True)
        text(surf, self.fonts["med"], f"{lv['difficulty']}   * {lv['stars']}", (card.x + 137, card.y + 90), (255, 201, 40))
        for c in range(3):
            got = (s["coins"] >> c) & 1
            center = (card.right - 110 + c * 36, card.y + 75)
            pygame.draw.circle(surf, (255, 201, 40) if got else (60, 60, 80), center, 14)
            pygame.draw.circle(surf, (120, 80, 0) if got else (150, 150, 170), center, 14, 3)
        text(surf, self.fonts["small"], "Normal mode", (card.x + 30, card.y + 140))
        progress_bar(surf, self.fonts, pygame.Rect(card.x + 30, card.y + 162, card.width - 60, 26), s["best"])
        text(surf, self.fonts["small"], "Practice mode", (card.x + 30, card.y + 200))
        progress_bar(surf, self.fonts, pygame.Rect(card.x + 30, card.y + 222, card.width - 60, 26), s["practice"], True)
        text(surf, self.fonts["small"], f"{round(lv['seconds'])}s long  -  {s['attempts']} attempts  -  {s['jumps']} jumps"
             + ("  -  completed" if s["done"] else ""), (W // 2, card.bottom - 25), center=True)
        for i in range(len(self.levels)):
            pygame.draw.circle(surf, (255, 255, 255) if i == self.selected else (110, 110, 140), (W // 2 - 70 + i * 20, card.bottom + 30), 6)

    def draw_icons(self, surf):
        text(surf, self.fonts["title"], "Icon Kit", (W // 2, 60), center=True, shadow=True)
        panel(surf, pygame.Rect(W // 2 - 330, 110, 660, 470))
        for i, m in enumerate(("cube", "rocket", "ball", "saucer", "dart", "mech", "crawler")):
            draw_player(surf, m, W // 2 - 270 + i * 90, 190, 60, -0.3 if m == "dart" else 0, self.save["icon"], 0.1)
        text(surf, self.fonts["small"], "Design", (W // 2 - 300, 265))
        text(surf, self.fonts["small"], "Primary colour", (W // 2 - 300, 375))
        text(surf, self.fonts["small"], "Secondary colour", (W // 2 - 300, 475))

    def draw_settings(self, surf):
        text(surf, self.fonts["title"], "Settings", (W // 2, 140), center=True, shadow=True)
        panel(surf, pygame.Rect(W // 2 - 260, 210, 520, 440))
        s = self.save["settings"]
        for row, (key, label) in enumerate((("music", "Music"), ("sfx", "Sound effects"))):
            y = 250 + row * 80
            text(surf, self.fonts["med"], label, (W // 2 - 220, y + 12))
            text(surf, self.fonts["med"], f"{int(round(s[key] * 100))}%", (W // 2 + 150, y + 25), center=True)

    def draw_pause(self, surf):
        g = self.g
        shade_s = pygame.Surface((W, H), pygame.SRCALPHA)
        shade_s.fill((0, 0, 0, 110))
        surf.blit(shade_s, (0, 0))
        panel(surf, pygame.Rect(W // 2 - 280, 190, 560, 340))
        text(surf, self.fonts["big"], g.data["name"], (W // 2, 230), center=True, shadow=True)
        s = self.stats(g.index)
        text(surf, self.fonts["small"], "Normal mode", (W // 2 - 240, 265))
        progress_bar(surf, self.fonts, pygame.Rect(W // 2 - 240, 287, 480, 24), s["best"])
        text(surf, self.fonts["small"], "Practice mode", (W // 2 - 240, 325))
        progress_bar(surf, self.fonts, pygame.Rect(W // 2 - 240, 347, 480, 24), s["practice"], True)
        text(surf, self.fonts["small"], "Resume  -  Restart  -  Practice on/off  -  Levels", (W // 2, 395), center=True)

    def draw_complete(self, surf):
        g = self.g
        shade_s = pygame.Surface((W, H), pygame.SRCALPHA)
        shade_s.fill((0, 0, 0, 110))
        surf.blit(shade_s, (0, 0))
        panel(surf, pygame.Rect(W // 2 - 280, 150, 560, 460))
        text(surf, self.fonts["title"], "Practice Complete!" if g.practice else "Level Complete!", (W // 2, 200),
             (255, 229, 106), center=True, shadow=True)
        secs = int(g.run_time)
        for i, (k, v) in enumerate((("Attempts", g.attempt), ("Jumps", g.run_jumps), ("Time", f"{secs // 60}:{secs % 60:02d}"))):
            text(surf, self.fonts["med"], k, (W // 2 - 140, 260 + i * 36))
            text(surf, self.fonts["med"], str(v), (W // 2 + 140, 260 + i * 36), right=True)
        for c in range(3):
            got = (g.player.coins >> c) & 1 and not g.practice
            center = (W // 2 - 50 + c * 50, 395)
            pygame.draw.circle(surf, (255, 201, 40) if got else (60, 60, 80), center, 18)
            pygame.draw.circle(surf, (120, 80, 0) if got else (150, 150, 170), center, 18, 3)
        text(surf, self.fonts["med"], g.reward or ("Now try it in normal mode!" if g.practice else ""), (W // 2, 450),
             (255, 201, 40), center=True)


class Run:
    """State of one play session of a level."""

    def __init__(self, index, data, practice, prev_coins):
        self.index = index
        self.data = data
        self.level = Level(data)
        self.practice = practice
        self.prev_coins = prev_coins
        self.attempt = 0
        self.checkpoints = []
        self.time = 0.0
        self.last_cp = 0.0
        self.run_jumps = 0
        self.reward = ""

    def reset(self):
        self.player = Player(self.data["startMode"], self.data["startSpeed"])
        self.attempt += 1
        self.dead = False
        self.won = False
        self.death_timer = 0.0
        self.win_timer = 0.0
        self.angle = 0.0
        self.trail = []
        self.particles = []
        self.rings = []
        self.orb_hits = {}
        self.coin_times = {}
        self.run_time = 0.0
        self.jumps = 0
        self.shake = 0.0
        self.flash = 0.0
        self.acc = 0.0
        self.tele_fx = None
        c = self.data["colors"][0]
        self.bg = hexc(c[1])
        self.ground = hexc(c[2])
        self.cam = [self.player.x - 6.4, -2.2]
        self.ceil = 0.0

    def burst(self, x, y, n, colors, speed, life, size):
        for i in range(n):
            a = random.random() * math.pi * 2
            v = speed * (0.3 + random.random() * 0.7)
            lf = life * (0.5 + random.random() * 0.5)
            self.particles.append([x, y, math.cos(a) * v, math.sin(a) * v, lf, life, colors[i % len(colors)],
                                   size * (0.5 + random.random())])

    def ring(self, x, y, color, r0, r1, life):
        self.rings.append([x, y, color, r0, r1, life, life])

    def update_angle(self, dt):
        p = self.player
        sp = SPEEDS[p.speed]
        if p.mode == "cube":
            if p.on_ground:
                q = math.pi / 2
                self.angle += (round(self.angle / q) * q - self.angle) * min(1.0, dt * 30)
            else:
                self.angle += p.g * 7.4 * dt
        elif p.mode == "rocket":
            self.angle = -math.atan2(p.vy, sp) * 0.8
        elif p.mode == "dart":
            self.angle = -math.atan2(p.vy, sp)
        elif p.mode == "ball":
            self.angle += p.g * sp * 1.6 * dt
        elif p.mode == "saucer":
            self.angle = -p.vy * 0.015
        else:
            self.angle = 0.0

    def update_visuals(self, dt, icon):
        p = self.player
        self.cam[0] = p.x - 6.4
        corridor = p.mode in CEIL_MODES
        if corridor:
            ty = -1.0
        else:
            view = 11.0
            ty = self.cam[1]
            if p.y + 1 > ty + view * 0.72:
                ty = p.y + 1 - view * 0.72
            if p.y < ty + view * 0.25:
                ty = max(-2.2, p.y - view * 0.25)
        self.cam[1] += (ty - self.cam[1]) * min(1.0, dt * 5)
        self.ceil += ((1.0 if corridor else 0.0) - self.ceil) * min(1.0, dt * 6)
        c = self.data["colors"][0]
        for t in self.data["colors"]:
            if t[0] <= p.x:
                c = t
        k = min(1.0, dt * 2.5)
        self.bg = mix(self.bg, hexc(c[1]), k)
        self.ground = mix(self.ground, hexc(c[2]), k)
        if not self.dead:
            self.trail.append((p.x + 0.5 - (0.2 if p.mode == "dart" else 0.45), p.y + 0.5))
            mx = 60 if p.mode == "dart" else 14
            del self.trail[:-mx]
            if p.on_ground and p.mode in ("cube", "mech") and random.random() < 0.5:
                self.particles.append([p.x + 0.1, p.y + (0.08 if p.g > 0 else 0.92), -2 - random.random() * 2,
                                       random.random() * 1.5 * p.g, 0.3, 0.3, hexc(icon["primary"]), 0.1])
            if p.mode in ("rocket", "saucer"):
                self.particles.append([p.x + 0.05, p.y + 0.35, -4, (random.random() - 0.5) * 2, 0.35, 0.35,
                                       (255, 180, 58) if random.random() < 0.5 else (255, 106, 42), 0.14])
        for q in self.particles:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[2] *= 0.97
            q[3] *= 0.97
            q[4] -= dt
        self.particles = [q for q in self.particles if q[4] > 0]
        for r in self.rings:
            r[5] -= dt
        self.rings = [r for r in self.rings if r[5] > 0]
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt * 1.5)


class Renderer:
    _glow_cache = {}

    def __init__(self, surf, g, save, fonts, pulse):
        self.s = surf
        self.g = g
        self.save = save
        self.fonts = fonts
        self.pulse = pulse
        self.cam = tuple(g.cam) if g else (0, -2.2)
        if g and g.shake > 0:
            self.cam = (self.cam[0] + (random.random() - 0.5) * g.shake, self.cam[1] + (random.random() - 0.5) * g.shake)

    def sx(self, x):
        return (x - self.cam[0]) * U

    def sy(self, y):
        return H - (y - self.cam[1]) * U

    def glow(self, color, radius):
        key = (color, int(radius))
        surf = self._glow_cache.get(key)
        if surf is None:
            r = int(radius)
            surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            for i in range(r, 0, -2):
                a = int(110 * (1 - i / r) ** 1.5)
                pygame.draw.circle(surf, color + (a,), (r, r), i)
            self._glow_cache[key] = surf
        return surf

    def background(self, bg):
        top, bot = shade(bg, -0.15 + self.pulse * 0.05), shade(bg, -0.55)
        bands = 24
        for i in range(bands):
            pygame.draw.rect(self.s, ci(mix(top, bot, i / (bands - 1))), (0, i * H // bands, W, H // bands + 1))
        for f, size, amt in ((0.08, 3.2, 0.09), (0.18, 2.0, 0.07)):
            px = size * U
            off = -((self.cam[0] * f * U) % (px * 2))
            col = ci(shade(bg, -0.15 + amt))
            x = off - px * 2
            while x < W + px:
                y = px * 0.5 if f > 0.1 else 0
                while y < H:
                    pygame.draw.rect(self.s, col, (x, y, px * 0.92, px * 0.92), 2)
                    y += px * 2
                x += px * 2

    def ground(self, gcol, ceil):
        gy = self.sy(0)
        tile = 4 * U

        def strip(y0, y1, line_y):
            bands = 8
            for i in range(bands):
                yy = y0 + (y1 - y0) * i / bands
                pygame.draw.rect(self.s, ci(shade(gcol, 0.05 - 0.65 * i / bands)), (0, min(yy, yy + (y1 - y0) / bands), W, abs(y1 - y0) / bands + 1))
            off = -((self.cam[0] * U) % tile)
            x = off
            while x < W:
                pygame.draw.rect(self.s, ci(shade(gcol, -0.35)), (x, min(y0, y1), tile, min(tile, abs(y1 - y0))), 2)
                x += tile
            pygame.draw.line(self.s, (255, 255, 255), (W * 0.1, line_y), (W * 0.9, line_y), 3)
            pygame.draw.line(self.s, ci(shade(gcol, 0.6)), (0, line_y), (W * 0.1, line_y), 2)
            pygame.draw.line(self.s, ci(shade(gcol, 0.6)), (W * 0.9, line_y), (W, line_y), 2)

        if gy < H:
            strip(gy, H, gy)
        if ceil > 0.01:
            cy = self.sy(CEIL) - (1 - ceil) * 3 * U
            if cy > 0:
                strip(cy, 0, cy)

    def draw(self):
        g = self.g
        self.background(g.bg)
        self.attempt_text()
        self.objects()
        self.ground(g.ground, g.ceil)
        self.checkpoints()
        if not g.player.dead:
            self.player()
        self.particles()
        if g.flash > 0:
            fl = pygame.Surface((W, H), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(255 * min(1, g.flash))))
            self.s.blit(fl, (0, 0))
        self.hud()

    def attempt_text(self):
        g = self.g
        x, y = self.sx(2), self.sy(5.2)
        if x < -U * 12:
            return
        label = "Practice" if g.practice else f"Attempt {g.attempt}"
        text(self.s, self.fonts["world"], label, (x, y - U), shadow=True)

    def visible(self):
        lvl = self.g.level
        seen = set()
        x0 = int(math.floor(self.cam[0])) - 2
        x1 = int(math.ceil(self.cam[0] + W / U)) + 2
        out = []
        for c in range(x0, x1 + 1):
            for o in lvl.cols.get(c, ()):
                if o.id not in seen:
                    seen.add(o.id)
                    out.append(o)
        return out

    def objects(self):
        g = self.g
        s = self.s
        accent = ci(shade(g.bg, 0.65))
        objs = self.visible()
        for o in objs:
            if o.t.startswith("p_"):
                self.portal(o)
        for o in objs:
            if o.t == "block":
                r = pygame.Rect(self.sx(o.x), self.sy(o.y2), o.w * U + 1, o.h * U + 1)
                pygame.draw.rect(s, ci(shade(g.bg, -0.85)), r)
                inner = ci(shade(g.bg, -0.55))
                for i in range(1, int(o.w)):
                    pygame.draw.line(s, inner, (r.x + i * U, r.y), (r.x + i * U, r.bottom))
                for j in range(1, int(o.h)):
                    pygame.draw.line(s, inner, (r.x, r.y + j * U), (r.right, r.y + j * U))
                pygame.draw.rect(s, accent, r, max(2, int(U * 0.06)))
            elif o.t == "saw":
                cx, cy, rr = self.sx(o.x), self.sy(o.y), o.r * U
                ang = g.time * 6
                pts = [(cx + math.cos(ang + i * math.pi / 14) * (rr if i % 2 == 0 else rr * 0.82),
                        cy + math.sin(ang + i * math.pi / 14) * (rr if i % 2 == 0 else rr * 0.82)) for i in range(28)]
                pygame.draw.polygon(s, (10, 10, 14), pts)
                pygame.draw.polygon(s, accent, pts, 3)
                pygame.draw.circle(s, accent, (cx, cy), rr * 0.45, 3)
                pygame.draw.circle(s, accent, (cx, cy), rr * 0.15)
            elif o.t.startswith("spike"):
                small = o.t in ("spike_s", "spike_sd")
                down = o.t in ("spike_d", "spike_sd")
                hh = (0.45 if small else 1.0) * U
                x = self.sx(o.x)
                base = self.sy(o.y + 1) if down else self.sy(o.y)
                tip = base + hh if down else base - hh
                pts = [(x + U * 0.06, base), (x + U * 0.5, tip), (x + U * 0.94, base)]
                pygame.draw.polygon(s, (5, 5, 8), pts)
                pygame.draw.polygon(s, (255, 255, 255), pts, 2)
        for o in objs:
            if o.t.startswith("orb_"):
                self.orb(o)
            elif o.t.startswith("pad_"):
                self.pad(o)
            elif o.t == "coin":
                self.coin(o)

    def orb(self, o):
        g = self.g
        col = hexc(ORB_COLORS[o.t])
        cx, cy = self.sx(o.x + 0.5), self.sy(o.y + 0.5)
        used = (g.player.used >> o.id) & 1
        gl = self.glow(col if o.t != "orb_k" else (255, 60, 60), U * 0.9)
        if not used:
            self.s.blit(gl, gl.get_rect(center=(cx, cy)))
        pygame.draw.circle(self.s, col, (cx, cy), U * (0.3 + self.pulse * 0.04))
        pygame.draw.circle(self.s, (255, 60, 60) if o.t == "orb_k" else (255, 255, 255), (cx, cy), U * (0.3 + self.pulse * 0.04), 3)
        pygame.draw.circle(self.s, col if o.t != "orb_k" else (255, 60, 60), (cx, cy), U * (0.46 + self.pulse * 0.08), 2)
        t0 = g.orb_hits.get(o.id)
        if t0 is not None:
            k = min(1.0, (g.time - t0) / 0.35)
            if k < 1:
                pygame.draw.circle(self.s, col, (cx, cy), U * (0.4 + k * 0.9), max(1, int(U * 0.08 * (1 - k))))

    def pad(self, o):
        col = hexc(PAD_COLORS[o.t])
        x = self.sx(o.x)
        base = self.sy(o.y + 1) if o.flip else self.sy(o.y)
        r = pygame.Rect(x + U * 0.05, base - U * 0.2, U * 0.9, U * 0.4)
        pygame.draw.ellipse(self.s, col, r)
        pygame.draw.ellipse(self.s, (255, 255, 255), r, 2)
        gl = self.glow(col, U * 0.6)
        self.s.blit(gl, gl.get_rect(center=(x + U * 0.5, base - (U * 0.3 if not o.flip else -U * 0.3))))

    def coin(self, o):
        g = self.g
        idx = int(o.r)
        got = (g.player.coins >> idx) & 1
        t0 = g.coin_times.get(idx, g.time)
        cx, cy = self.sx(o.x + 0.5), self.sy(o.y + 0.5) - ((g.time - t0) * U * 3 if got else 0)
        if got and g.time - t0 > 0.6:
            return
        prev = (g.prev_coins >> idx) & 1
        w = abs(math.cos(g.time * 3)) * U * 0.84 + 2
        r = pygame.Rect(0, 0, w, U * 0.84)
        r.center = (cx, cy)
        pygame.draw.ellipse(self.s, (154, 164, 184) if prev else (255, 201, 40), r)
        pygame.draw.ellipse(self.s, (91, 100, 120) if prev else (176, 122, 0), r, 3)

    def portal(self, o):
        g = self.g
        col = hexc(PORTAL_COLORS.get(o.t, "#ffffff"))
        cx = self.sx(o.x + 0.5)
        cy = self.sy(o.y + o.h / 2)
        if o.t in SPEED_ARROWS:
            n = SPEED_ARROWS[o.t]
            d = -1 if n < 0 else 1
            for i in range(abs(n)):
                ox = cx + (i - (abs(n) - 1) / 2) * U * 0.45
                pts = [(ox - d * U * 0.3, cy - U * 0.8), (ox + d * U * 0.3, cy), (ox - d * U * 0.3, cy + U * 0.8), (ox - d * U * 0.05, cy)]
                pygame.draw.polygon(self.s, col, pts)
                pygame.draw.polygon(self.s, (255, 255, 255), pts, 2)
            return
        ry = o.h / 2 * U * 0.95
        r = pygame.Rect(0, 0, U * 1.1, ry * 2)
        r.center = (cx, cy)
        gl = self.glow(col, min(ry, U * 2.5))
        self.s.blit(gl, gl.get_rect(center=(cx, cy)))
        pygame.draw.ellipse(self.s, ci(shade(col, -0.3)), r, int(U * 0.22))
        pygame.draw.ellipse(self.s, ci(shade(col, 0.3 + self.pulse * 0.3)), r.inflate(-U * 0.06, -U * 0.06), int(U * 0.1))
        for i in range(5):
            k = (g.time * 1.5 + i / 5 + o.id * 0.37) % 1
            py = cy + math.sin(i * 2.3 + o.id) * ry * 0.7
            pygame.draw.rect(self.s, ci(mix(col, g.bg, k)), (cx + (1 - k) * U * 1.2, py, U * 0.1, U * 0.1))

    def checkpoints(self):
        for c in self.g.checkpoints:
            p = c["player"]
            x, y = self.sx(p.x + 0.5), self.sy(p.y + 0.5)
            if -U < x < W + U:
                pts = [(x, y - U * 0.3), (x + U * 0.3, y), (x, y + U * 0.3), (x - U * 0.3, y)]
                pygame.draw.polygon(self.s, (60, 255, 120), pts)
                pygame.draw.polygon(self.s, (0, 80, 30), pts, 2)

    def player(self):
        g = self.g
        p = g.player
        icon = self.save["icon"]
        if len(g.trail) > 1 and p.mode in ("dart", "rocket"):
            pts = [(self.sx(x), self.sy(y)) for x, y in g.trail]
            wide = p.mode == "dart"
            pygame.draw.lines(self.s, hexc(icon["secondary"] if wide else icon["primary"]), False, pts, int(U * (0.3 if wide else 0.16)))
            if wide:
                pygame.draw.lines(self.s, (255, 255, 255), False, pts, max(2, int(U * 0.1)))
        if g.tele_fx and g.time - g.tele_fx[3] < 0.25:
            x = self.sx(g.tele_fx[0] + 0.5)
            y0, y1 = self.sy(g.tele_fx[1] + 0.5), self.sy(g.tele_fx[2] + 0.5)
            pygame.draw.rect(self.s, (200, 140, 255), (x - U * 0.4, min(y0, y1), U * 0.8, abs(y1 - y0)))
        cx, cy = self.sx(p.x + 0.5), self.sy(p.y + 0.5)
        gl = self.glow((255, 255, 255), U * 1.1)
        self.s.blit(gl, gl.get_rect(center=(cx, cy)))
        draw_player(self.s, p.mode, cx, cy, U * 0.98, g.angle, icon, g.time, p.g < 0)

    def particles(self):
        g = self.g
        for q in g.particles:
            a = max(0.0, q[4] / q[5])
            size = q[7] * U * a
            pygame.draw.rect(self.s, ci(mix(g.bg, q[6], a)), (self.sx(q[0]) - size / 2, self.sy(q[1]) - size / 2, size, size))
        for r in g.rings:
            k = 1 - r[5] / r[6]
            rad = (r[3] + k * r[4]) * U
            pygame.draw.circle(self.s, ci(mix(r[2], g.bg, k)), (self.sx(r[0]), self.sy(r[1])), rad, max(1, int(U * 0.15 * (1 - k)) + 1))

    def hud(self):
        g = self.g
        pct = max(0.0, min(1.0, g.player.x / g.level.length))
        bw, bh = 520, 12
        bx, by = (W - bw) // 2, 14
        pygame.draw.rect(self.s, (0, 0, 0), (bx - 2, by - 2, bw + 4, bh + 4))
        pygame.draw.rect(self.s, (58, 255, 124) if g.practice else (85, 170, 255), (bx, by, bw * pct, bh))
        pygame.draw.rect(self.s, (240, 240, 240), (bx - 2, by - 2, bw + 4, bh + 4), 2)
        if self.save["settings"]["percent"]:
            text(self.s, self.fonts["med"], f"{int(pct * 100)}%", (bx + bw + 12, by - 4), shadow=True)


def main():
    Game().run()
