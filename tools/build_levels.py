#!/usr/bin/env python3
"""Builds levels/levels.json and web/js/levels.js.

Levels are grown one obstacle pattern at a time from a seeded random
generator, so the output is identical on every run. After each pattern is
placed, the robust bot from solve.py plays it (with on-time and late
inputs). Patterns it cannot pass are thrown away and rerolled, so every
level is guaranteed to be beatable without frame-perfect timing.

    python3 tools/build_levels.py          # build all levels (uses all CPU cores)
    python3 tools/solve.py --coins         # independent re-check of the result
    node tools/check_parity.js             # check the JS engine agrees
"""

import json
import multiprocessing
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "python"))

from compose import compose, compose_loop  # noqa: E402
from neonpulse.physics import SPEEDS, Level  # noqa: E402
from solve import EVERY, Search, route_coins, solve  # noqa: E402
from neonpulse.physics import Player, step  # noqa: E402

GROUND_MODES = ("cube", "mech")
CORRIDOR_MODES = ("rocket", "ball", "saucer", "dart", "crawler")
BALL_TOP = 5.0
# A pattern is kept only if this share of the bot's incoming states can get
# through it, so nothing depends on one lucky approach.
MIN_PASS_RATIO = 0.25
# Flying forms are steered constantly, and many of the bot's states are at
# heights or speeds no player would choose, so a lower share is enough there.
MIN_PASS_RATIO_FLYING = 0.08
MIN_COIN_RATIO = 0.08
# Each pattern is judged from the states the bot is in about half a second of
# travel before it (roughly human reaction time). This must stay over ~2.5
# blocks so the next pattern's objects can't have mattered yet, which keeps
# solve.py's replay exact.
REACTION_TIME = 0.55
# Extra blocks of space before each pattern (times speed) for forms whose
# moves need a long run-up, since players see obstacles well ahead.
LEAD_IN = {"mech": 3.0, "dart": 4.0, "rocket": 2.0, "saucer": 1.5}


