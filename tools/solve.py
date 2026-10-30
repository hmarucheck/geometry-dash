#!/usr/bin/env python3
"""Beam-search bot that proves every level can be completed by a human.

The bot plays two copies of the player at once: A gets the bot's inputs on
time, B gets the exact same inputs a few frames late (the level's
"botDelay"). A path only counts if both survive, so every jump, flip and
flap has a timing window of at least that many frames - no frame-perfect
inputs anywhere.

Usage:
    python3 tools/solve.py              # verify every level in levels/levels.json
    python3 tools/solve.py 3            # verify only level index 3
    python3 tools/solve.py --coins      # also prove every secret coin is reachable

Solutions are written to tools/solutions/<index>.json so that
tools/check_parity.js can replay them through the JavaScript engine.
"""

import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))

from neonpulse.physics import Level, Player, step  # noqa: E402

EVERY = 2  # physics steps per decision (60 decisions per second)


def _key(n):
    a, b = n[0], n[1]
    return (round(a.y * 10), round(a.vy * 1.2), round(b.y * 10), round(b.vy * 1.2),
            a.g, b.g, a.mode, b.mode, a.on_ground, b.on_ground, a.buffered, n[2],
            a.used, b.used, a.coins & b.coins, a.boost > 0, b.boost > 0, a.speed)


def _calm(n):
    """A state a real player would plausibly be in: on-time and late copies in step."""
    a, b = n[0], n[1]
    if a.mode != b.mode or a.g != b.g:
        return False
    if a.mode in ("rocket", "dart", "saucer"):
        return abs(a.y - b.y) < 0.6
    return a.on_ground and b.on_ground and abs(a.y - b.y) < 0.01


