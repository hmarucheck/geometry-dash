// Deterministic game physics for Neon Pulse.
// Line-by-line port of python/neonpulse/physics.py - keep both in sync.
// tools/check_parity.js replays solver runs through this file to verify.
(function (root) {
  'use strict';

  const STEP = 1 / 120;
  const SPEEDS = [8.4, 10.4, 12.96, 15.6, 19.2];
  const CEIL = 9.0;
  const CEIL_MODES = new Set(['rocket', 'ball', 'saucer', 'dart', 'crawler']);
  const HEADBUTT_MODES = new Set(['cube', 'mech']);
  const MODES = ['cube', 'rocket', 'ball', 'saucer', 'dart', 'mech', 'crawler'];

  const CUBE_G = 100.0;
  const CUBE_JUMP = 21.0;
  const MAX_FALL = 26.0;
  const ROCKET_UP = 48.0;
  const ROCKET_DOWN = 40.0;
  const ROCKET_MAX = 11.0;
  const BALL_G = 80.0;
  const BALL_PUSH = 3.0;
  const BALL_MAX = 20.0;
  const SAUCER_G = 60.0;
  const SAUCER_FLAP = 14.0;
  const SAUCER_MAX = 13.0;
  const MECH_JUMP = 14.0;
  const MECH_BOOST = 0.15;

  const ORB_POWER = { orb_y: 1.0, orb_p: 0.68, orb_r: 1.35 };
  const PAD_POWER = { pad_y: 1.4, pad_p: 0.78, pad_r: 1.75 };
  const MODE_ORB_SCALE = { cube: 1.0, mech: 1.0, crawler: 1.0, rocket: 0.55, ball: 0.75, saucer: 0.75, dart: 0.0 };

  const ORBS = new Set(['orb_y', 'orb_p', 'orb_r', 'orb_b', 'orb_g', 'orb_k']);
  const PADS = new Set(['pad_y', 'pad_p', 'pad_r', 'pad_b']);
  const PORTALS = new Set(['p_cube', 'p_rocket', 'p_ball', 'p_saucer', 'p_dart', 'p_mech',
    'p_crawler', 'p_gup', 'p_gdown', 'p_gflip', 'p_s0', 'p_s1', 'p_s2', 'p_s3', 'p_s4']);
  const SPEED_PORTALS = { p_s0: 0, p_s1: 1, p_s2: 2, p_s3: 3, p_s4: 4 };
  const SPIKE_BOX = {
    spike: [0.32, 0.68, 0.0, 0.65],
    spike_d: [0.32, 0.68, 0.35, 1.0],
    spike_s: [0.32, 0.68, 0.0, 0.35],
    spike_sd: [0.32, 0.68, 0.65, 1.0],
  };

  class Level {
    constructor(data) {
      this.data = data;
      this.name = data.name;
      this.length = data.length;
      this.objects = data.objects.map((d, i) => {
        const isPortal = d.t.startsWith('p_');
        const o = {
          id: i, t: d.t, x: d.x, y: d.y,
          w: d.w !== undefined ? d.w : 1,
          h: d.h !== undefined ? d.h : (isPortal ? 3 : 1),
          r: d.r !== undefined ? d.r : 1,
          flip: !!d.flip,
        };
        o.x2 = o.x + o.w;
        o.y2 = o.y + o.h;
        return o;
      });
      this.cols = new Map();
      for (const o of this.objects) {
        let c0, c1;
        if (o.t === 'saw') {
          c0 = Math.floor(o.x - o.r); c1 = Math.floor(o.x + o.r);
        } else {
          c0 = Math.floor(o.x); c1 = Math.floor(o.x2 - 1e-9);
        }
        for (let c = c0; c <= c1; c++) {
          if (!this.cols.has(c)) this.cols.set(c, []);
          this.cols.get(c).push(o);
        }
      }
      this.coins = this.objects.filter((o) => o.t === 'coin');
    }

    near(x) {
      const c = Math.floor(x);
      const out = [];
      for (let cc = c - 1; cc <= c + 1; cc++) {
        const lst = this.cols.get(cc);
        if (lst) for (const o of lst) out.push(o);
      }
      return out;
    }

    columnObjs(x0, x1) {
      const out = [];
      for (let cc = Math.floor(x0); cc <= Math.floor(x1); cc++) {
        const lst = this.cols.get(cc);
        if (lst) for (const o of lst) out.push(o);
      }
      return out;
    }
  }

  class Player {
    constructor(level, mode, speed) {
      this.x = 0.0;
      this.y = 0.0;
      this.vy = 0.0;
      this.g = 1;
      this.mode = mode || 'cube';
      this.speed = speed === undefined ? 1 : speed;
      this.onGround = true;
      this.buffered = false;
      this.boost = 0.0;
      this.used = new Uint8Array(level.objects.length);
      this.coins = 0;
      this.dead = false;
      this.won = false;
      this.tele = null;
      this.events = [];
    }

    clone() {
      const p = Object.create(Player.prototype);
      Object.assign(p, this);
      p.used = this.used.slice();
      p.tele = null;
      p.events = [];
      return p;
    }
  }

  function overlap(ax0, ax1, ay0, ay1, bx0, bx1, by0, by1) {
    return ax1 > bx0 && ax0 < bx1 && ay1 > by0 && ay0 < by1;
  }

  function setMode(p, mode) {
    if (p.mode === mode) return;
    p.mode = mode;
    p.vy *= 0.5;
    p.boost = 0.0;
    p.onGround = false;
    p.events.push('portal');
  }

  function applyOrb(p, o) {
    const t = o.t;
    const g = p.g;
    if (t in ORB_POWER) {
      const s = MODE_ORB_SCALE[p.mode];
      if (s === 0.0) return false;
      p.vy = g * CUBE_JUMP * ORB_POWER[t] * s;
    } else if (t === 'orb_b') {
      p.g = -g;
      p.vy = -p.g * 8.0;
    } else if (t === 'orb_g') {
      p.g = -g;
      p.vy = -p.g * 16.0;
    } else if (t === 'orb_k') {
      p.vy = -g * 24.0;
    }
    p.onGround = false;
    p.boost = 0.0;
    return true;
  }

  function applyPad(p, o) {
    const t = o.t;
    const g = p.g;
    if (t === 'pad_b') {
      p.g = -g;
      p.vy = -p.g * 15.0;
    } else {
      let s = MODE_ORB_SCALE[p.mode];
      if (s === 0.0) s = 0.5;
      p.vy = g * CUBE_JUMP * PAD_POWER[t] * s;
    }
    p.onGround = false;
    p.boost = 0.0;
  }

  function applyPortal(p, o) {
    const t = o.t;
    if (t === 'p_gup') {
      if (p.g !== -1) { p.g = -1; p.vy *= 0.5; }
    } else if (t === 'p_gdown') {
      if (p.g !== 1) { p.g = 1; p.vy *= 0.5; }
    } else if (t === 'p_gflip') {
      p.g = -p.g;
      p.vy *= 0.5;
    } else if (t in SPEED_PORTALS) {
      p.speed = SPEED_PORTALS[t];
    } else {
      setMode(p, t.slice(2));
    }
    p.events.push('portal');
  }

  function crawlerTeleport(p, lvl) {
    const x0 = p.x + 0.05;
    const x1 = p.x + 0.95;
    let target;
    if (p.g > 0) {
      target = CEIL - 1.0;
      for (const b of lvl.columnObjs(x0, x1)) {
        if (b.t === 'block' && b.x2 > x0 && b.x < x1) {
          if (b.y >= p.y + 1.0 - 1e-6 && b.y - 1.0 < target) target = b.y - 1.0;
        }
      }
    } else {
      target = 0.0;
      for (const b of lvl.columnObjs(x0, x1)) {
        if (b.t === 'block' && b.x2 > x0 && b.x < x1) {
          if (b.y2 <= p.y + 1e-6 && b.y2 > target) target = b.y2;
        }
      }
    }
    p.tele = [p.y, target];
    p.y = target;
    p.g = -p.g;
    p.vy = 0.0;
    p.onGround = true;
    p.events.push('tele');
  }

  // Advance the player by one fixed STEP.
  function step(p, lvl, held, pressed) {
    if (p.dead || p.won) return;
    if (pressed) p.buffered = true;
    const dt = STEP;
    p.x += SPEEDS[p.speed] * dt;
    const near = lvl.near(p.x);

    // Orbs take priority over the mode's own click action.
    if (p.buffered) {
      const pcx = p.x + 0.5;
      const pcy = p.y + 0.5;
      for (const o of near) {
        if (ORBS.has(o.t) && !p.used[o.id]) {
          if (Math.abs(pcx - (o.x + 0.5)) < 0.95 && Math.abs(pcy - (o.y + 0.5)) < 0.95) {
            if (applyOrb(p, o)) {
              p.used[o.id] = 1;
              p.buffered = false;
              p.events.push('orb');
              break;
            }
          }
        }
      }
    }

    const mode = p.mode;
    let g = p.g;
    if (mode === 'cube') {
      if (p.onGround && held) {
        p.vy = g * CUBE_JUMP;
        p.onGround = false;
        p.buffered = false;
        p.events.push('jump');
      }
      p.vy -= g * CUBE_G * dt;
      if (p.vy * g < -MAX_FALL) p.vy = -MAX_FALL * g;
    } else if (mode === 'mech') {
      if (p.onGround && held) {
        p.vy = g * MECH_JUMP;
        p.boost = MECH_BOOST;
        p.onGround = false;
        p.buffered = false;
        p.events.push('jump');
      }
      if (p.boost > 0.0 && held) {
        p.vy = g * MECH_JUMP;
        p.boost -= dt;
      } else {
        p.boost = 0.0;
        p.vy -= g * CUBE_G * dt;
        if (p.vy * g < -MAX_FALL) p.vy = -MAX_FALL * g;
      }
    } else if (mode === 'rocket') {
      if (held) p.vy += g * ROCKET_UP * dt;
      else p.vy -= g * ROCKET_DOWN * dt;
      if (p.vy > ROCKET_MAX) p.vy = ROCKET_MAX;
      else if (p.vy < -ROCKET_MAX) p.vy = -ROCKET_MAX;
    } else if (mode === 'ball') {
      if (p.onGround && p.buffered) {
        g = -g;
        p.g = g;
        p.vy = -g * BALL_PUSH;
        p.onGround = false;
        p.buffered = false;
        p.events.push('flip');
      }
      p.vy -= g * BALL_G * dt;
      if (p.vy * g < -BALL_MAX) p.vy = -BALL_MAX * g;
    } else if (mode === 'saucer') {
      if (p.buffered) {
        p.vy = g * SAUCER_FLAP;
        p.buffered = false;
        p.onGround = false;
        p.events.push('jump');
      }
      p.vy -= g * SAUCER_G * dt;
      if (p.vy * g < -SAUCER_MAX) p.vy = -SAUCER_MAX * g;
    } else if (mode === 'dart') {
      p.vy = (held ? 1.0 : -1.0) * g * SPEEDS[p.speed];
    } else if (mode === 'crawler') {
      if (p.onGround && p.buffered) {
        p.buffered = false;
        crawlerTeleport(p, lvl);
        g = p.g;
      }
      p.vy -= g * CUBE_G * dt;
      if (p.vy * g < -MAX_FALL) p.vy = -MAX_FALL * g;
    }

    p.y += p.vy * dt;

    // Solid collisions.
    p.onGround = false;
    const headbutt = HEADBUTT_MODES.has(mode);
    if (p.y < 0.0) {
      if (g < 0 && headbutt) { p.dead = true; return; }
      p.y = 0.0;
      if (p.vy < 0.0) p.vy = 0.0;
      if (g > 0) p.onGround = true;
    }
    if (CEIL_MODES.has(mode) && p.y + 1.0 > CEIL) {
      p.y = CEIL - 1.0;
      if (p.vy > 0.0) p.vy = 0.0;
      if (g < 0) p.onGround = true;
    }
    for (const b of near) {
      if (b.t !== 'block') continue;
      if (p.x + 1.0 > b.x && p.x < b.x2 && p.y + 1.0 > b.y && p.y < b.y2) {
        const snap = 0.3 + Math.abs(p.vy) * dt;
        if (p.vy <= 0.0 && p.y >= b.y2 - snap) {
          if (g < 0 && headbutt) { p.dead = true; return; }
          p.y = b.y2;
          p.vy = 0.0;
          if (g > 0) p.onGround = true;
        } else if (p.vy >= 0.0 && p.y + 1.0 <= b.y + snap) {
          if (g > 0 && headbutt) { p.dead = true; return; }
          p.y = b.y - 1.0;
          p.vy = 0.0;
          if (g < 0) p.onGround = true;
        } else {
          p.dead = true;
          return;
        }
      }
    }

    // Pads, portals, coins.
    const px0 = p.x, px1 = p.x + 1.0, py0 = p.y, py1 = p.y + 1.0;
    for (const o of near) {
      const t = o.t;
      if (PADS.has(t)) {
        if (p.used[o.id]) continue;
        let hit;
        if (o.flip) hit = overlap(px0, px1, py0, py1, o.x, o.x + 1.0, o.y + 0.6, o.y + 1.0);
        else hit = overlap(px0, px1, py0, py1, o.x, o.x + 1.0, o.y, o.y + 0.4);
        if (hit) {
          p.used[o.id] = 1;
          applyPad(p, o);
          p.events.push('pad');
        }
      } else if (PORTALS.has(t)) {
        if (p.used[o.id]) continue;
        if (overlap(px0, px1, py0, py1, o.x, o.x2, o.y, o.y2)) {
          p.used[o.id] = 1;
          applyPortal(p, o);
        }
      } else if (t === 'coin') {
        if (overlap(px0, px1, py0, py1, o.x + 0.1, o.x + 0.9, o.y + 0.1, o.y + 0.9)) {
          const idx = Math.trunc(o.r);
          if (!((p.coins >> idx) & 1)) {
            p.coins |= 1 << idx;
            p.events.push('coin');
          }
        }
      }
    }

    // Hazards use a slightly smaller player box.
    const hx0 = p.x + 0.1, hx1 = p.x + 0.9, hy0 = p.y + 0.1, hy1 = p.y + 0.9;
    for (const o of near) {
      const t = o.t;
      const bx = SPIKE_BOX[t];
      if (bx) {
        if (overlap(hx0, hx1, hy0, hy1, o.x + bx[0], o.x + bx[1], o.y + bx[2], o.y + bx[3])) {
          p.dead = true;
          return;
        }
      } else if (t === 'saw') {
        const cx = Math.min(Math.max(o.x, hx0), hx1);
        const cy = Math.min(Math.max(o.y, hy0), hy1);
        const dx = o.x - cx;
        const dy = o.y - cy;
        const rr = o.r * 0.8;
        if (dx * dx + dy * dy < rr * rr) {
          p.dead = true;
          return;
        }
      }
    }

    if (!held) p.buffered = false;
    if (p.y > 40.0 || p.y < -5.0) { p.dead = true; return; }
    if (p.x >= lvl.length) p.won = true;
  }

  const Engine = {
    STEP, SPEEDS, CEIL, CEIL_MODES, MODES, ORBS, PADS, PORTALS, SPIKE_BOX,
    Level, Player, step,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = Engine;
  else root.Engine = Engine;
})(typeof window !== 'undefined' ? window : globalThis);
