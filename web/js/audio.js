// Real-time synthesizer for the generated songs in levels.js, plus sound effects.
// Every level's song is note data (patterns + arrangement) produced by
// tools/compose.py; this file turns it into sound with the Web Audio API.
(function () {
  'use strict';

  const LOOKAHEAD = 0.18;
  const midiHz = (m) => 440 * Math.pow(2, (m - 69) / 12);

  class AudioEngine {
    constructor() {
      this.ctx = null;
      this.musicVolume = 0.8;
      this.sfxVolume = 0.8;
      this.song = null;
      this.timer = null;
    }

    // Browsers only allow audio after a user gesture, so this is called from input handlers.
    unlock() {
      if (!this.ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        this.ctx = new AC();
        this.master = this.ctx.createGain();
        this.master.connect(this.ctx.destination);
        this.comp = this.ctx.createDynamicsCompressor();
        this.comp.threshold.value = -14;
        this.comp.ratio.value = 4;
        this.comp.connect(this.master);
        this.sfxBus = this.ctx.createGain();
        this.sfxBus.gain.value = this.sfxVolume;
        this.sfxBus.connect(this.master);
        const len = this.ctx.sampleRate;
        this.noise = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
        const d = this.noise.getChannelData(0);
        let seed = 12345;
        for (let i = 0; i < len; i++) {
          seed = (seed * 1103515245 + 12345) & 0x7fffffff;
          d[i] = (seed / 0x3fffffff) - 1;
        }
      }
      if (this.ctx.state === 'suspended') this.ctx.resume();
    }

    setVolumes(music, sfx) {
      this.musicVolume = music;
      this.sfxVolume = sfx;
      if (this.song) this.song.bus.gain.value = music * 0.55;
      if (this.sfxBus) this.sfxBus.gain.value = sfx;
    }

    // ---- songs ---------------------------------------------------------
    play(song, opts) {
      opts = opts || {};
      this.stop();
      if (!this.ctx) return;
      const bus = this.ctx.createGain();
      bus.gain.value = this.musicVolume * 0.55;
      bus.connect(this.comp);
      const spb = 60 / song.bpm;
      const barCache = new Map();
      const barEvents = (i) => {
        const key = song.bars[i].join(',');
        if (!barCache.has(key)) {
          const ev = [];
          for (const p of song.bars[i]) for (const e of song.patterns[p]) ev.push(e);
          ev.sort((a, b) => a[0] - b[0]);
          barCache.set(key, ev);
        }
        return barCache.get(key);
      };
      const start = this.ctx.currentTime + (opts.delay || 0.05);
      this.song = { data: song, bus, start, spb, bar: 0, ev: 0, abs: 0, barEvents };
      const tick = () => this._schedule();
      tick();
      this.timer = setInterval(tick, 25);
    }

    stop(fade) {
      if (this.timer) clearInterval(this.timer);
      this.timer = null;
      if (this.song && this.ctx) {
        const bus = this.song.bus;
        const t = this.ctx.currentTime;
        bus.gain.cancelScheduledValues(t);
        bus.gain.setValueAtTime(bus.gain.value, t);
        bus.gain.linearRampToValueAtTime(0, t + (fade || 0.04));
        setTimeout(() => bus.disconnect(), ((fade || 0.04) + 0.6) * 1000);
      }
      this.song = null;
    }

    // Seconds since the current song started (negative during the lead-in).
    time() {
      if (!this.song || !this.ctx) return 0;
      return this.ctx.currentTime - this.song.start;
    }

    // 1 right on a beat, decaying towards 0 until the next one.
    pulse() {
      if (!this.song) return 0;
      const b = this.time() / this.song.spb;
      if (b < 0) return 0;
      return Math.pow(1 - (b % 1), 3);
    }

    _schedule() {
      const s = this.song;
      if (!s) return;
      const song = s.data;
      const horizon = this.ctx.currentTime + LOOKAHEAD;
      const barLen = 4 * s.spb;
      for (;;) {
        const barStart = s.start + s.abs * barLen;
        if (barStart > horizon) return;
        const ev = s.barEvents(s.bar);
        while (s.ev < ev.length) {
          const e = ev[s.ev];
          const t = barStart + e[0] * s.spb;
          if (t > horizon) return;
          if (t >= this.ctx.currentTime - 0.05) this._note(e[2], t, e[1] * s.spb, e[3], e[4], song.style, s.bus);
          s.ev++;
        }
        s.ev = 0;
        s.abs++;
        s.bar++;
        if (s.bar >= song.bars.length) s.bar = song.loop ? 0 : Math.min(2, song.bars.length - 1);
      }
    }

    _env(gain, t, a, peak, dur, rel) {
      const g = gain.gain;
      g.setValueAtTime(0.0001, t);
      g.linearRampToValueAtTime(peak, t + a);
      g.setValueAtTime(peak, t + Math.max(a, dur));
      g.exponentialRampToValueAtTime(0.0001, t + Math.max(a, dur) + rel);
    }

    _osc(type, freq, t, end, dest, detune) {
      const o = this.ctx.createOscillator();
      o.type = type === 'pulse' ? 'square' : type;
      o.frequency.setValueAtTime(freq, t);
      if (detune) o.detune.setValueAtTime(detune, t);
      o.connect(dest);
      o.start(t);
      o.stop(end + 0.05);
      return o;
    }

    _noise(t, dur, dest) {
      const n = this.ctx.createBufferSource();
      n.buffer = this.noise;
      n.connect(dest);
      n.start(t, Math.random() * 0.5);
      n.stop(t + dur + 0.05);
      return n;
    }

    _filter(type, freq, q) {
      const f = this.ctx.createBiquadFilter();
      f.type = type;
      f.frequency.value = freq;
      if (q) f.Q.value = q;
      return f;
    }

    _note(inst, t, dur, midi, vel, style, bus) {
      const ctx = this.ctx;
      const g = ctx.createGain();
      g.connect(bus);
      switch (inst) {
        case 'kick': {
          const o = ctx.createOscillator();
          o.type = 'sine';
          o.frequency.setValueAtTime(160, t);
          o.frequency.exponentialRampToValueAtTime(42, t + 0.13);
          o.connect(g);
          g.gain.setValueAtTime(vel * 1.1, t);
          g.gain.exponentialRampToValueAtTime(0.001, t + 0.38);
          o.start(t);
          o.stop(t + 0.4);
          break;
        }
        case 'snare': {
          const f = this._filter('highpass', 1300);
          f.connect(g);
          this._noise(t, 0.2, f);
          g.gain.setValueAtTime(vel * 0.55, t);
          g.gain.exponentialRampToValueAtTime(0.001, t + 0.18);
          const g2 = ctx.createGain();
          g2.connect(bus);
          this._osc('triangle', 190, t, t + 0.1, g2);
          g2.gain.setValueAtTime(vel * 0.5, t);
          g2.gain.exponentialRampToValueAtTime(0.001, t + 0.1);
          break;
        }
        case 'clap': {
          const f = this._filter('bandpass', 1500, 1.2);
          f.connect(g);
          this._noise(t, 0.25, f);
          g.gain.setValueAtTime(0.0001, t);
          for (let i = 0; i < 3; i++) {
            g.gain.setValueAtTime(vel * 0.8, t + i * 0.012);
            g.gain.exponentialRampToValueAtTime(0.05, t + i * 0.012 + 0.01);
          }
          g.gain.exponentialRampToValueAtTime(0.001, t + 0.2);
          break;
        }
        case 'hat':
        case 'ohat': {
          const f = this._filter('highpass', 7000);
          f.connect(g);
          const d = inst === 'hat' ? 0.045 : 0.22;
          this._noise(t, d, f);
          g.gain.setValueAtTime(vel * 0.6, t);
          g.gain.exponentialRampToValueAtTime(0.001, t + d);
          break;
        }
        case 'crash': {
          const f = this._filter('highpass', 3500);
          f.connect(g);
          this._noise(t, 1.4, f);
          g.gain.setValueAtTime(vel * 0.5, t);
          g.gain.exponentialRampToValueAtTime(0.001, t + 1.3);
          break;
        }
        case 'bass': {
          const f = this._filter('lowpass', 300, 6);
          f.frequency.setValueAtTime(1400, t);
          f.frequency.exponentialRampToValueAtTime(260, t + Math.min(dur, 0.25));
          f.connect(g);
          this._osc(style.bass, midiHz(midi), t, t + dur + 0.06, f);
          this._env(g, t, 0.005, vel * 0.55, dur, 0.06);
          break;
        }
        case 'lead': {
          const f = this._filter('lowpass', style.cutoff || 2400, 2);
          f.connect(g);
          const hz = midiHz(midi);
          const o1 = this._osc(style.lead, hz, t, t + dur + 0.12, f, -7);
          const o2 = this._osc(style.lead, hz, t, t + dur + 0.12, f, 7);
          const lfo = ctx.createOscillator();
          const lg = ctx.createGain();
          lfo.frequency.value = 5.5;
          lg.gain.value = hz * 0.006;
          lfo.connect(lg);
          lg.connect(o1.frequency);
          lg.connect(o2.frequency);
          lfo.start(t + 0.12);
          lfo.stop(t + dur + 0.15);
          this._env(g, t, 0.01, vel * 0.22, dur, 0.1);
          break;
        }
        case 'arp': {
          const f = this._filter('lowpass', (style.cutoff || 2400) * 1.2, 3);
          f.connect(g);
          this._osc(style.arp, midiHz(midi), t, t + dur + 0.1, f);
          g.gain.setValueAtTime(vel * 0.3, t);
          g.gain.exponentialRampToValueAtTime(0.001, t + Math.max(dur, 0.12));
          break;
        }
        case 'pad': {
          const f = this._filter('lowpass', 900, 0.7);
          f.connect(g);
          const hz = midiHz(midi);
          this._osc(style.pad, hz, t, t + dur + 0.5, f, -10);
          this._osc(style.pad, hz, t, t + dur + 0.5, f, 10);
          this._env(g, t, 0.25, vel * 0.16, dur, 0.4);
          break;
        }
        default:
          g.disconnect();
      }
    }

    // ---- sound effects -------------------------------------------------
    sfx(name) {
      if (!this.ctx) return;
      const ctx = this.ctx;
      const t = ctx.currentTime + 0.005;
      const g = ctx.createGain();
      g.connect(this.sfxBus);
      if (name === 'death') {
        const f = this._filter('lowpass', 3000);
        f.frequency.setValueAtTime(4000, t);
        f.frequency.exponentialRampToValueAtTime(200, t + 0.5);
        f.connect(g);
        this._noise(t, 0.6, f);
        g.gain.setValueAtTime(0.9, t);
        g.gain.exponentialRampToValueAtTime(0.001, t + 0.6);
        const g2 = ctx.createGain();
        g2.connect(this.sfxBus);
        const o = this._osc('sine', 120, t, t + 0.4, g2);
        o.frequency.exponentialRampToValueAtTime(35, t + 0.35);
        g2.gain.setValueAtTime(0.9, t);
        g2.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
      } else if (name === 'coin') {
        [76, 83, 88].forEach((m, i) => {
          const gi = ctx.createGain();
          gi.connect(this.sfxBus);
          this._osc('square', midiHz(m), t + i * 0.06, t + i * 0.06 + 0.15, gi);
          gi.gain.setValueAtTime(0.0001, t);
          gi.gain.setValueAtTime(0.15, t + i * 0.06);
          gi.gain.exponentialRampToValueAtTime(0.001, t + i * 0.06 + 0.15);
        });
      } else if (name === 'win') {
        [60, 64, 67, 72, 76, 79, 84].forEach((m, i) => {
          const gi = ctx.createGain();
          gi.connect(this.sfxBus);
          this._osc('triangle', midiHz(m), t + i * 0.07, t + i * 0.07 + 0.8, gi);
          gi.gain.setValueAtTime(0.0001, t);
          gi.gain.setValueAtTime(0.25, t + i * 0.07);
          gi.gain.exponentialRampToValueAtTime(0.001, t + i * 0.07 + 0.8);
        });
      } else if (name === 'click' || name === 'checkpoint') {
        const hi = name === 'click' ? 900 : 1300;
        const o = this._osc('square', hi, t, t + 0.08, g);
        o.frequency.exponentialRampToValueAtTime(hi * 1.6, t + 0.05);
        g.gain.setValueAtTime(0.12, t);
        g.gain.exponentialRampToValueAtTime(0.001, t + 0.08);
      } else {
        g.disconnect();
      }
    }
  }

  window.AudioEngine = AudioEngine;
})();
