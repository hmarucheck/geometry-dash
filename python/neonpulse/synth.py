"""Offline synthesizer for the generated songs (Python/pygame version).

Renders a song from levels.json (patterns + arrangement) into a WAV file
with numpy, caching the result so each song is only rendered once. The
instruments mirror web/js/audio.js closely enough that both versions of
the game sound alike.
"""

import hashlib
import json
import os
import wave

import numpy as np

RATE = 22050
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".cache")


def midi_hz(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def _harmonics(kind, f, cutoff):
    """(multiple, amplitude) pairs for a band-limited waveform."""
    top = max(1, int(min(cutoff, RATE * 0.45) / f))
    if kind == "sine":
        return [(1, 1.0)]
    if kind in ("square", "pulse"):
        return [(k, 1.0 / k) for k in range(1, top + 1, 2)]
    if kind == "triangle":
        return [(k, (1.0 if (k // 2) % 2 == 0 else -1.0) / (k * k)) for k in range(1, top + 1, 2)]
    return [(k, 1.0 / k) for k in range(1, top + 1)]  # saw


def _osc(kind, f, n, cutoff, phase_mod=None):
    t = np.arange(n) / RATE
    base = 2 * np.pi * f * t
    if phase_mod is not None:
        base = base + phase_mod
    out = np.zeros(n)
    for k, a in _harmonics(kind, f, cutoff):
        out += a * np.sin(k * base)
    return out * 0.6


def _env(n, attack, hold, release):
    a = max(1, int(attack * RATE))
    h = max(0, int(hold * RATE) - a)
    r = max(1, int(release * RATE))
    e = np.concatenate([np.linspace(0, 1, a), np.ones(h), np.exp(-np.linspace(0, 6, r))])
    if len(e) < n:
        e = np.concatenate([e, np.zeros(n - len(e))])
    return e[:n]


class _Noise:
    def __init__(self):
        rng = np.random.default_rng(12345)
        self.buf = rng.uniform(-1, 1, RATE * 2)

    def get(self, n, off):
        o = int(off) % (len(self.buf) - n - 1)
        return self.buf[o:o + n]


def _highpass(x, order=1):
    for _ in range(order):
        x = np.diff(x, prepend=x[0])
    return x


def _note(inst, dur, midi, vel, style, noise, k):
    if inst == "kick":
        n = int(0.38 * RATE)
        t = np.arange(n) / RATE
        f = 42 + 118 * np.exp(-t / 0.04)
        ph = 2 * np.pi * np.cumsum(f) / RATE
        return np.sin(ph) * np.exp(-t / 0.09) * vel * 1.1
    if inst == "snare":
        n = int(0.2 * RATE)
        t = np.arange(n) / RATE
        body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.03) * 0.5
        return (_highpass(noise.get(n, k * 977)) * 0.5 * np.exp(-t / 0.045) + body) * vel
    if inst == "clap":
        n = int(0.22 * RATE)
        t = np.arange(n) / RATE
        env = np.exp(-t / 0.05)
        for i in range(3):
            s = int(i * 0.012 * RATE)
            env[s:s + int(0.01 * RATE)] += 0.8
        return _highpass(noise.get(n, k * 613)) * env * vel * 0.45
    if inst in ("hat", "ohat"):
        d = 0.045 if inst == "hat" else 0.22
        n = int(d * RATE)
        t = np.arange(n) / RATE
        return _highpass(noise.get(n, k * 331), 2) * np.exp(-t / (d / 4)) * vel * 0.3
    if inst == "crash":
        n = int(1.3 * RATE)
        t = np.arange(n) / RATE
        return _highpass(noise.get(n, k * 101), 2) * np.exp(-t / 0.35) * vel * 0.28
    f = midi_hz(midi)
    if inst == "bass":
        n = int((dur + 0.06) * RATE)
        x = _osc(style.get("bass", "saw"), f, n, 900)
        return x * _env(n, 0.005, dur, 0.06) * vel * 0.75
    if inst == "lead":
        n = int((dur + 0.12) * RATE)
        t = np.arange(n) / RATE
        vib = np.sin(2 * np.pi * 5.5 * t) * (f * 0.006) / 5.5 * np.clip((t - 0.12) * 8, 0, 1)
        cut = style.get("cutoff", 2400)
        x = _osc(style.get("lead", "square"), f * 0.996, n, cut, vib) + _osc(style.get("lead", "square"), f * 1.004, n, cut, vib)
        return x * _env(n, 0.01, dur, 0.1) * vel * 0.3
    if inst == "arp":
        n = int((max(dur, 0.12) + 0.05) * RATE)
        t = np.arange(n) / RATE
        x = _osc(style.get("arp", "square"), f, n, style.get("cutoff", 2400) * 1.2)
        return x * np.exp(-t / max(dur, 0.12) * 5) * vel * 0.45
    if inst == "pad":
        n = int((dur + 0.45) * RATE)
        kind = style.get("pad", "saw")
        x = _osc(kind, f * 0.994, n, 900) + _osc(kind, f * 1.006, n, 900)
        return x * _env(n, 0.25, dur, 0.4) * vel * 0.28
    return np.zeros(1)


def render(song, seconds=None):
    """Render a song dict to a float array in [-1, 1]."""
    spb = 60.0 / song["bpm"]
    bar_len = 4 * spb
    bars = song["bars"]
    total = len(bars) * bar_len if seconds is None else seconds
    n_total = int((total + 1.5) * RATE)
    out = np.zeros(n_total)
    noise = _Noise()
    style = song["style"]
    cache = {}
    k = 0
    for bi, bar in enumerate(bars):
        t0 = bi * bar_len
        if t0 > total:
            break
        for pname in bar:
            for ev in song["patterns"][pname]:
                start = t0 + ev[0] * spb
                key = (ev[2], ev[3], round(ev[1], 3), ev[4]) if ev[2] not in ("snare", "hat", "ohat", "clap", "crash") else None
                if key is not None and key in cache:
                    x = cache[key]
                else:
                    x = _note(ev[2], ev[1] * spb, ev[3], ev[4], style, noise, k)
                    if key is not None:
                        cache[key] = x
                k += 1
                s = int(start * RATE)
                e = min(n_total, s + len(x))
                if e > s:
                    out[s:e] += x[:e - s]
    out = np.tanh(out * 0.9)
    return out


def song_path(song, name):
    """Render (or reuse from the cache) a song as a WAV file and return its path."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = hashlib.sha1(json.dumps(song, sort_keys=True).encode()).hexdigest()[:12]
    safe = "".join(c if c.isalnum() else "_" for c in name)
    path = os.path.join(CACHE_DIR, f"{safe}_{h}.wav")
    if not os.path.exists(path):
        data = render(song)
        pcm = (np.clip(data, -1, 1) * 28000).astype("<i2")
        tmp = path + ".tmp"
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        os.replace(tmp, path)
    return path


def effect(name):
    """Short sound effects as int16 mono arrays."""
    if name == "death":
        n = int(0.6 * RATE)
        t = np.arange(n) / RATE
        noise = np.random.default_rng(7).uniform(-1, 1, n)
        lp = np.convolve(noise, np.ones(6) / 6, mode="same")
        f = 35 + 85 * np.exp(-t / 0.1)
        thud = np.sin(2 * np.pi * np.cumsum(f) / RATE)
        x = lp * np.exp(-t / 0.15) * 0.9 + thud * np.exp(-t / 0.12) * 0.9
    elif name == "coin":
        x = np.concatenate([_osc("square", midi_hz(m), int(0.07 * RATE), 4000) * 0.4 for m in (76, 83, 88)])
        x *= np.exp(-np.linspace(0, 2, len(x)))
    elif name == "win":
        parts = []
        for m in (60, 64, 67, 72, 76, 79, 84):
            seg = _osc("triangle", midi_hz(m), int(0.07 * RATE), 4000)
            parts.append(seg)
        tail = _osc("triangle", midi_hz(84), int(0.7 * RATE), 4000) * np.exp(-np.linspace(0, 5, int(0.7 * RATE)))
        x = np.concatenate(parts + [tail]) * 0.6
    else:  # click / checkpoint
        n = int(0.08 * RATE)
        t = np.arange(n) / RATE
        f0 = 900 if name == "click" else 1300
        f = f0 * (1 + 0.6 * np.clip(t / 0.05, 0, 1))
        x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / RATE)) * np.exp(-t / 0.02) * 0.25
    return (np.clip(x, -1, 1) * 26000).astype("<i2")
