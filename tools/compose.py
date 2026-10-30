"""Procedural song composer.

Every level has a small "song spec" (tempo, key, scale, chord progression,
instrument choices). compose() turns it into note patterns plus an
arrangement. The result is stored in levels.json and played by the synths
in web/js/audio.js and python/neonpulse/synth.py, so both versions of the
game play exactly the same notes.
"""

import random

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "harmonic": [0, 2, 3, 5, 7, 8, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
}

LEAD_RHYTHMS = [
    [(0, 1), (1, 0.5), (1.5, 0.5), (2, 1.5), (3.5, 0.5)],
    [(0, 0.5), (0.5, 0.5), (1, 0.5), (1.5, 0.5), (2, 1), (3, 1)],
    [(0, 1.5), (1.5, 1.5), (3, 1)],
    [(0, 0.75), (0.75, 0.75), (1.5, 0.5), (2, 0.75), (2.75, 0.75), (3.5, 0.5)],
    [(0, 2), (2, 0.5), (2.5, 0.5), (3, 1)],
    [(0.5, 0.5), (1, 0.5), (1.5, 1), (2.5, 0.5), (3, 0.5), (3.5, 0.5)],
    [(0, 0.25), (0.25, 0.25), (0.5, 0.5), (1, 1), (2, 0.25), (2.25, 0.25), (2.5, 0.5), (3, 1)],
]

BASS_RHYTHMS = {
    "eighths": [(i * 0.5, 0.45, 0) for i in range(8)],
    "octaves": [(i * 0.5, 0.45, 12 if i % 2 else 0) for i in range(8)],
    "offbeat": [(i + 0.5, 0.45, 0) for i in range(4)],
    "gallop": [(0, 0.5, 0), (0.75, 0.25, 0), (1, 0.5, 12), (1.5, 0.5, 0), (2, 0.5, 0),
               (2.75, 0.25, 0), (3, 0.5, 7), (3.5, 0.5, 12)],
    "sync": [(0, 0.7, 0), (0.75, 0.5, 0), (1.5, 0.5, 12), (2.5, 0.5, 0), (3, 0.5, 7), (3.5, 0.4, 0)],
    "wobble": [(0, 0.95, 0), (1, 0.45, 0), (1.5, 0.95, 12), (2.5, 0.45, 0), (3, 0.95, 7)],
}


def _degree_to_midi(root, scale, degree, octave=0):
    n = len(scale)
    o, d = divmod(degree, n)
    return root + scale[d] + 12 * (o + octave)


def _chord(root, scale, degree):
    return [_degree_to_midi(root, scale, degree + k) for k in (0, 2, 4)]


def _drums(style, variant):
    ev = []
    if style == "half":
        kicks, snares, hat_step = [0, 2.5], [2], 0.5
    elif style == "break":
        kicks, snares, hat_step = [0, 1.75, 2.5], [1, 3], 0.25
    elif style == "dnb":
        kicks, snares, hat_step = [0, 1.25, 2.5], [1, 3], 0.25
    else:
        kicks, snares, hat_step = [0, 1, 2, 3], [1, 3], 0.5
    if variant == "intro":
        for k in kicks:
            ev.append([k, 0.25, "kick", 0, 0.7])
        for i in range(4):
            ev.append([i + 0.5, 0.1, "hat", 0, 0.25])
        return ev
    for k in kicks:
        ev.append([k, 0.25, "kick", 0, 1.0])
    for s in snares:
        if variant == "fill" and s >= 3:
            continue
        ev.append([s, 0.25, "snare", 0, 0.8])
        if style == "four":
            ev.append([s, 0.25, "clap", 0, 0.5])
    t = 0.0
    while t < 4:
        if style == "four" and t % 1 == 0:
            t += hat_step
            continue
        if variant == "fill" and t >= 3:
            break
        v = 0.35 if (t * 2) % 2 == 1 else 0.22
        ev.append([t, 0.1, "hat", 0, v])
        t += hat_step
    if variant == "fill":
        for i in range(4):
            ev.append([3 + i * 0.25, 0.2, "snare", 0, 0.4 + i * 0.15])
    else:
        ev.append([3.5, 0.4, "ohat", 0, 0.25])
    return ev


def _melody(rng, root, scale, prog, bars=4):
    """Generate a lead phrase: one pattern per bar, following the chords."""
    n = len(scale)
    motif_a = rng.choice(LEAD_RHYTHMS)
    motif_b = rng.choice(LEAD_RHYTHMS)
    pos = 7 + rng.randint(0, 4)  # scale-degree position around the upper octave
    out = []
    for b in range(bars):
        rhythm = motif_a if b % 2 == 0 else motif_b
        deg = prog[b % len(prog)]
        chord_degs = {(deg + k) % n for k in (0, 2, 4)}
        ev = []
        for j, (t, d) in enumerate(rhythm):
            strong = t in (0, 2)
            step = rng.choice([-2, -1, -1, 1, 1, 2, 0, 3, -3])
            pos += step
            if pos < 5:
                pos += 3
            if pos > 15:
                pos -= 3
            if strong:
                # nudge to the nearest chord tone
                for delta in (0, 1, -1, 2, -2):
                    if (pos + delta) % n in chord_degs:
                        pos += delta
                        break
            if b == bars - 1 and j == len(rhythm) - 1:
                pos = 7 + (deg % n)
            midi = _degree_to_midi(root, scale, pos)
            ev.append([t, d * 0.9, "lead", midi, 0.55 if strong else 0.45])
        out.append(ev)
    return out


