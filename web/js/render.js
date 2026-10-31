// Canvas drawing for Neon Pulse: world, player forms, particles and HUD.
(function () {
  'use strict';

  const ORB_COLORS = {
    orb_y: '#ffe23a', orb_p: '#ff5ad8', orb_r: '#ff4040', orb_b: '#3ad0ff', orb_g: '#3aff7c', orb_k: '#1a1a1a',
  };
  const PAD_COLORS = { pad_y: '#ffe23a', pad_p: '#ff5ad8', pad_r: '#ff4040', pad_b: '#3ad0ff' };
  const PORTAL_STYLE = {
    p_cube: ['#3aff6e', 'CUBE'], p_rocket: ['#ff4fd8', 'ROCKET'], p_ball: ['#ff5a3a', 'BALL'],
    p_saucer: ['#ffa13a', 'SAUCER'], p_dart: ['#3ae8ff', 'DART'], p_mech: ['#f2f2f2', 'MECH'],
    p_crawler: ['#a45aff', 'CRAWLER'], p_gup: ['#ffe23a', ''], p_gdown: ['#3a9cff', ''], p_gflip: ['#3aff7c', ''],
    p_s0: ['#ffa13a', '<'], p_s1: ['#3ad0ff', '>'], p_s2: ['#3aff6e', '>>'], p_s3: ['#ff4fd8', '>>>'], p_s4: ['#ff4040', '>>>>'],
  };

  function hexToRgb(h) {
    const n = parseInt(h.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgb(c, a) {
    return a === undefined ? `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})` : `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
  }
  function mix(a, b, t) {
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  }
  function shade(c, f) {
    return f >= 0 ? mix(c, [255, 255, 255], f) : mix(c, [0, 0, 0], -f);
  }

  // ---------------------------------------------------------------------
  // Player icons. (x, y) is the centre in pixels; s is one block in pixels.
  const DESIGNS = ['classic', 'visor', 'cross', 'diamond', 'stripes', 'ring', 'grin', 'split', 'robot', 'star'];

  function drawCubeFace(ctx, s, icon) {
    const p = icon.primary, q = icon.secondary;
    const h = s / 2;
    ctx.fillStyle = p;
    ctx.fillRect(-h, -h, s, s);
    ctx.fillStyle = q;
    const d = DESIGNS[icon.design % DESIGNS.length];
    if (d === 'classic') {
      ctx.fillRect(-h * 0.55, -h * 0.55, s * 0.55, s * 0.55);
      ctx.fillStyle = p;
      ctx.fillRect(-h * 0.3, -h * 0.3, s * 0.3, s * 0.3);
    } else if (d === 'visor') {
      ctx.fillRect(-h * 0.8, -h * 0.35, s * 0.8, s * 0.3);
      ctx.fillStyle = '#fff';
      ctx.fillRect(h * 0.25, -h * 0.28, s * 0.12, s * 0.16);
    } else if (d === 'cross') {
      ctx.fillRect(-h * 0.18, -h * 0.8, s * 0.18, s * 0.8);
      ctx.fillRect(-h * 0.8, -h * 0.18, s * 0.8, s * 0.18);
    } else if (d === 'diamond') {
      ctx.beginPath();
      ctx.moveTo(0, -h * 0.75); ctx.lineTo(h * 0.75, 0); ctx.lineTo(0, h * 0.75); ctx.lineTo(-h * 0.75, 0);
      ctx.closePath();
      ctx.fill();
    } else if (d === 'stripes') {
      for (let i = -1; i <= 1; i++) ctx.fillRect(-h, i * s * 0.3 - s * 0.07, s, s * 0.14);
    } else if (d === 'ring') {
      ctx.beginPath();
      ctx.arc(0, 0, h * 0.62, 0, Math.PI * 2);
      ctx.arc(0, 0, h * 0.32, 0, Math.PI * 2, true);
      ctx.fill();
    } else if (d === 'grin') {
      ctx.fillRect(-h * 0.55, -h * 0.45, s * 0.2, s * 0.2);
      ctx.fillRect(h * 0.15, -h * 0.45, s * 0.2, s * 0.2);
      ctx.fillRect(-h * 0.55, h * 0.2, s * 0.55, s * 0.14);
      ctx.fillRect(-h * 0.55, h * 0.05, s * 0.1, s * 0.14);
      ctx.fillRect(h * 0.35, h * 0.05, s * 0.1, s * 0.14);
    } else if (d === 'split') {
      ctx.beginPath();
      ctx.moveTo(-h, -h); ctx.lineTo(h, h); ctx.lineTo(-h, h);
      ctx.closePath();
      ctx.fill();
    } else if (d === 'robot') {
      ctx.fillRect(-h * 0.7, -h * 0.5, s * 0.7, s * 0.4);
      ctx.fillStyle = p;
      ctx.fillRect(-h * 0.5, -h * 0.35, s * 0.15, s * 0.15);
      ctx.fillRect(h * 0.2, -h * 0.35, s * 0.15, s * 0.15);
      ctx.fillStyle = q;
      ctx.fillRect(-h * 0.4, h * 0.3, s * 0.4, s * 0.12);
    } else if (d === 'star') {
      ctx.beginPath();
      for (let i = 0; i < 10; i++) {
        const r = i % 2 ? h * 0.3 : h * 0.75;
        const a = -Math.PI / 2 + (i * Math.PI) / 5;
        ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r);
      }
      ctx.closePath();
      ctx.fill();
    }
    ctx.lineWidth = Math.max(1.5, s * 0.07);
    ctx.strokeStyle = '#000';
    ctx.strokeRect(-h, -h, s, s);
  }

  // mode: game mode; angle in radians; anim: running time for legs etc.
  function drawPlayer(ctx, mode, x, y, s, angle, icon, anim, flipped) {
    ctx.save();
    ctx.translate(x, y);
    if (flipped && (mode === 'mech' || mode === 'crawler' || mode === 'saucer' || mode === 'rocket')) ctx.scale(1, -1);
    if (mode === 'cube') {
      ctx.rotate(angle);
      drawCubeFace(ctx, s, icon);
    } else if (mode === 'rocket') {
      ctx.rotate(angle);
      ctx.save();
      ctx.translate(-s * 0.08, -s * 0.22);
      drawCubeFace(ctx, s * 0.5, icon);
      ctx.restore();
      ctx.beginPath();
      ctx.moveTo(-s * 0.6, -s * 0.05);
      ctx.lineTo(s * 0.55, -s * 0.05);
      ctx.lineTo(s * 0.7, s * 0.12);
      ctx.lineTo(s * 0.35, s * 0.35);
      ctx.lineTo(-s * 0.45, s * 0.35);
      ctx.lineTo(-s * 0.65, s * 0.15);
      ctx.closePath();
      ctx.fillStyle = icon.primary;
      ctx.fill();
      ctx.lineWidth = Math.max(1.5, s * 0.06);
      ctx.strokeStyle = '#000';
      ctx.stroke();
      ctx.fillStyle = icon.secondary;
      ctx.fillRect(-s * 0.35, s * 0.08, s * 0.6, s * 0.12);
    } else if (mode === 'ball') {
      ctx.rotate(angle);
      const r = s * 0.5;
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.fillStyle = icon.primary;
      ctx.fill();
      ctx.fillStyle = icon.secondary;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, r, 0, Math.PI / 2);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, r, Math.PI, Math.PI * 1.5);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.arc(0, 0, r * 0.35, 0, Math.PI * 2);
      ctx.fillStyle = icon.primary;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.lineWidth = Math.max(1.5, s * 0.07);
      ctx.strokeStyle = '#000';
      ctx.stroke();
    } else if (mode === 'saucer') {
      ctx.rotate(angle);
      ctx.beginPath();
      ctx.arc(0, -s * 0.05, s * 0.32, Math.PI, 0);
      ctx.fillStyle = 'rgba(180,240,255,0.55)';
      ctx.fill();
      ctx.save();
      ctx.translate(0, -s * 0.14);
      drawCubeFace(ctx, s * 0.36, icon);
      ctx.restore();
      ctx.beginPath();
      ctx.ellipse(0, s * 0.1, s * 0.62, s * 0.2, 0, 0, Math.PI * 2);
      ctx.fillStyle = icon.primary;
      ctx.fill();
      ctx.lineWidth = Math.max(1.5, s * 0.06);
      ctx.strokeStyle = '#000';
      ctx.stroke();
      ctx.fillStyle = icon.secondary;
      for (let i = -1; i <= 1; i++) {
        ctx.beginPath();
        ctx.arc(i * s * 0.3, s * 0.1, s * 0.06, 0, Math.PI * 2);
        ctx.fill();
      }
    } else if (mode === 'dart') {
      ctx.rotate(angle);
      ctx.beginPath();
      ctx.moveTo(s * 0.5, 0);
      ctx.lineTo(-s * 0.45, -s * 0.38);
      ctx.lineTo(-s * 0.25, 0);
      ctx.lineTo(-s * 0.45, s * 0.38);
      ctx.closePath();
      ctx.fillStyle = icon.primary;
      ctx.fill();
      ctx.lineWidth = Math.max(1.5, s * 0.06);
      ctx.strokeStyle = '#000';
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(s * 0.25, 0);
      ctx.lineTo(-s * 0.2, -s * 0.16);
      ctx.lineTo(-s * 0.2, s * 0.16);
      ctx.closePath();
      ctx.fillStyle = icon.secondary;
      ctx.fill();
    } else if (mode === 'mech') {
      const step = Math.sin(anim * 18);
      ctx.strokeStyle = '#000';
      ctx.lineWidth = Math.max(2, s * 0.08);
      ctx.fillStyle = icon.secondary;
      for (const side of [-1, 1]) {
        const k = side * step;
        ctx.save();
        ctx.translate(side * s * 0.15, s * 0.05);
        ctx.rotate(k * 0.4);
        ctx.fillRect(-s * 0.08, 0, s * 0.16, s * 0.42);
        ctx.strokeRect(-s * 0.08, 0, s * 0.16, s * 0.42);
        ctx.fillRect(-s * 0.05, s * 0.36, s * 0.28, s * 0.1);
        ctx.restore();
      }
      ctx.save();
      ctx.translate(0, -s * 0.18);
      drawCubeFace(ctx, s * 0.62, icon);
      ctx.restore();
    } else if (mode === 'crawler') {
      const step = Math.sin(anim * 22);
      ctx.strokeStyle = icon.secondary;
      ctx.lineWidth = Math.max(2, s * 0.09);
      ctx.lineCap = 'round';
      for (let i = 0; i < 4; i++) {
        const side = i < 2 ? -1 : 1;
        const off = (i % 2 ? 0.12 : 0.32) * side;
        const k = (i % 2 ? step : -step) * 0.12;
        ctx.beginPath();
        ctx.moveTo(off * s, 0);
        ctx.lineTo((off * 1.6 + k) * s, s * 0.2);
        ctx.lineTo((off * 1.5 + k) * s, s * 0.48);
        ctx.stroke();
      }
      ctx.save();
      ctx.translate(0, -s * 0.12);
      ctx.beginPath();
      ctx.ellipse(0, 0, s * 0.42, s * 0.3, 0, 0, Math.PI * 2);
      ctx.fillStyle = icon.primary;
      ctx.fill();
      ctx.lineWidth = Math.max(1.5, s * 0.06);
      ctx.strokeStyle = '#000';
      ctx.stroke();
      ctx.fillStyle = icon.secondary;
      ctx.fillRect(-s * 0.2, -s * 0.12, s * 0.12, s * 0.12);
      ctx.fillRect(s * 0.08, -s * 0.12, s * 0.12, s * 0.12);
      ctx.restore();
    }
    ctx.restore();
  }

  // Difficulty faces for the level select (original artwork).
  function drawFace(ctx, diff, x, y, r) {
    const cols = ['#3ac8ff', '#3aff7c', '#ffd23a', '#ff8a3a', '#ff3ad2', '#ff2a2a'];
    ctx.save();
    ctx.translate(x, y);
    if (diff === 5) {
      ctx.fillStyle = '#ff2a2a';
      for (const sd of [-1, 1]) {
        ctx.beginPath();
        ctx.moveTo(sd * r * 0.45, -r * 0.7);
        ctx.lineTo(sd * r * 0.95, -r * 1.35);
        ctx.lineTo(sd * r * 0.85, -r * 0.45);
        ctx.fill();
      }
    }
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fillStyle = cols[diff];
    ctx.fill();
    ctx.lineWidth = r * 0.12;
    ctx.strokeStyle = '#000';
    ctx.stroke();
    ctx.fillStyle = '#000';
    const eyeY = -r * 0.2;
    if (diff >= 3) {
      for (const sd of [-1, 1]) {
        ctx.beginPath();
        ctx.moveTo(sd * r * 0.15, eyeY - r * 0.05);
        ctx.lineTo(sd * r * 0.6, eyeY - r * 0.3);
        ctx.lineTo(sd * r * 0.55, eyeY + r * 0.12);
        ctx.closePath();
        ctx.fill();
      }
    } else {
      for (const sd of [-1, 1]) {
        ctx.beginPath();
        ctx.arc(sd * r * 0.35, eyeY, r * 0.13, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.beginPath();
    ctx.lineWidth = r * 0.12;
    if (diff <= 1) ctx.arc(0, r * 0.1, r * 0.45, 0.15 * Math.PI, 0.85 * Math.PI);
    else if (diff === 2) { ctx.moveTo(-r * 0.4, r * 0.4); ctx.lineTo(r * 0.4, r * 0.4); }
    else ctx.arc(0, r * 0.75, r * 0.45, 1.2 * Math.PI, 1.8 * Math.PI);
    ctx.stroke();
    ctx.restore();
  }

  // ---------------------------------------------------------------------
  class Renderer {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.frame = 0;
      this.resize();
    }

    resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = window.innerWidth, h = window.innerHeight;
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
      this.canvas.style.width = w + 'px';
      this.canvas.style.height = h + 'px';
      this.W = this.canvas.width;
      this.H = this.canvas.height;
      // Pixels per block: 11 blocks tall, but always at least 16 blocks wide.
      this.U = Math.min(this.H / 11, this.W / 16);
      this.dpr = dpr;
    }

    sx(wx, cam) { return (wx - cam.x) * this.U; }
    sy(wy, cam) { return this.H - (wy - cam.y) * this.U; }

    // Background used behind menus: slowly scrolling world without obstacles.
    drawMenuBackground(t, bg, ground, pulse) {
      const cam = { x: t * 4, y: -2.2 };
      this.drawBackground(cam, bg, pulse);
      this.drawGround(cam, ground, 0, pulse);
    }

    drawBackground(cam, bg, pulse) {
      const ctx = this.ctx, W = this.W, H = this.H, U = this.U;
      const top = shade(bg, -0.15 + pulse * 0.05);
      const bot = shade(bg, -0.55);
      const grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, rgb(top));
      grad.addColorStop(1, rgb(bot));
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);
      // Two parallax layers of big translucent squares.
      for (const layer of [{ f: 0.08, size: 3.2, a: 0.07 }, { f: 0.18, size: 2.0, a: 0.06 }]) {
        const size = layer.size * U;
        const off = -((cam.x * layer.f * U) % (size * 2));
        ctx.strokeStyle = rgb(shade(bg, 0.5), layer.a + pulse * 0.03);
        ctx.fillStyle = rgb(shade(bg, 0.3), layer.a * 0.6);
        ctx.lineWidth = 2;
        for (let gx = off - size * 2; gx < W + size; gx += size * 2) {
          for (let gy = (layer.f > 0.1 ? size * 0.5 : 0); gy < H; gy += size * 2) {
            ctx.fillRect(gx, gy, size * 0.92, size * 0.92);
            ctx.strokeRect(gx, gy, size * 0.92, size * 0.92);
          }
        }
      }
    }

    drawGround(cam, ground, ceilAlpha, pulse) {
      const ctx = this.ctx, W = this.W, U = this.U;
      const gy = this.sy(0, cam);
      const gcol = ground;
      const draw = (yTop, yBottom, lineY) => {
        const grad = ctx.createLinearGradient(0, yTop, 0, yBottom);
        grad.addColorStop(0, rgb(shade(gcol, 0.05)));
        grad.addColorStop(1, rgb(shade(gcol, -0.6)));
        ctx.fillStyle = grad;
        ctx.fillRect(0, yTop, W, yBottom - yTop);
        const tile = 4 * U;
        const off = -((cam.x * U) % tile);
        ctx.strokeStyle = rgb(shade(gcol, -0.35), 0.8);
        ctx.lineWidth = 2;
        for (let x = off; x < W; x += tile) {
          ctx.strokeRect(x, Math.min(yTop, yBottom), tile, Math.min(tile, Math.abs(yBottom - yTop)));
        }
        const lg = ctx.createLinearGradient(0, 0, W, 0);
        lg.addColorStop(0, 'rgba(255,255,255,0)');
        lg.addColorStop(0.5, `rgba(255,255,255,${0.85 + pulse * 0.15})`);
        lg.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = lg;
        ctx.fillRect(0, lineY - 1.5 * this.dpr, W, 3 * this.dpr);
      };
      if (gy < this.H) draw(gy, this.H, gy);
      if (ceilAlpha > 0.01) {
        const cy = this.sy(Engine.CEIL, cam);
        const slide = (1 - ceilAlpha) * 3 * U;
        if (cy - slide > 0) draw(-slide, cy - slide, cy - slide);
      }
    }

    // Iterate each visible object exactly once.
    visible(level, cam, fn) {
      this.frame++;
      const x0 = Math.floor(cam.x) - 2, x1 = Math.ceil(cam.x + this.W / this.U) + 2;
      for (let c = x0; c <= x1; c++) {
        const lst = level.cols.get(c);
        if (!lst) continue;
        for (const o of lst) {
          if (o._f === this.frame) continue;
          o._f = this.frame;
          fn(o);
        }
      }
    }

    drawObjects(g) {
      const ctx = this.ctx, U = this.U, cam = g.cam, t = g.time, pulse = g.pulse;
      const accent = rgb(shade(g.bgColor, 0.65));
      const blocks = [], hazards = [], others = [];
      this.visible(g.level, cam, (o) => {
        if (o.t === 'block') blocks.push(o);
        else if (o.t === 'saw' || o.t.startsWith('spike')) hazards.push(o);
        else others.push(o);
      });
      // Portals are drawn in two halves around the player; back half here.
      for (const o of others) if (o.t.startsWith('p_')) this.drawPortal(o, g, true);

      for (const o of blocks) {
        const x = this.sx(o.x, cam), y = this.sy(o.y2, cam), w = o.w * U, h = o.h * U;
        const grad = ctx.createLinearGradient(0, y, 0, y + h);
        grad.addColorStop(0, 'rgba(0,0,0,0.78)');
        grad.addColorStop(1, rgb(shade(g.bgColor, -0.8), 0.92));
        ctx.fillStyle = grad;
        ctx.fillRect(x, y, w, h);
        ctx.strokeStyle = rgb(shade(g.bgColor, 0.4), 0.25);
        ctx.lineWidth = 1;
        for (let i = 1; i < o.w; i++) {
          ctx.beginPath(); ctx.moveTo(x + i * U, y); ctx.lineTo(x + i * U, y + h); ctx.stroke();
        }
        for (let j = 1; j < o.h; j++) {
          ctx.beginPath(); ctx.moveTo(x, y + j * U); ctx.lineTo(x + w, y + j * U); ctx.stroke();
        }
        ctx.strokeStyle = accent;
        ctx.lineWidth = Math.max(2, U * 0.06);
        ctx.strokeRect(x, y, w, h);
        ctx.strokeStyle = `rgba(255,255,255,${0.12 + pulse * 0.12})`;
        ctx.lineWidth = 1;
        ctx.strokeRect(x + U * 0.12, y + U * 0.12, w - U * 0.24, h - U * 0.24);
      }

      for (const o of hazards) {
        if (o.t === 'saw') {
          const cx = this.sx(o.x, cam), cy = this.sy(o.y, cam), r = o.r * U;
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(t * 6);
          ctx.beginPath();
          const teeth = 14;
          for (let i = 0; i < teeth * 2; i++) {
            const rr = i % 2 ? r * 0.82 : r;
            const a = (i * Math.PI) / teeth;
            ctx.lineTo(Math.cos(a) * rr, Math.sin(a) * rr);
          }
          ctx.closePath();
          ctx.fillStyle = 'rgba(0,0,0,0.85)';
          ctx.fill();
          ctx.strokeStyle = accent;
          ctx.lineWidth = Math.max(2, U * 0.05);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(0, 0, r * 0.45, 0, Math.PI * 2);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(0, 0, r * 0.15, 0, Math.PI * 2);
          ctx.fillStyle = accent;
          ctx.fill();
          ctx.restore();
          continue;
        }
        const small = o.t === 'spike_s' || o.t === 'spike_sd';
        const down = o.t === 'spike_d' || o.t === 'spike_sd';
        const hh = small ? 0.45 : 1;
        const x = this.sx(o.x, cam);
        const base = down ? this.sy(o.y + 1, cam) : this.sy(o.y, cam);
        const tip = down ? base + hh * U : base - hh * U;
        ctx.beginPath();
        ctx.moveTo(x + U * 0.06, base);
        ctx.lineTo(x + U * 0.5, tip);
        ctx.lineTo(x + U * 0.94, base);
        ctx.closePath();
        const sg = ctx.createLinearGradient(0, tip, 0, base);
        sg.addColorStop(0, 'rgba(0,0,0,0.6)');
        sg.addColorStop(1, 'rgba(0,0,0,0.95)');
        ctx.fillStyle = sg;
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = Math.max(1.5, U * 0.05);
        ctx.stroke();
      }

      for (const o of others) {
        if (o.t.startsWith('orb_')) this.drawOrb(o, g);
        else if (o.t.startsWith('pad_')) this.drawPad(o, g);
        else if (o.t === 'coin') this.drawCoin(o, g);
      }
    }

    drawOrb(o, g) {
      const ctx = this.ctx, U = this.U, cam = g.cam;
      const cx = this.sx(o.x + 0.5, cam), cy = this.sy(o.y + 0.5, cam);
      const col = hexToRgb(ORB_COLORS[o.t]);
      const used = g.player.used[o.id];
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, U * 0.9);
      glow.addColorStop(0, rgb(col, used ? 0.15 : 0.5));
      glow.addColorStop(1, rgb(col, 0));
      ctx.fillStyle = glow;
      ctx.fillRect(cx - U, cy - U, U * 2, U * 2);
      ctx.beginPath();
      ctx.arc(cx, cy, U * (0.3 + g.pulse * 0.04), 0, Math.PI * 2);
      ctx.fillStyle = rgb(o.t === 'orb_k' ? [20, 20, 20] : col);
      ctx.fill();
      ctx.lineWidth = Math.max(2, U * 0.06);
      ctx.strokeStyle = o.t === 'orb_k' ? '#ff3030' : '#fff';
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, U * (0.46 + g.pulse * 0.08), 0, Math.PI * 2);
      ctx.strokeStyle = rgb(o.t === 'orb_k' ? [255, 60, 60] : col, 0.8);
      ctx.lineWidth = Math.max(1.5, U * 0.04);
      ctx.stroke();
      if (used) {
        const age = g.orbHits.get(o.id);
        if (age !== undefined) {
          const k = Math.min(1, (g.time - age) / 0.35);
          ctx.beginPath();
          ctx.arc(cx, cy, U * (0.4 + k * 0.9), 0, Math.PI * 2);
          ctx.strokeStyle = rgb(col, 1 - k);
          ctx.lineWidth = U * 0.08 * (1 - k);
          ctx.stroke();
        }
      }
    }

    drawPad(o, g) {
      const ctx = this.ctx, U = this.U, cam = g.cam;
      const col = hexToRgb(PAD_COLORS[o.t]);
      const x = this.sx(o.x, cam);
      const base = o.flip ? this.sy(o.y + 1, cam) : this.sy(o.y, cam);
      const dir = o.flip ? 1 : -1;
      const glow = ctx.createLinearGradient(0, base, 0, base + dir * U * 1.2);
      glow.addColorStop(0, rgb(col, 0.45 + g.pulse * 0.2));
      glow.addColorStop(1, rgb(col, 0));
      ctx.fillStyle = glow;
      ctx.fillRect(x + U * 0.1, Math.min(base, base + dir * U * 1.2), U * 0.8, U * 1.2);
      ctx.beginPath();
      ctx.ellipse(x + U * 0.5, base, U * 0.45, U * 0.2, 0, o.flip ? 0 : Math.PI, o.flip ? Math.PI : Math.PI * 2);
      ctx.fillStyle = rgb(col);
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = Math.max(1.5, U * 0.04);
      ctx.stroke();
    }

    drawCoin(o, g) {
      const ctx = this.ctx, U = this.U, cam = g.cam;
      const idx = Math.trunc(o.r);
      const got = (g.player.coins >> idx) & 1;
      const cx = this.sx(o.x + 0.5, cam), cy = this.sy(o.y + 0.5, cam);
      const prev = g.prevCoins & (1 << idx);
      ctx.save();
      ctx.translate(cx, cy - (got ? (g.time - (g.coinTimes[idx] || g.time)) * U * 3 : 0));
      if (got) ctx.globalAlpha = Math.max(0, 1 - (g.time - (g.coinTimes[idx] || g.time)) * 1.5);
      ctx.scale(Math.cos(g.time * 3), 1);
      const r = U * 0.42;
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.fillStyle = prev ? '#9aa4b8' : '#ffc928';
      ctx.fill();
      ctx.lineWidth = Math.max(2, U * 0.06);
      ctx.strokeStyle = prev ? '#5b6478' : '#b07a00';
      ctx.stroke();
      ctx.beginPath();
      for (let i = 0; i < 10; i++) {
        const rr = i % 2 ? r * 0.25 : r * 0.6;
        const a = -Math.PI / 2 + (i * Math.PI) / 5;
        ctx.lineTo(Math.cos(a) * rr, Math.sin(a) * rr);
      }
      ctx.closePath();
      ctx.fillStyle = prev ? '#d8deea' : '#fff3b0';
      ctx.fill();
      ctx.restore();
    }

    drawPortal(o, g, back) {
      const ctx = this.ctx, U = this.U, cam = g.cam;
      const st = PORTAL_STYLE[o.t];
      if (!st) return;
      const col = hexToRgb(st[0]);
      const cx = this.sx(o.x + 0.5, cam);
      const cy = this.sy(o.y + o.h / 2, cam);
      const rx = U * 0.55, ry = (o.h / 2) * U * 0.95;
      const speed = o.t.startsWith('p_s');
      ctx.save();
      if (speed) {
        if (!back) { ctx.restore(); return; }
        ctx.fillStyle = rgb(col, 0.85);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = Math.max(1.5, U * 0.04);
        const n = st[1].length;
        const dir = st[1][0] === '<' ? -1 : 1;
        for (let i = 0; i < n; i++) {
          const ox = cx + (i - (n - 1) / 2) * U * 0.45;
          ctx.beginPath();
          ctx.moveTo(ox - dir * U * 0.3, cy - U * 0.8);
          ctx.lineTo(ox + dir * U * 0.3, cy);
          ctx.lineTo(ox - dir * U * 0.3, cy + U * 0.8);
          ctx.lineTo(ox - dir * U * 0.05, cy);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
        }
        ctx.restore();
        return;
      }
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, ry * 1.1);
      glow.addColorStop(0, rgb(col, back ? 0.35 : 0));
      glow.addColorStop(1, rgb(col, 0));
      if (back) {
        ctx.fillStyle = glow;
        ctx.fillRect(cx - ry, cy - ry * 1.1, ry * 2, ry * 2.2);
      }
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, back ? Math.PI * 0.5 : -Math.PI * 0.5, back ? Math.PI * 1.5 : Math.PI * 0.5);
      ctx.lineWidth = U * 0.22;
      ctx.strokeStyle = rgb(shade(col, -0.3));
      ctx.stroke();
      ctx.lineWidth = U * 0.1;
      ctx.strokeStyle = rgb(shade(col, 0.3 + g.pulse * 0.3));
      ctx.stroke();
      if (back) {
        // little sparks drifting into the portal
        for (let i = 0; i < 5; i++) {
          const k = ((g.time * 1.5 + i / 5 + o.id * 0.37) % 1);
          const py = cy + Math.sin(i * 2.3 + o.id) * ry * 0.7;
          ctx.fillStyle = rgb(col, 1 - k);
          ctx.fillRect(cx + (1 - k) * U * 1.2, py, U * 0.1, U * 0.1);
        }
        if (st[1] && o.h >= 3) {
          ctx.font = `bold ${Math.round(U * 0.24)}px system-ui, sans-serif`;
          ctx.textAlign = 'center';
          ctx.fillStyle = rgb(shade(col, 0.6), 0.8);
          ctx.fillText(st[1], cx, cy - ry - U * 0.15);
        }
      }
      ctx.restore();
    }

    drawPlayerWorld(g) {
      const p = g.player, U = this.U, cam = g.cam, ctx = this.ctx;
      const cx = this.sx(p.x + 0.5, cam), cy = this.sy(p.y + 0.5, cam);
      // trail
      if (g.trail.length > 1 && (p.mode === 'dart' || p.mode === 'rocket' || g.settings.trail)) {
        const wide = p.mode === 'dart';
        ctx.beginPath();
        for (let i = 0; i < g.trail.length; i++) {
          const tp = g.trail[i];
          const x = this.sx(tp[0], cam), y = this.sy(tp[1], cam);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.lineWidth = wide ? U * 0.3 : U * 0.16;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.strokeStyle = wide ? g.icon.secondary : g.icon.primary;
        ctx.globalAlpha = 0.55;
        ctx.stroke();
        if (wide) {
          ctx.lineWidth = U * 0.1;
          ctx.strokeStyle = '#fff';
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
      // crawler teleport streak
      if (g.teleFx && g.time - g.teleFx.t < 0.25) {
        const k = 1 - (g.time - g.teleFx.t) / 0.25;
        const x = this.sx(g.teleFx.x + 0.5, cam);
        const y0 = this.sy(g.teleFx.y0 + 0.5, cam), y1 = this.sy(g.teleFx.y1 + 0.5, cam);
        ctx.fillStyle = `rgba(200,140,255,${0.6 * k})`;
        ctx.fillRect(x - U * 0.4, Math.min(y0, y1), U * 0.8, Math.abs(y1 - y0));
      }
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, U * 1.1);
      glow.addColorStop(0, 'rgba(255,255,255,0.18)');
      glow.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = glow;
      ctx.fillRect(cx - U * 1.2, cy - U * 1.2, U * 2.4, U * 2.4);
      drawPlayer(ctx, p.mode, cx, cy, U * 0.98, g.angle, g.icon, g.time, p.g < 0);
    }

    drawParticles(g) {
      const ctx = this.ctx, U = this.U, cam = g.cam;
      for (const q of g.particles) {
        const a = Math.max(0, q.life / q.max);
        ctx.globalAlpha = a;
        ctx.fillStyle = q.color;
        const s = q.size * U * (q.shrink ? a : 1);
        ctx.fillRect(this.sx(q.x, cam) - s / 2, this.sy(q.y, cam) - s / 2, s, s);
      }
      ctx.globalAlpha = 1;
      for (const r of g.rings) {
        const k = 1 - r.life / r.max;
        ctx.beginPath();
        ctx.arc(this.sx(r.x, cam), this.sy(r.y, cam), (r.r0 + k * r.r1) * U, 0, Math.PI * 2);
        ctx.strokeStyle = r.color;
        ctx.globalAlpha = 1 - k;
        ctx.lineWidth = U * 0.15 * (1 - k) + 1;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    drawCheckpoints(g) {
      const ctx = this.ctx, U = this.U, cam = g.cam;
      for (const c of g.checkpoints) {
        const x = this.sx(c.player.x + 0.5, cam), y = this.sy(c.player.y + 0.5, cam);
        if (x < -U || x > this.W + U) continue;
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = 'rgba(60,255,120,0.85)';
        ctx.fillRect(-U * 0.22, -U * 0.22, U * 0.44, U * 0.44);
        ctx.strokeStyle = '#063';
        ctx.lineWidth = 2;
        ctx.strokeRect(-U * 0.22, -U * 0.22, U * 0.44, U * 0.44);
        ctx.restore();
      }
    }

    drawAttemptText(g) {
      const ctx = this.ctx, U = this.U;
      const x = this.sx(g.attemptX, g.cam), y = this.sy(5.2, g.cam);
      if (x < -U * 12) return;
      ctx.font = `900 ${Math.round(U * 0.9)}px system-ui, "Segoe UI", sans-serif`;
      ctx.textAlign = 'left';
      ctx.lineWidth = U * 0.12;
      ctx.strokeStyle = 'rgba(0,0,0,0.6)';
      const text = g.practice ? 'Practice' : `Attempt ${g.attempt}`;
      ctx.strokeText(text, x, y);
      ctx.fillStyle = '#fff';
      ctx.fillText(text, x, y);
    }

    drawHud(g) {
      const ctx = this.ctx, W = this.W, dpr = this.dpr;
      const pct = Math.max(0, Math.min(1, g.player.x / g.level.length));
      const bw = Math.min(W * 0.4, 520 * dpr), bh = 12 * dpr;
      const bx = (W - bw) / 2, by = 14 * dpr;
      ctx.fillStyle = 'rgba(0,0,0,0.45)';
      ctx.fillRect(bx - 2 * dpr, by - 2 * dpr, bw + 4 * dpr, bh + 4 * dpr);
      const grad = ctx.createLinearGradient(bx, 0, bx + bw, 0);
      grad.addColorStop(0, g.practice ? '#3aff7c' : '#5af');
      grad.addColorStop(1, g.practice ? '#b6ffcf' : '#9ef');
      ctx.fillStyle = grad;
      ctx.fillRect(bx, by, bw * pct, bh);
      ctx.strokeStyle = 'rgba(255,255,255,0.9)';
      ctx.lineWidth = 2 * dpr;
      ctx.strokeRect(bx - 2 * dpr, by - 2 * dpr, bw + 4 * dpr, bh + 4 * dpr);
      if (g.settings.percent) {
        ctx.font = `800 ${Math.round(16 * dpr)}px system-ui, sans-serif`;
        ctx.textAlign = 'left';
        ctx.fillStyle = '#fff';
        ctx.fillText(`${Math.floor(pct * 100)}%`, bx + bw + 12 * dpr, by + bh);
      }
    }

    draw(g) {
      const ctx = this.ctx;
      ctx.save();
      if (g.shake > 0) ctx.translate((Math.random() - 0.5) * g.shake * this.U, (Math.random() - 0.5) * g.shake * this.U);
      this.drawBackground(g.cam, g.bgColor, g.pulse);
      this.drawAttemptText(g);
      this.drawObjects(g);
      this.drawGround(g.cam, g.groundColor, g.ceilAlpha, g.pulse);
      this.drawCheckpoints(g);
      if (!g.player.dead) this.drawPlayerWorld(g);
      this.visible(g.level, g.cam, (o) => { if (o.t.startsWith('p_')) this.drawPortal(o, g, false); });
      this.drawParticles(g);
      ctx.restore();
      if (g.flash > 0) {
        ctx.fillStyle = `rgba(255,255,255,${g.flash})`;
        ctx.fillRect(0, 0, this.W, this.H);
      }
      this.drawHud(g);
    }
  }

  window.Render = { Renderer, drawPlayer, drawFace, hexToRgb, mix, rgb, shade, DESIGNS };
})();
