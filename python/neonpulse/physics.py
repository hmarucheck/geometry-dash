"""Deterministic game physics for Neon Pulse.

This module is the reference implementation of the rules. The browser
version (web/js/engine.js) is a line-by-line port of it, and
tools/check_parity.js replays solver runs through both to make sure they
agree. Keep the two files in sync when changing anything here.

Units: one grid block = 1.0. The player is a 1x1 box whose bottom-left
corner is (x, y). The ground surface is y = 0. Positive y is up.
Gravity direction g is +1 (normal, falls down) or -1 (flipped).
"""

import math

STEP = 1.0 / 120.0
SPEEDS = (8.4, 10.4, 12.96, 15.6, 19.2)
CEIL = 9.0
CEIL_MODES = ("rocket", "ball", "saucer", "dart", "crawler")
HEADBUTT_MODES = ("cube", "mech")
MODES = ("cube", "rocket", "ball", "saucer", "dart", "mech", "crawler")

CUBE_G = 100.0
CUBE_JUMP = 21.0
MAX_FALL = 26.0
ROCKET_UP = 48.0
ROCKET_DOWN = 40.0
ROCKET_MAX = 11.0
BALL_G = 80.0
BALL_PUSH = 3.0
BALL_MAX = 20.0
SAUCER_G = 60.0
SAUCER_FLAP = 14.0
SAUCER_MAX = 13.0
MECH_JUMP = 14.0
MECH_BOOST = 0.15

ORB_POWER = {"orb_y": 1.0, "orb_p": 0.68, "orb_r": 1.35}
PAD_POWER = {"pad_y": 1.4, "pad_p": 0.78, "pad_r": 1.75}
MODE_ORB_SCALE = {"cube": 1.0, "mech": 1.0, "crawler": 1.0, "rocket": 0.55,
                  "ball": 0.75, "saucer": 0.75, "dart": 0.0}

SOLID = ("block",)
HAZARDS = ("spike", "spike_d", "spike_s", "spike_sd", "saw")
ORBS = ("orb_y", "orb_p", "orb_r", "orb_b", "orb_g", "orb_k")
PADS = ("pad_y", "pad_p", "pad_r", "pad_b")
PORTALS = ("p_cube", "p_rocket", "p_ball", "p_saucer", "p_dart", "p_mech",
           "p_crawler", "p_gup", "p_gdown", "p_gflip",
           "p_s0", "p_s1", "p_s2", "p_s3", "p_s4")

SPEED_PORTALS = {"p_s0": 0, "p_s1": 1, "p_s2": 2, "p_s3": 3, "p_s4": 4}

# Spike hitboxes relative to their cell: (x0, x1, y0, y1)
SPIKE_BOX = {
    "spike": (0.32, 0.68, 0.0, 0.65),
    "spike_d": (0.32, 0.68, 0.35, 1.0),
    "spike_s": (0.32, 0.68, 0.0, 0.35),
    "spike_sd": (0.32, 0.68, 0.65, 1.0),
}


class Obj:
    __slots__ = ("id", "t", "x", "y", "w", "h", "x2", "y2", "r", "flip")

    def __init__(self, oid, d):
        self.id = oid
        self.t = d["t"]
        self.x = float(d["x"])
        self.y = float(d["y"])
        self.w = float(d.get("w", 1))
        self.h = float(d.get("h", 3 if self.t.startswith("p_") else 1))
        self.r = float(d.get("r", 1))
        self.flip = bool(d.get("flip", False))
        self.x2 = self.x + self.w
        self.y2 = self.y + self.h


class Level:
    """A level's objects bucketed by integer column for fast lookup."""

    def __init__(self, data):
        self.data = data
        self.name = data["name"]
        self.length = float(data["length"])
        self.objects = [Obj(i, d) for i, d in enumerate(data["objects"])]
        self.cols = {}
        for o in self.objects:
            if o.t == "saw":
                c0, c1 = int(math.floor(o.x - o.r)), int(math.floor(o.x + o.r))
            else:
                c0, c1 = int(math.floor(o.x)), int(math.floor(o.x2 - 1e-9))
            for c in range(c0, c1 + 1):
                self.cols.setdefault(c, []).append(o)
        self.coins = [o for o in self.objects if o.t == "coin"]

    def near(self, x):
        c = int(math.floor(x))
        out = []
        for cc in (c - 1, c, c + 1):
            lst = self.cols.get(cc)
            if lst:
                out.extend(lst)
        return out

    def column_objs(self, x0, x1):
        out = []
        for cc in range(int(math.floor(x0)), int(math.floor(x1)) + 1):
            lst = self.cols.get(cc)
            if lst:
                out.extend(lst)
        return out