def compose(spec, seconds):
    rng = random.Random(spec["seed"])
    root = spec["root"]
    scale = SCALES[spec["scale"]]
    prog = spec["prog"]
    bpm = spec["bpm"]
    drums = spec.get("drums", "four")
    bass_rh = BASS_RHYTHMS[spec.get("bassRhythm", "octaves")]
    patterns = {}
    patterns["d_main"] = _drums(drums, "main")
    patterns["d_fill"] = _drums(drums, "fill")
    patterns["d_intro"] = _drums(drums, "intro")
    patterns["crash"] = [[0, 2, "crash", 0, 0.5]]
    for i, deg in enumerate(prog):
        ch = _chord(root, scale, deg)
        bass_root = ch[0] - 24
        patterns[f"b{i}"] = [[t, d, "bass", bass_root + o, 0.8] for (t, d, o) in bass_rh]
        arp_notes = ch + [c + 12 for c in ch]
        order = spec.get("arpOrder", "up")
        if order == "updown":
            arp_notes = arp_notes + arp_notes[-2:0:-1]
        elif order == "random":
            arp_notes = [rng.choice(arp_notes) for _ in range(8)]
        patterns[f"a{i}"] = [[k * 0.25, 0.2, "arp", arp_notes[k % len(arp_notes)] + 12, 0.3]
                             for k in range(16)]
        patterns[f"p{i}"] = [[0, 3.9, "pad", c, 0.25] for c in ch]
    mel_a = _melody(rng, root, scale, prog)
    mel_b = _melody(rng, root, scale, prog)
    for i in range(4):
        patterns[f"mA{i}"] = mel_a[i]
        patterns[f"mB{i}"] = mel_b[i]

    beats_needed = seconds * bpm / 60.0
    total_bars = int(beats_needed / 4) + 4
    L = len(prog)
    sections = [("A", 8), ("B", 8), ("C", 4), ("D", 8), ("B", 8), ("A", 4), ("D", 8)]
    bars = []
    # two bar intro
    for i in range(2):
        bars.append(["d_intro", f"p{i % L}"] + (["crash"] if i == 0 else []))
    si = 0
    while len(bars) < total_bars:
        name, length = sections[si % len(sections)]
        si += 1
        for j in range(length):
            c = j % L
            m = j % 4
            bar = []
            last = j == length - 1
            if name != "C":
                bar.append("d_fill" if last else "d_main")
                bar.append(f"b{c}")
            if j == 0:
                bar.append("crash")
            if name == "A":
                bar.append(f"a{c}")
                if j >= 4:
                    bar.append(f"p{c}")
            elif name == "B":
                bar += [f"mA{m}", f"p{c}"]
                if spec.get("arpUnderLead", True):
                    bar.append(f"a{c}")
            elif name == "C":
                bar += [f"p{c}", f"mB{m}"]
                if j >= 2:
                    bar.append("d_intro")
            else:
                bar += [f"mB{m}" if (j // 4) % 2 == 0 else f"mA{m}", f"a{c}", f"p{c}"]
            bars.append(bar)
    return {
        "bpm": bpm,
        "style": {
            "lead": spec.get("lead", "square"),
            "bass": spec.get("bass", "saw"),
            "arp": spec.get("arp", "square"),
            "pad": spec.get("pad", "saw"),
            "cutoff": spec.get("cutoff", 2200),
        },
        "patterns": patterns,
        "bars": bars,
    }


def compose_loop(spec, kind):
    """Short looping songs for the menu and practice mode."""
    rng = random.Random(spec["seed"])
    root = spec["root"]
    scale = SCALES[spec["scale"]]
    prog = spec["prog"]
    patterns = {}
    L = len(prog)
    for i, deg in enumerate(prog):
        ch = _chord(root, scale, deg)
        patterns[f"p{i}"] = [[0, 3.9, "pad", c, 0.22] for c in ch]
        arp = ch + [c + 12 for c in ch]
        patterns[f"a{i}"] = [[k * 0.5, 0.4, "arp", arp[(k * 2 + i) % len(arp)] + 12, 0.22] for k in range(8)]
        patterns[f"b{i}"] = [[0, 1.8, "bass", ch[0] - 24, 0.6], [2, 1.8, "bass", ch[0] - 24, 0.5]]
    mel = _melody(rng, root, scale, prog)
    for i in range(4):
        patterns[f"m{i}"] = mel[i]
    patterns["d"] = _drums("half", "main") if kind == "menu" else _drums("half", "intro")
    bars = []
    for rep in range(4):
        for i in range(L):
            bar = [f"p{i}", f"a{i}", f"b{i}"]
            if kind == "menu" and rep >= 1:
                bar.append("d")
            if kind == "menu" and rep >= 2:
                bar.append(f"m{i % 4}")
            if kind == "practice" and rep % 2 == 1:
                bar.append(f"m{i % 4}")
            bars.append(bar)
    return {
        "bpm": spec["bpm"],
        "loop": True,
        "style": {"lead": spec.get("lead", "triangle"), "bass": "sine", "arp": spec.get("arp", "triangle"),
                  "pad": "saw", "cutoff": spec.get("cutoff", 1400)},
        "patterns": patterns,
        "bars": bars,
    }