class Search:
    """Incremental robust beam search.

    Nodes are (A, B, history, parent, held, lineages). relabel() gives every
    frontier state its own lineage bit. When two states merge (same key) their
    lineage bits are combined, and pruning keeps as many lineages covered as
    it can, so lineages_alive() honestly says what share of the states at the
    last relabel could get through.
    """

    def __init__(self, delay, mode="cube", speed=1, beam=350, seed=1234):
        self.delay = delay
        self.mask = (1 << (delay + 2)) - 1
        self.beam = beam
        self.rng = random.Random(seed)
        a = Player(mode, speed)
        self.frontier = [(a, a.clone(), 0, None, False, 1)]
        self.lineages = 1
        self.calm = 1
        self.won = None
        self.furthest = 0.0

    def snapshot(self):
        return (list(self.frontier), self.won, self.furthest, self.rng.getstate(), self.lineages, self.calm)

    def restore(self, snap):
        self.frontier, self.won, self.furthest = list(snap[0]), snap[1], snap[2]
        self.rng.setstate(snap[3])
        self.lineages = snap[4]
        self.calm = snap[5]

    def relabel(self):
        self.frontier = [n[:5] + (1 << i,) for i, n in enumerate(self.frontier)]
        self.lineages = max(1, len(self.frontier))
        self.calm = 0
        for n in self.frontier:
            if _calm(n):
                self.calm |= n[5]
        if not self.calm:
            self.calm = (1 << self.lineages) - 1

    def lineages_alive(self):
        """Share of the calm states at the last relabel that still have a descendant."""
        m = 0
        for n in self.frontier:
            m |= n[5]
        return bin(m & self.calm).count("1") / bin(self.calm).count("1")

    def _prune(self, nodes):
        """Keep calm states first (where real players actually are), then cover
        as many calm lineages as possible, then fill up at random."""
        nodes = list(nodes)
        self.rng.shuffle(nodes)
        calm = [n for n in nodes if _calm(n)][:self.beam // 2]
        taken = {id(n) for n in calm}
        out = list(calm)
        covered = ~self.calm
        for n in out:
            covered |= n[5]
        rest = []
        for n in nodes:
            if id(n) in taken:
                continue
            if n[5] & ~covered and len(out) < self.beam:
                covered |= n[5]
                out.append(n)
            else:
                rest.append(n)
        out.extend(rest[:self.beam - len(out)])
        return out

    def run(self, lvl, until_x, need_coin=None, coin_deadline=None, boundaries=None):
        D = self.delay
        frontier = self.frontier
        bi = 0
        while frontier and frontier[0][0].x < until_x:
            if boundaries is not None and bi < len(boundaries) and frontier[0][0].x >= boundaries[bi]:
                while bi < len(boundaries) and frontier[0][0].x >= boundaries[bi]:
                    bi += 1
                self.frontier = frontier
                self.relabel()
                frontier = self.frontier
            nxt = {}
            for node in frontier:
                a, b, hist, lin = node[0], node[1], node[2], node[5]
                for held in (False, True):
                    h2 = ((hist << 1) | held) & self.mask
                    qa = a.clone()
                    qb = b.clone()
                    pa = held and not (hist & 1)
                    hb = bool((h2 >> D) & 1)
                    pb = hb and not ((h2 >> (D + 1)) & 1)
                    for i in range(EVERY):
                        step(qa, lvl, held, pa and i == 0)
                        step(qb, lvl, hb, pb and i == 0)
                    if qa.dead or qb.dead:
                        self.furthest = max(self.furthest, qa.x)
                        continue
                    if need_coin is not None and qa.x > coin_deadline \
                            and not ((qa.coins & qb.coins) >> need_coin) & 1:
                        continue
                    child = (qa, qb, h2, node, held, lin)
                    if qa.won and qb.won:
                        self.won = child
                        self.frontier = [child]
                        return True
                    k = _key(child)
                    old = nxt.get(k)
                    if old is None:
                        nxt[k] = child
                    elif lin & ~old[5]:
                        nxt[k] = old[:5] + (old[5] | lin,)
            frontier = list(nxt.values())
            if len(frontier) > self.beam:
                frontier = self._prune(frontier)
        self.frontier = frontier
        return bool(frontier)

    def inputs(self):
        node = self.won or (self.frontier[0] if self.frontier else None)
        out = []
        while node is not None and node[3] is not None:
            out.append(1 if node[4] else 0)
            node = node[3]
        out.reverse()
        return out


def solve(data, need_coin=None):
    """Replays the builder's search on the finished level (same segment
    boundaries, same pruning), optionally requiring one coin."""
    lvl = Level(data)
    s = Search(data.get("botDelay", 3), data.get("startMode", "cube"), data.get("startSpeed", 1))
    deadline = None
    if need_coin is not None:
        deadline = lvl.coins[need_coin].x + 1.5
    s.run(lvl, 1e9, need_coin, deadline, boundaries=data.get("segments", [0.0]))
    return (s.inputs() if s.won else None), s.furthest


def replay(data, inputs):
    lvl = Level(data)
    p = Player(data.get("startMode", "cube"), data.get("startSpeed", 1))
    prev = 0
    for v in inputs:
        h = v == 1
        for i in range(EVERY):
            step(p, lvl, h, h and not prev and i == 0)
            if p.dead or p.won:
                return p
        prev = v
    return p


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    path = os.path.join(HERE, "..", "levels", "levels.json")
    with open(path) as f:
        levels = json.load(f)["levels"]
    out_dir = os.path.join(HERE, "solutions")
    os.makedirs(out_dir, exist_ok=True)
    idxs = [int(a) for a in args] if args else range(len(levels))
    failed = False
    for i in idxs:
        data = levels[i]
        t0 = time.time()
        inputs, furthest = solve(data)
        dt = time.time() - t0
        if inputs is None:
            failed = True
            print(f"[{i}] {data['name']}: UNSOLVED, furthest x={furthest:.1f} / {data['length']} ({dt:.1f}s)")
            continue
        p = replay(data, inputs)
        with open(os.path.join(out_dir, f"{i}.json"), "w") as f:
            json.dump({"level": i, "every": EVERY, "inputs": inputs,
                       "final": {"x": p.x, "y": p.y, "vy": p.vy, "won": p.won}}, f)
        print(f"[{i}] {data['name']}: solved, even with inputs {data.get('botDelay')} frames late "
              f"({len(inputs) / 60:.1f}s of play, search {dt:.1f}s)", flush=True)
        if "--coins" in flags:
            for c in range(len(Level(data).coins)):
                ci, _ = solve(data, need_coin=c)
                print(f"      coin {c + 1}: {'reachable' if ci else 'NOT REACHABLE'}", flush=True)
                failed = failed or ci is None
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