class Player:
    __slots__ = ("x", "y", "vy", "g", "mode", "speed", "on_ground", "buffered",
                 "boost", "used", "coins", "dead", "won", "tele", "events")

    def __init__(self, mode="cube", speed=1):
        self.x = 0.0
        self.y = 0.0
        self.vy = 0.0
        self.g = 1
        self.mode = mode
        self.speed = speed
        self.on_ground = True
        self.buffered = False
        self.boost = 0.0
        self.used = 0  # bitmask of object ids already triggered
        self.coins = 0  # bitmask of coin indices collected
        self.dead = False
        self.won = False
        self.tele = None  # (y_from, y_to) of last crawler teleport, for visuals
        self.events = []  # transient visual/audio events for renderers

    def clone(self):
        p = Player.__new__(Player)
        p.x, p.y, p.vy, p.g = self.x, self.y, self.vy, self.g
        p.mode, p.speed, p.on_ground = self.mode, self.speed, self.on_ground
        p.buffered, p.boost, p.used, p.coins = self.buffered, self.boost, self.used, self.coins
        p.dead, p.won, p.tele = self.dead, self.won, None
        p.events = []
        return p


def _overlap(ax0, ax1, ay0, ay1, bx0, bx1, by0, by1):
    return ax1 > bx0 and ax0 < bx1 and ay1 > by0 and ay0 < by1


def _set_mode(p, mode):
    if p.mode == mode:
        return
    p.mode = mode
    p.vy *= 0.5
    p.boost = 0.0
    p.on_ground = False
    p.events.append("portal")


def _apply_orb(p, o):
    t = o.t
    g = p.g
    if t in ORB_POWER:
        s = MODE_ORB_SCALE[p.mode]
        if s == 0.0:
            return False
        p.vy = g * CUBE_JUMP * ORB_POWER[t] * s
    elif t == "orb_b":
        p.g = -g
        p.vy = -p.g * 8.0
    elif t == "orb_g":
        p.g = -g
        p.vy = -p.g * 16.0
    elif t == "orb_k":
        p.vy = -g * 24.0
    p.on_ground = False
    p.boost = 0.0
    return True


def _apply_pad(p, o):
    t = o.t
    g = p.g
    if t == "pad_b":
        p.g = -g
        p.vy = -p.g * 15.0
    else:
        s = MODE_ORB_SCALE[p.mode]
        if s == 0.0:
            s = 0.5
        p.vy = g * CUBE_JUMP * PAD_POWER[t] * s
    p.on_ground = False
    p.boost = 0.0


def _apply_portal(p, o):
    t = o.t
    if t == "p_gup":
        if p.g != -1:
            p.g = -1
            p.vy *= 0.5
    elif t == "p_gdown":
        if p.g != 1:
            p.g = 1
            p.vy *= 0.5
    elif t == "p_gflip":
        p.g = -p.g
        p.vy *= 0.5
    elif t in SPEED_PORTALS:
        p.speed = SPEED_PORTALS[t]
    else:
        _set_mode(p, t[2:])
    p.events.append("portal")


def _crawler_teleport(p, lvl):
    x0 = p.x + 0.05
    x1 = p.x + 0.95
    if p.g > 0:
        target = CEIL - 1.0
        for b in lvl.column_objs(x0, x1):
            if b.t == "block" and b.x2 > x0 and b.x < x1:
                if b.y >= p.y + 1.0 - 1e-6 and b.y - 1.0 < target:
                    target = b.y - 1.0
    else:
        target = 0.0
        for b in lvl.column_objs(x0, x1):
            if b.t == "block" and b.x2 > x0 and b.x < x1:
                if b.y2 <= p.y + 1e-6 and b.y2 > target:
                    target = b.y2
    p.tele = (p.y, target)
    p.y = target
    p.g = -p.g
    p.vy = 0.0
    p.on_ground = True
    p.events.append("tele")