class Builder:
    def __init__(self, seed, diff, speed, delay):
        self.rng = random.Random(seed)
        self.seed = seed
        self.diff = diff
        self.objs = []
        self.colors = []
        self.x = 22.0
        self.speed = speed
        self.mode = "cube"
        self.coin_count = 0
        self.want_coin = False
        self.easy_coin = False
        self.time = 22.0 / SPEEDS[speed]
        self.side = 0  # ball/crawler: which side the next hazard goes on
        self.search = Search(delay, "cube", speed)
        self.segments = [0.0]
        self.history = []  # state before each kept placement, for backtracking
        self.force = []  # cube patterns that must appear in this level
        self.picked = None
        self.rejected = 0
        self.stats = {}  # mode -> [attempts, accepted, gave up]

    # --- low level -------------------------------------------------------
    def add(self, t, x, y, **kw):
        d = {"t": t, "x": round(x, 3), "y": round(y, 3)}
        d.update(kw)
        self.objs.append(d)

    def block(self, x, y, w=1, h=1):
        self.add("block", x, y, w=round(w, 3), h=round(h, 3))

    def spikes(self, x, n=1, y=0, t="spike"):
        for i in range(n):
            self.add(t, x + i, y)

    def coin(self, x, y):
        """Coins must be the last object a pattern adds (see place())."""
        if self.want_coin:
            self.add("coin", x, y, r=self.coin_count)
            self.coin_count += 1

    @property
    def k(self):
        return SPEEDS[self.speed] / SPEEDS[1]

    def advance(self, to):
        self.time += (to - self.x) / SPEEDS[self.speed]
        self.x = to

    def gap(self, scale=1.0):
        base = [8.0, 7.0, 6.0, 5.2, 4.6, 4.2][self.diff]
        self.advance(self.x + (base + self.rng.random() * 2.0) * self.k * scale)

    # --- verification ----------------------------------------------------
    def _state(self):
        return (len(self.objs), self.x, self.time, self.coin_count, self.mode, self.speed,
                self.side, self.search.snapshot(), len(self.segments))

    def _restore(self, st):
        del self.objs[st[0]:]
        self.x, self.time, self.coin_count, self.mode, self.speed, self.side = st[1:7]
        self.search.restore(st[7])
        del self.segments[st[8]:]

    def margin(self):
        return max(2.5, REACTION_TIME * SPEEDS[self.speed])

    def _level(self):
        return Level({"name": "", "length": 1e9, "objects": self.objs})

    def place(self, fn, gap_scale=1.0, min_ratio=None):
        """Add a pattern, then keep it only if the bot can get through it."""
        if min_ratio is None:
            min_ratio = MIN_PASS_RATIO_FLYING if self.mode in ("rocket", "saucer", "dart") else MIN_PASS_RATIO
        self.search.relabel()
        st = self._state()
        self.picked = None
        fn()
        self.gap(gap_scale)
        until = self.x - self.margin()
        if self.coin_count > st[3]:
            # Prove the coin can be collected (and survived) before keeping it.
            probe = Search(self.search.delay)
            probe.restore(st[7])
            coin = self.objs[-1]
            ok = probe.run(self._level(), until, need_coin=coin["r"], coin_deadline=coin["x"] + 1.5)
            if not ok or probe.lineages_alive() < MIN_COIN_RATIO:
                self.objs.pop()
                self.coin_count -= 1
        if self.search.run(self._level(), until) and self.search.lineages_alive() >= min_ratio:
            if self.coin_count > st[3]:
                self.want_coin = False
            self.segments.append(until)
            self.history.append(st)
            if self.picked in self.force:
                self.force.remove(self.picked)
            return True
        self._restore(st)
        self.rejected += 1
        return False

    def place_any(self, fn, gap_scale=1.0, tries=8):
        st = self.stats.setdefault(self.mode, [0, 0, 0])
        for _ in range(tries):
            st[0] += 1
            if self.place(fn, gap_scale):
                st[1] += 1
                return
        st[2] += 1
        # Nothing fits here: leave some empty room, which is always passable.
        for _ in range(8):
            if self.place(lambda: self.advance(self.x + 4 * self.k), gap_scale, 0.0):
                return
            self._backtrack()
        raise RuntimeError("dead end at x=%.1f (seed %s)" % (self.x, self.seed))

    def _backtrack(self):
        """Undo the last kept placement (its unchecked tail left no way through)."""
        if self.history:
            self._restore(self.history.pop())

    # --- transitions -----------------------------------------------------
    def to_mode(self, mode):
        def fn():
            x = self.x
            tall = self.mode not in GROUND_MODES
            if self.mode in CORRIDOR_MODES:
                self.add("p_gdown", x, 0, h=9)
                x += 1.5
            self.add("p_" + mode, x, 0, h=9 if tall else 5)
            self.mode = mode
            self.side = 0
            run = (9.0 if tall and mode in GROUND_MODES else 6.0) * self.k
            if mode == "ball":
                # Leave time to drop below the lowered ceiling first.
                run = (11.0 if tall else 6.0) * self.k
                start = x + (9.0 if tall else 2.0) * self.k
                self.block(start, BALL_TOP, x + run - start, 9 - BALL_TOP)
            self.advance(x + run)
        self._place_required(fn, "portal")

    def set_speed(self, s):
        def fn():
            tall = self.mode not in GROUND_MODES
            self.add("p_s%d" % s, self.x, 0, h=9 if tall else 5)
            self.advance(self.x + 3)
            self.speed = s
            self.advance(self.x + 3 * self.k)
        self._place_required(fn, "speed portal")

    def _place_required(self, fn, what):
        for attempt in range(6):
            if self.place(fn, 0.0, 0.0):
                return
            if attempt >= 1:
                # The pattern before this one leaves no way through: swap it
                # for empty space and try again.
                self._backtrack()
            self.place(lambda: self.advance(self.x + 3 * self.k), 0.0, 0.0)
        raise RuntimeError("%s failed at x=%.1f (seed %s)" % (what, self.x, self.seed))

    def color(self, bg, ground):
        self.colors.append([round(self.x - 10, 2), bg, ground])

    # --- cube ------------------------------------------------------------
    def cube_pattern(self):
        r = self.rng
        d = self.diff
        x = self.x
        k = self.k
        pool = ["spikes", "spikes", "block", "islands", "padjump"]
        if d >= 1:
            pool += ["stairs", "orbpit", "blockspike", "platpad", "saw", "pinkpad", "redorb"]
        if d >= 2:
            pool += ["grav", "pinkchain", "tower", "islands", "blueorb", "redpad", "bluepad"]
        if d >= 3:
            pool += ["bluepad", "spikes", "orbpit", "greenorb", "blackorb"]
        p = r.choice(pool)
        if self.force:
            p = self.force[0]  # a showcase pattern this level must contain
        self.picked = p
        if self.want_coin and p not in ("spikes", "platpad"):
            p = r.choice(["spikes", "platpad"])
        if p == "spikes":
            n = r.choice([1, 1, 2] if d == 0 else [1, 2, 2, 3] if d < 3 else [2, 3, 3])
            self.spikes(x, n)
            self.coin(x + n / 2 - 0.5, 1.4 if self.easy_coin else 2.3)
            end = x + n
        elif p == "block":
            self.block(x, 0)
            if d >= 1:
                self.spikes(x + 1, 1, t="spike_s")
            end = x + 1 + (d >= 1)
        elif p == "islands":
            n = r.randint(2, 3 + (d >= 2))
            w = max(3 if d < 2 else 2, round(2.5 * k))
            g = max(2 if d < 3 else 3, round(2.5 * k))
            cx = x
            for i in range(n):
                self.block(cx, 0, w, 1)
                if i < n - 1:
                    self.spikes(cx + w, g)
                cx += w + g
            end = cx - g
        elif p == "padjump":
            self.add("pad_y", x, 0)
            self.spikes(x + 1, 3 + (d >= 2))
            end = x + 6
        elif p == "stairs":
            steps = 2 + (d >= 2)
            sw = max(3, round(3 * k + 0.4))
            for i in range(steps):
                self.block(x + i * sw, 0, sw, i + 1)
            if d >= 2:
                self.spikes(x + steps * sw - 1, 1, y=steps, t="spike_s")
            end = x + steps * sw + 2 * k
        elif p == "orbpit":
            self.spikes(x, 6)
            self.add("orb_y", x + 2.0 * k, 2.0)
            end = x + 6
        elif p == "blockspike":
            self.block(x, 0, 5, 1)
            self.spikes(x + 2.5, 1, y=1)
            end = x + 5
        elif p == "platpad":
            self.add("pad_y", x, 0)
            self.block(x + 3, 2, 7, 1)
            self.spikes(x + 2, 8)
            self.coin(x + 5.5, 5.2)
            end = x + 10
        elif p == "saw":
            self.add("saw", x + 1, 0, r=1.2)
            end = x + 2.2
        elif p == "grav":
            L = int(14 * k) + (4 if d >= 3 else 0)
            flip = r.random() < 0.4
            self.add("p_gflip" if flip else "p_gup", x, 0, h=4)
            self.block(x + 1, 6, L, 1)
            sx = x + 5 * k
            while sx < x + L - 3 * k:
                n = r.choice([1, 1, 2]) if d < 4 else r.choice([1, 2, 3])
                self.spikes(sx, n, y=5, t="spike_d")
                sx += n + 5.5 * k
            self.add("p_gflip" if flip else "p_gdown", x + L + 0.5, 3, h=4)
            end = x + L + 1.5 + 2 * k
        elif p == "pinkchain":
            self.spikes(x, 9)
            self.add("orb_p", x + 2.2 * k, 2.0)
            self.add("orb_y", x + 5.4 * k, 2.0)
            end = x + 9
        elif p == "tower":
            tw = max(2, round(2 * k))
            for i in range(3):
                self.block(x + i * tw, 0, tw, i + 1)
            end = x + 3 * tw + 3 * k
        elif p == "pinkpad":
            self.add("pad_p", x, 0)
            self.spikes(x + 1.2, 1)
            self.block(x + 4, 0, 3, 1)
            end = x + 7
        elif p == "redorb":
            self.spikes(x, 8)
            self.add("orb_r", x + 2.0 * k, 2.0)
            end = x + 8
        elif p == "redpad":
            self.add("pad_r", x, 0)
            self.spikes(x + 1.5, 6)
            self.block(x + 4, 4.5, 3, 1)
            end = x + 8.5
        elif p == "blueorb":
            # tap the blue orb mid-jump to fall up onto the ceiling run
            L = int(14 * k)
            self.spikes(x, 3)
            self.add("orb_b", x + 1.2 * k, 2.0)
            self.block(x + 1, 6, L, 1)
            self.spikes(x + 3, L - 3)
            sx = x + 7 * k
            while sx < x + L - 3 * k:
                self.spikes(sx, 1, y=5, t="spike_sd")
                sx += 6 * k
            self.add("p_gdown", x + L + 0.5, 3, h=4)
            end = x + L + 1.5 + 2 * k
        elif p == "greenorb":
            # ride the ceiling, then tap the green orb to dive back down
            L = int(12 * k)
            self.add("p_gup", x, 0, h=4)
            self.block(x + 1, 6, L + 6, 1)
            self.add("orb_g", x + L - 1, 4.3)
            self.spikes(x + L + 1, 5, y=5, t="spike_d")
            self.add("p_gdown", x + L + 7, 0, h=9)
            end = x + L + 8 + 2 * k
        elif p == "blackorb":
            # bounce high off a pad, then slam down under the hanging spikes
            self.add("pad_y", x, 0)
            self.add("orb_k", x + 2.5 * k, 3.2)
            self.block(x + 5 * k, 4.2, 4, 3)
            self.spikes(x + 5 * k, 4, y=3.2, t="spike_d")
            end = x + 5 * k + 4
        else:  # bluepad
            L = int(16 * k)
            self.add("pad_b", x, 0)
            self.spikes(x + 1, 3)
            self.block(x + 1, 6, L, 1)
            sx = x + 7 * k
            while sx < x + L - 3 * k:
                self.spikes(sx, r.choice([1, 2]), y=5, t="spike_d")
                sx += 7 * k
            self.add("p_gdown", x + L + 0.5, 3, h=4)
            end = x + L + 1.5 + 2 * k
        self.advance(end)

    # --- rocket ----------------------------------------------------------
    def gate(self, x, center, size, w=2, coin=True):
        lo = center - size / 2
        hi = center + size / 2
        if lo > 0.01:
            self.block(x, 0, w, lo)
        if hi < 8.99:
            self.block(x, hi, w, 9 - hi)
        if coin:
            self.coin(x + w + 1.5 * self.k, 7.4 if center < 4.5 else 0.6)

    def rocket_pattern(self):
        r = self.rng
        d = self.diff
        x = self.x
        size = 4.6 - 0.35 * d
        p = r.choice(["gate", "tunnel", "tunnel", "spikes"])
        if p == "gate" or self.want_coin:
            self.gate(x, r.uniform(2.6, 6.4), size)
            end = x + 2
        elif p == "tunnel":
            n = 3 + d // 2
            c = r.uniform(3, 6)
            for i in range(n):
                self.gate(x + i * 2, c, size + 0.6, coin=False)
                c += r.choice([-1, 1]) * (0.5 + 0.12 * d) * min(self.k, 1.3)
                c = max(2.6, min(6.4, c))
            end = x + n * 2
        else:
            n = 4 + d
            self.spikes(x, n)
            self.spikes(x, n, y=8, t="spike_d")
            self.block(x + n // 2, 0, 1, 2.5)
            self.block(x + n // 2, 6.5, 1, 2.5)
            end = x + n
        self.advance(end)

    # --- saucer ----------------------------------------------------------
    def saucer_pattern(self):
        r = self.rng
        d = self.diff
        x = self.x
        p = r.choice(["gate", "gate", "steps", "spikes"])
        if p == "gate" or self.want_coin:
            self.gate(x, r.uniform(2.8, 6.2), 4.6 - 0.25 * d, w=1)
            end = x + 1
        elif p == "steps":
            h = r.choice([2, 3])
            for i in range(3):
                self.block(x + i * 4 * self.k, 0, 1, h + i)
                self.spikes(x + i * 4 * self.k, 1, y=h + i)
            end = x + 8 * self.k + 1
        else:
            n = 5 + d
            self.spikes(x, n)
            self.add("saw", x + n / 2, 8.4, r=1.3)
            end = x + n
        self.advance(end)

    # --- ball ------------------------------------------------------------
    def ball_pattern(self):
        r = self.rng
        d = self.diff
        start = self.x
        n = r.randint(2, 3 + (d >= 3))
        x = start
        if self.side == 0:
            # floor hazard: be on the ceiling
            if r.random() < 0.5:
                self.spikes(x, n)
            else:
                self.block(x, 0, n, 1)
                self.spikes(x, n, y=1, t="spike_s")
        elif r.random() < 0.6:
            self.spikes(x, n, y=BALL_TOP - 1, t="spike_d")
        else:
            self.block(x, BALL_TOP - 1, n, 1)
            self.spikes(x, n, y=BALL_TOP - 2, t="spike_sd")
        self.side ^= 1
        self.advance(x + n + (6.2 - 0.4 * d) * self.k)
        self.block(start, BALL_TOP, self.x - start, 9 - BALL_TOP)
        self.coin(x + n + 1.6 * self.k, 2.0)

    # --- dart ------------------------------------------------------------
    def dart_pattern(self):
        r = self.rng
        d = self.diff
        x = self.x
        k = self.k
        p = r.choice(["zig", "zig", "tunnel", "spikes"])
        if p == "zig" or self.want_coin:
            a = round(r.uniform(3.0, 5.0), 2)
            s = (7.5 - 0.5 * d) * k
            self.block(x, 0, 1, a)
            self.spikes(x, 1, y=a, t="spike_s")
            b = round(max(2.2, min(8.0, a + 1.6 - 0.3 * d)), 2)
            self.block(x + s, b, 1, 9 - b)
            self.coin(x + s + 1.4 * k, 0.3)
            end = x + s + 1
        elif p == "tunnel":
            n = 6 + d
            lo = r.uniform(1, 3)
            size = 3.6 - 0.2 * d
            for i in range(n):
                self.block(x + i, 0, 1, round(lo, 2))
                self.block(x + i, round(lo + size, 2), 1, round(9 - lo - size, 2))
                lo += r.choice([-1, 1]) * 0.6 * k
                lo = max(0.8, min(4.0, lo))
            end = x + n
        else:
            n = 6 + d
            self.spikes(x, n)
            self.spikes(x, n, y=8, t="spike_d")
            end = x + n
        self.advance(end)

    # --- mech ------------------------------------------------------------
    def mech_pattern(self):
        r = self.rng
        d = self.diff
        x = self.x
        k = self.k
        p = r.choice(["pillar", "pillar", "pit", "steps", "spikepillar"])
        if p == "pillar" or self.want_coin:
            h = r.choice([1, 2, 2, 3]) if d < 3 else r.choice([2, 3])
            self.block(x, 0, 1, h)
            self.coin(x + 0.5, h + 2.2)
            end = x + 1
        elif p == "pit":
            n = r.randint(2, 3 + (d >= 3))
            self.spikes(x, n)
            end = x + n
        elif p == "spikepillar":
            h = r.choice([1, 2])
            self.block(x, 0, 2, h)
            self.spikes(x + 0.5, 1, y=h, t="spike_s")
            end = x + 2
        else:
            sw = max(4, round(4 * k))
            for i in range(3):
                self.block(x + i * sw, 0, sw, i + 1)
            end = x + 3 * sw + 3 * k
        self.advance(end)

    # --- crawler ---------------------------------------------------------
    def crawler_pattern(self):
        r = self.rng
        d = self.diff
        x = self.x
        n = r.randint(3, 5 + d // 2)
        if self.side == 0:
            self.spikes(x, n)
        else:
            self.spikes(x, n, y=8, t="spike_d")
        end = x + n
        if r.random() < 0.3 + 0.1 * d:
            # a block in the middle of the corridor to teleport around
            self.block(x + n + 1.5 * self.k, 3, 2, 3)
            end = x + n + 1.5 * self.k + 2
        self.side ^= 1
        self.advance(end)

    # --- sections --------------------------------------------------------
    def section(self, mode, count, coin_at=None):
        if mode != self.mode:
            self.to_mode(mode)
        fn = {"cube": self.cube_pattern, "rocket": self.rocket_pattern,
              "saucer": self.saucer_pattern, "dart": self.dart_pattern,
              "mech": self.mech_pattern, "ball": self.ball_pattern,
              "crawler": self.crawler_pattern}[mode]
        scale = {"rocket": 0.75, "saucer": 0.75, "dart": 0.75, "ball": 0.0, "crawler": 0.8}.get(mode, 1.0)
        lead = LEAD_IN.get(mode, 0.0)

        def pattern():
            # Forms with long set-up moves get extra room to line up.
            self.advance(self.x + lead * self.k)
            fn()
        target = self.coin_count + 1
        for i in range(count):
            self.want_coin = coin_at is not None and i >= coin_at and self.coin_count < target
            self.place_any(pattern, scale)
        self.want_coin = False

    def finish(self, lvl_length_pad=14):
        if self.mode != "cube":
            self.to_mode("cube")
        self.advance(self.x + lvl_length_pad)
        self.search.relabel()
        if not self.search.run(Level({"name": "", "length": self.x, "objects": self.objs}), 1e9):
            raise RuntimeError("level end unreachable (seed %s)" % self.seed)
        return self.x


DIFFS = ["Easy", "Normal", "Hard", "Harder", "Insane", "Demon"]
# Frames (1/60 s) by which every input may be late and still work.
BOT_DELAY = [6, 5, 4, 4, 3, 3]

LEVELS = [
    {
        "name": "First Light", "diff": 0, "stars": 1, "speed": 1, "seed": 11,
        "music": {"seed": 101, "bpm": 120, "root": 60, "scale": "major", "prog": [0, 4, 5, 3],
                  "lead": "square", "bass": "triangle", "arp": "square", "pad": "saw",
                  "drums": "four", "bassRhythm": "octaves", "cutoff": 2600},
        "colors": [["#1f5bff", "#0c34c9"], ["#7b3cff", "#4b1ccc"], ["#0d9cff", "#0a62d6"]],
        "sections": [("cube", 8, 4), ("rocket", 7, 3), ("cube", 9, 5)],
    },
    {
        "name": "Neon Steps", "diff": 1, "stars": 2, "speed": 1, "seed": 22,
        "music": {"seed": 202, "bpm": 128, "root": 55, "scale": "mixolydian", "prog": [0, 6, 3, 0],
                  "lead": "saw", "bass": "square", "arp": "pulse", "pad": "saw",
                  "drums": "four", "bassRhythm": "eighths", "arpOrder": "updown", "cutoff": 2400},
        "colors": [["#d81bd1", "#8e0f8a"], ["#ff3c7d", "#b3124b"], ["#7a2cff", "#4a11b0"], ["#ff5ad0", "#a01c86"]],
        "sections": [("cube", 9, 5), ("rocket", 7, None), ("cube", 6, None), ("ball", 8, 1), ("cube", 6, 2)],
    },
    {
        "name": "Gravity Well", "diff": 2, "stars": 4, "speed": 1, "seed": 33,
        "music": {"seed": 303, "bpm": 132, "root": 57, "scale": "minor", "prog": [0, 5, 2, 6],
                  "lead": "pulse", "bass": "saw", "arp": "square", "pad": "saw",
                  "drums": "break", "bassRhythm": "sync", "cutoff": 2000},
        "colors": [["#14b84a", "#0b7a2f"], ["#0fb39a", "#077565"], ["#62c214", "#3b7a09"], ["#13a35c", "#086637"]],
        "sections": [("cube", 7, 3), ("ball", 9, 1), ("speed", 0), ("cube", 7, None), ("speed", 1),
                     ("crawler", 9, None), ("cube", 6, None), ("rocket", 5, 2)],
    },
    {
        "name": "Skyline Drift", "diff": 2, "stars": 5, "speed": 1, "seed": 44,
        "music": {"seed": 404, "bpm": 140, "root": 62, "scale": "dorian", "prog": [0, 3, 4, 6],
                  "lead": "triangle", "bass": "saw", "arp": "pulse", "pad": "saw",
                  "drums": "four", "bassRhythm": "offbeat", "arpOrder": "random", "cutoff": 2400},
        "colors": [["#ff7a1a", "#b84a00"], ["#ff4f4f", "#b02424"], ["#ffaa22", "#b86d00"], ["#ff5e8a", "#b0284e"]],
        "sections": [("cube", 6, None), ("saucer", 9, 4), ("speed", 2), ("cube", 7, 2),
                     ("rocket", 8, None), ("saucer", 6, 3), ("cube", 5, None)],
    },
    {
        "name": "Zigzag Rush", "diff": 3, "stars": 6, "speed": 1, "seed": 55, "force": ["greenorb"],
        "music": {"seed": 505, "bpm": 150, "root": 52, "scale": "minor", "prog": [0, 3, 5, 4],
                  "lead": "saw", "bass": "square", "arp": "square", "pad": "saw",
                  "drums": "four", "bassRhythm": "gallop", "cutoff": 2800},
        "colors": [["#00c8e8", "#00809a"], ["#2a7bff", "#1447b3"], ["#00e0b0", "#00916f"], ["#3a5bff", "#1b2fb3"]],
        "sections": [("cube", 6, None), ("dart", 9, 4), ("speed", 2), ("cube", 6, None),
                     ("dart", 9, 6), ("speed", 1), ("cube", 5, 3), ("rocket", 5, None)],
    },
    {
        "name": "Iron Stride", "diff": 3, "stars": 7, "speed": 1, "seed": 66,
        "music": {"seed": 606, "bpm": 145, "root": 49, "scale": "harmonic", "prog": [0, 5, 3, 4],
                  "lead": "square", "bass": "saw", "arp": "pulse", "pad": "saw",
                  "drums": "break", "bassRhythm": "wobble", "cutoff": 1800},
        "colors": [["#d0202a", "#801018"], ["#9a1f3c", "#5a0f22"], ["#d64a16", "#86290a"], ["#b0122e", "#650818"]],
        "sections": [("mech", 9, 3), ("crawler", 9, None), ("ball", 8, None), ("mech", 7, 4),
                     ("speed", 2), ("rocket", 7, 2), ("cube", 5, None)],
    },
    {
        "name": "Crystal Cavern", "diff": 4, "stars": 9, "speed": 2, "seed": 77,
        "music": {"seed": 707, "bpm": 165, "root": 54, "scale": "lydian", "prog": [0, 1, 4, 5],
                  "lead": "pulse", "bass": "saw", "arp": "triangle", "pad": "saw",
                  "drums": "dnb", "bassRhythm": "sync", "arpOrder": "updown", "cutoff": 3000},
        "colors": [["#18c6c0", "#0a7470"], ["#8a3cff", "#5216b5"], ["#2096ff", "#0c5ab0"], ["#d43cff", "#7e16a8"]],
        "sections": [("cube", 6, None), ("rocket", 6, 3), ("saucer", 6, None), ("dart", 6, None),
                     ("ball", 7, None), ("mech", 6, 2), ("crawler", 7, None), ("speed", 3), ("cube", 6, 3)],
    },
    {
        "name": "Final Voltage", "diff": 5, "stars": 10, "speed": 3, "seed": 88, "force": ["greenorb"],
        "music": {"seed": 808, "bpm": 174, "root": 52, "scale": "phrygian", "prog": [0, 1, 0, 6],
                  "lead": "saw", "bass": "saw", "arp": "square", "pad": "saw",
                  "drums": "dnb", "bassRhythm": "gallop", "cutoff": 3200},
        "colors": [["#2a0a10", "#160307"], ["#3a0014", "#1e000a"], ["#1a1a2e", "#0c0c18"], ["#40000a", "#200005"]],
        "sections": [("cube", 6, None), ("dart", 6, 3), ("rocket", 6, None), ("ball", 7, None),
                     ("saucer", 6, 2), ("crawler", 7, None), ("mech", 6, None), ("speed", 4),
                     ("dart", 6, None), ("cube", 6, 4)],
    },
]

MENU_SONG = {"seed": 9001, "bpm": 110, "root": 57, "scale": "dorian", "prog": [0, 3, 6, 4],
             "lead": "triangle", "arp": "triangle", "cutoff": 1600}
PRACTICE_SONG = {"seed": 9002, "bpm": 92, "root": 60, "scale": "major", "prog": [0, 5, 3, 4],
                 "lead": "triangle", "arp": "triangle", "cutoff": 1200}


def trajectory(data, inputs, delay):
    """Positions of the on-time (A) and late (B) players along the bot's winning run."""
    lvl = Level(data)
    a = Player(data["startMode"], data["startSpeed"])
    b = a.clone()
    hist = 0
    mask = (1 << (delay + 2)) - 1
    out = []
    for v in inputs:
        held = v == 1
        h2 = ((hist << 1) | held) & mask
        hb = bool((h2 >> delay) & 1)
        for i in range(EVERY):
            step(a, lvl, held, held and not (hist & 1) and i == 0)
            step(b, lvl, hb, hb and not ((h2 >> (delay + 1)) & 1) and i == 0)
        hist = h2
        out.append((a.x, a.y, b.y, a.on_ground))
    return out


def fix_coins(data, inputs):
    """Move any coin the full-level check can't collect onto a proven path nearby,
    at the top of a jump where the on-time and late players agree."""
    path = trajectory(data, inputs, data["botDelay"])
    coins = [o for o in data["objects"] if o["t"] == "coin"]
    on_route = route_coins(data, inputs)
    moved = 0
    for c in coins:
        idx = int(c["r"])
        if (on_route >> idx) & 1 or solve(data, need_coin=idx)[0]:
            continue
        near = [p for p in path if abs(p[0] - c["x"]) < 8 and abs(p[1] - p[2]) < 0.25]
        if not near:
            near = [p for p in path if abs(p[1] - p[2]) < 0.25]
        best = max(near, key=lambda p: (not p[3], p[1], -abs(p[0] - c["x"])))
        c["x"], c["y"] = round(best[0], 3), round((best[1] + best[2]) / 2, 3)
        moved += 1
    return moved


def build_level(spec):
    delay = BOT_DELAY[spec["diff"]]
    b = Builder(spec["seed"], spec["diff"], spec["speed"], delay)
    b.force = list(spec.get("force", []))
    for i, sec in enumerate(spec["sections"]):
        if sec[0] == "speed":
            b.set_speed(sec[1])
            continue
        c = spec["colors"][i % len(spec["colors"])]
        b.color(c[0], c[1])
        mode, count, coin_at = sec
        b.section(mode, count, coin_at)
        print(f"  {spec['name']}: {mode} section done at x={b.x:.0f} ({b.rejected} rerolls so far)",
              file=sys.stderr, flush=True)
    # Any coin that could not be placed safely goes over the final spikes.
    if b.coin_count < 3 and b.mode != "cube":
        b.to_mode("cube")
    tries = 0
    while b.coin_count < 3:
        b.want_coin = True
        tries += 1
        if tries > 6:
            b.easy_coin = True  # put it right in the normal jump path
        b.place_any(b.cube_pattern)
    b.easy_coin = False
    length = b.finish()
    print(f"  {spec['name']} pattern stats (tries, kept, gave up): {b.stats}", file=sys.stderr, flush=True)
    seconds = b.time + 3
    data = {
        "name": spec["name"],
        "difficulty": DIFFS[spec["diff"]],
        "diff": spec["diff"],
        "stars": spec["stars"],
        "botDelay": delay,
        "startMode": "cube",
        "startSpeed": spec["speed"],
        "length": length,
        "seconds": round(seconds, 1),
        "colors": b.colors,
        "segments": b.segments,
        "objects": b.objs,
        "song": compose(spec["music"], seconds),
    }
    moved = fix_coins(data, b.search.inputs())
    print(f"  {spec['name']}: moved {moved} coin(s) onto a proven path", file=sys.stderr, flush=True)
    return data, b.rejected


def main():
    only = [int(a) for a in sys.argv[1:]]
    root = os.path.join(HERE, "..")
    path = os.path.join(root, "levels", "levels.json")
    specs = LEVELS if not only else [LEVELS[i] for i in only]
    with multiprocessing.Pool(min(len(specs), os.cpu_count() or 1)) as pool:
        built = pool.map(build_level, specs)
    if only and os.path.exists(path):
        with open(path) as f:
            levels = json.load(f)["levels"]
        for i, (lv, _) in zip(only, built):
            levels[i] = lv
    else:
        levels = [lv for lv, _ in built]
    out = {
        "version": 1,
        "levels": levels,
        "songs": {
            "menu": compose_loop(MENU_SONG, "menu"),
            "practice": compose_loop(PRACTICE_SONG, "practice"),
        },
    }
    text = json.dumps(out, separators=(",", ":"))
    with open(path, "w") as f:
        f.write(text)
    with open(os.path.join(root, "web", "js", "levels.js"), "w") as f:
        f.write("// Generated by tools/build_levels.py - do not edit by hand.\n")
        f.write("window.GAME_DATA = " + text + ";\n")
    for lv, rej in built:
        print(f"{lv['name']:16s} {lv['difficulty']:7s} length={lv['length']:7.1f} "
              f"time={lv['seconds']:5.1f}s objects={len(lv['objects']):4d} rerolled={rej}")


if __name__ == "__main__":
    main()