def step(p, lvl, held, pressed):
    """Advance the player by one fixed STEP.

    held: the jump button is down during this step.
    pressed: the button went down since the previous step.
    """
    if p.dead or p.won:
        return
    if pressed:
        p.buffered = True
    dt = STEP
    p.x += SPEEDS[p.speed] * dt
    near = lvl.near(p.x)

    # Orbs take priority over the mode's own click action.
    if p.buffered:
        pcx = p.x + 0.5
        pcy = p.y + 0.5
        for o in near:
            if o.t in ORBS and not (p.used >> o.id) & 1:
                if abs(pcx - (o.x + 0.5)) < 0.95 and abs(pcy - (o.y + 0.5)) < 0.95:
                    if _apply_orb(p, o):
                        p.used |= 1 << o.id
                        p.buffered = False
                        p.events.append("orb")
                        break

    mode = p.mode
    g = p.g
    if mode == "cube":
        if p.on_ground and held:
            p.vy = g * CUBE_JUMP
            p.on_ground = False
            p.buffered = False
            p.events.append("jump")
        p.vy -= g * CUBE_G * dt
        if p.vy * g < -MAX_FALL:
            p.vy = -MAX_FALL * g
    elif mode == "mech":
        if p.on_ground and held:
            p.vy = g * MECH_JUMP
            p.boost = MECH_BOOST
            p.on_ground = False
            p.buffered = False
            p.events.append("jump")
        if p.boost > 0.0 and held:
            p.vy = g * MECH_JUMP
            p.boost -= dt
        else:
            p.boost = 0.0
            p.vy -= g * CUBE_G * dt
            if p.vy * g < -MAX_FALL:
                p.vy = -MAX_FALL * g
    elif mode == "rocket":
        if held:
            p.vy += g * ROCKET_UP * dt
        else:
            p.vy -= g * ROCKET_DOWN * dt
        if p.vy > ROCKET_MAX:
            p.vy = ROCKET_MAX
        elif p.vy < -ROCKET_MAX:
            p.vy = -ROCKET_MAX
    elif mode == "ball":
        if p.on_ground and p.buffered:
            g = -g
            p.g = g
            p.vy = -g * BALL_PUSH
            p.on_ground = False
            p.buffered = False
            p.events.append("flip")
        p.vy -= g * BALL_G * dt
        if p.vy * g < -BALL_MAX:
            p.vy = -BALL_MAX * g
    elif mode == "saucer":
        if p.buffered:
            p.vy = g * SAUCER_FLAP
            p.buffered = False
            p.on_ground = False
            p.events.append("jump")
        p.vy -= g * SAUCER_G * dt
        if p.vy * g < -SAUCER_MAX:
            p.vy = -SAUCER_MAX * g
    elif mode == "dart":
        p.vy = (1.0 if held else -1.0) * g * SPEEDS[p.speed]
    elif mode == "crawler":
        if p.on_ground and p.buffered:
            p.buffered = False
            _crawler_teleport(p, lvl)
            g = p.g
        p.vy -= g * CUBE_G * dt
        if p.vy * g < -MAX_FALL:
            p.vy = -MAX_FALL * g

    p.y += p.vy * dt

    # Solid collisions.
    p.on_ground = False
    headbutt = mode in HEADBUTT_MODES
    if p.y < 0.0:
        if g < 0 and headbutt:
            p.dead = True
            return
        p.y = 0.0
        if p.vy < 0.0:
            p.vy = 0.0
        if g > 0:
            p.on_ground = True
    if mode in CEIL_MODES and p.y + 1.0 > CEIL:
        p.y = CEIL - 1.0
        if p.vy > 0.0:
            p.vy = 0.0
        if g < 0:
            p.on_ground = True
    for b in near:
        if b.t != "block":
            continue
        if p.x + 1.0 > b.x and p.x < b.x2 and p.y + 1.0 > b.y and p.y < b.y2:
            snap = 0.3 + abs(p.vy) * dt
            if p.vy <= 0.0 and p.y >= b.y2 - snap:
                if g < 0 and headbutt:
                    p.dead = True
                    return
                p.y = b.y2
                p.vy = 0.0
                if g > 0:
                    p.on_ground = True
            elif p.vy >= 0.0 and p.y + 1.0 <= b.y + snap:
                if g > 0 and headbutt:
                    p.dead = True
                    return
                p.y = b.y - 1.0
                p.vy = 0.0
                if g < 0:
                    p.on_ground = True
            else:
                p.dead = True
                return

    # Pads, portals, coins.
    px0, px1, py0, py1 = p.x, p.x + 1.0, p.y, p.y + 1.0
    for o in near:
        t = o.t
        if t in PADS:
            if (p.used >> o.id) & 1:
                continue
            if o.flip:
                hit = _overlap(px0, px1, py0, py1, o.x, o.x + 1.0, o.y + 0.6, o.y + 1.0)
            else:
                hit = _overlap(px0, px1, py0, py1, o.x, o.x + 1.0, o.y, o.y + 0.4)
            if hit:
                p.used |= 1 << o.id
                _apply_pad(p, o)
                p.events.append("pad")
        elif t in PORTALS:
            if (p.used >> o.id) & 1:
                continue
            if _overlap(px0, px1, py0, py1, o.x, o.x2, o.y, o.y2):
                p.used |= 1 << o.id
                _apply_portal(p, o)
        elif t == "coin":
            if _overlap(px0, px1, py0, py1, o.x + 0.1, o.x + 0.9, o.y + 0.1, o.y + 0.9):
                idx = int(o.r)
                if not (p.coins >> idx) & 1:
                    p.coins |= 1 << idx
                    p.events.append("coin")

    # Hazards use a slightly smaller player box.
    hx0, hx1, hy0, hy1 = p.x + 0.1, p.x + 0.9, p.y + 0.1, p.y + 0.9
    for o in near:
        t = o.t
        if t in SPIKE_BOX:
            bx = SPIKE_BOX[t]
            if _overlap(hx0, hx1, hy0, hy1, o.x + bx[0], o.x + bx[1], o.y + bx[2], o.y + bx[3]):
                p.dead = True
                return
        elif t == "saw":
            cx = min(max(o.x, hx0), hx1)
            cy = min(max(o.y, hy0), hy1)
            dx = o.x - cx
            dy = o.y - cy
            rr = o.r * 0.8
            if dx * dx + dy * dy < rr * rr:
                p.dead = True
                return

    if not held:
        p.buffered = False
    if p.y > 40.0 or p.y < -5.0:
        p.dead = True
        return
    if p.x >= lvl.length:
        p.won = True
