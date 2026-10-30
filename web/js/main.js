// Neon Pulse - game flow, input, menus, practice mode and save data.
(function () {
  'use strict';

  const DATA = window.GAME_DATA;
  const { Level, Player, step, STEP, SPEEDS, CEIL_MODES } = window.Engine;
  const { Renderer, drawPlayer, drawFace, hexToRgb, mix, DESIGNS } = window.Render;

  const COLORS = ['#5cff3a', '#3af0ff', '#ffe23a', '#ff5ad8', '#ff4040', '#ff9a2a', '#a45aff', '#3a7cff',
    '#ffffff', '#9aa4b8', '#2a2a2a', '#00c896', '#ff7ab0', '#c8ff3a', '#7a4a2a', '#ffd6a0'];

  // ---------------------------------------------------------------- save
  const SAVE_KEY = 'neonpulse.save.v1';
  const defaults = () => ({
    icon: { primary: '#5cff3a', secondary: '#3af0ff', design: 0 },
    settings: { music: 0.8, sfx: 0.8, percent: true, auto: false, trail: false },
    levels: {},
    jumps: 0,
    attempts: 0,
  });
  let save = defaults();
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      save = Object.assign(defaults(), s);
      save.icon = Object.assign(defaults().icon, s.icon);
      save.settings = Object.assign(defaults().settings, s.settings);
    }
  } catch (e) { /* storage unavailable: play without saving */ }
  function persist() {
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(save)); } catch (e) { /* ignore */ }
  }
  function stats(i) {
    const name = DATA.levels[i].name;
    if (!save.levels[name]) save.levels[name] = { attempts: 0, jumps: 0, best: 0, practice: 0, done: false, coins: 0 };
    return save.levels[name];
  }

  // ---------------------------------------------------------------- setup
  const canvas = document.getElementById('game');
  const R = new Renderer(canvas);
  const audio = new window.AudioEngine();
  audio.setVolumes(save.settings.music, save.settings.sfx);
  const $ = (id) => document.getElementById(id);

  let screen = 'main';
  let selected = 0;
  let G = null; // the running game, if any
  let menuTime = 0;
  const menuColor = { bg: hexToRgb('#1f5bff'), ground: hexToRgb('#0c34c9') };
  const menuShown = { bg: menuColor.bg.slice(), ground: menuColor.ground.slice() };

  // ---------------------------------------------------------------- input
  const held = new Set();
  let pressed = false;
  function pressStart(src) {
    audio.unlock();
    if (!held.has(src)) pressed = true;
    held.add(src);
  }
  function pressEnd(src) { held.delete(src); }

  const JUMP_KEYS = new Set(['Space', 'ArrowUp', 'KeyW', 'Enter', 'NumpadEnter']);
  window.addEventListener('keydown', (e) => {
    audio.unlock();
    if (screen === 'play' && JUMP_KEYS.has(e.code)) {
      e.preventDefault();
      if (!e.repeat) pressStart(e.code);
      return;
    }
    if (e.repeat) return;
    if (e.code === 'KeyF') toggleFullscreen();
    if (screen === 'play') {
      if (e.code === 'Escape' || e.code === 'KeyP') pause();
      else if (e.code === 'KeyR') restart(true);
      else if (e.code === 'KeyZ') addCheckpoint(true);
      else if (e.code === 'KeyX') removeCheckpoint();
    } else if (screen === 'pause') {
      if (e.code === 'Escape' || e.code === 'KeyP' || e.code === 'Space') resume();
      else if (e.code === 'KeyR') { resume(); restart(true); }
    } else if (screen === 'levels') {
      if (e.code === 'ArrowLeft') selectLevel(selected - 1);
      else if (e.code === 'ArrowRight') selectLevel(selected + 1);
      else if (e.code === 'Space' || e.code === 'Enter') startLevel(selected, false);
      else if (e.code === 'Escape') show('main');
    } else if (screen === 'main') {
      if (e.code === 'Space' || e.code === 'Enter') show('levels');
    } else if (screen === 'complete') {
      if (e.code === 'Space' || e.code === 'Enter') startLevel(G.index, G.practice);
      else if (e.code === 'Escape') exitToLevels();
    } else if (e.code === 'Escape') {
      show('main');
    }
  });
  window.addEventListener('keyup', (e) => pressEnd(e.code));
  canvas.addEventListener('mousedown', (e) => { if (e.button === 0 && screen === 'play') pressStart('mouse'); });
  window.addEventListener('mouseup', () => pressEnd('mouse'));
  canvas.addEventListener('touchstart', (e) => {
    e.preventDefault();
    if (screen !== 'play') return;
    for (const t of e.changedTouches) pressStart('t' + t.identifier);
  }, { passive: false });
  const touchEnd = (e) => { for (const t of e.changedTouches) pressEnd('t' + t.identifier); };
  canvas.addEventListener('touchend', touchEnd);
  canvas.addEventListener('touchcancel', touchEnd);
  window.addEventListener('blur', () => { held.clear(); if (screen === 'play') pause(); });
  window.addEventListener('resize', () => R.resize());
  document.addEventListener('pointerdown', () => audio.unlock(), { capture: true });

  function toggleFullscreen() {
    try {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    } catch (e) { /* not supported */ }
  }

  // ---------------------------------------------------------------- screens
  const SCREENS = ['main', 'levels', 'icons', 'settings', 'pause', 'complete'];
  function show(name) {
    screen = name;
    for (const s of SCREENS) $('screen-' + s).classList.toggle('hidden', s !== name);
    $('hud').classList.toggle('hidden', name !== 'play');
    if (name === 'main') updateTotals();
    if (name === 'levels') selectLevel(selected);
    if (name === 'icons') buildIconKit();
    if (name === 'settings') syncSettings();
    if (['main', 'levels', 'icons', 'settings'].includes(name)) {
      G = null;
      if (!audio.song || audio.song.data !== DATA.songs.menu) audio.play(DATA.songs.menu);
    }
  }

  document.querySelectorAll('[data-back]').forEach((b) => b.addEventListener('click', () => { audio.sfx('click'); show(b.dataset.back); }));
  $('btn-play').onclick = () => { audio.unlock(); audio.sfx('click'); show('levels'); };
  $('btn-icons').onclick = () => { audio.unlock(); audio.sfx('click'); show('icons'); };
  $('btn-settings').onclick = () => { audio.unlock(); audio.sfx('click'); show('settings'); };

  function updateTotals() {
    let stars = 0, coins = 0, done = 0;
    DATA.levels.forEach((lv, i) => {
      const s = stats(i);
      if (s.done) { stars += lv.stars; done++; }
      for (let c = 0; c < 3; c++) if ((s.coins >> c) & 1) coins++;
    });
    $('totals').innerHTML = `<span class="star">&#9733; ${stars}</span><span>&#9673; ${coins} / ${DATA.levels.length * 3}</span>` +
      `<span>${done} / ${DATA.levels.length} levels</span>`;
  }

  // ---------------------------------------------------------------- level select
  function selectLevel(i) {
    const n = DATA.levels.length;
    selected = ((i % n) + n) % n;
    const lv = DATA.levels[selected];
    const s = stats(selected);
    $('lvl-name').textContent = lv.name;
    $('lvl-stars').innerHTML = `<span class="diff">${lv.difficulty}</span>&#9733; ${lv.stars}`;
    $('lvl-coins').innerHTML = [0, 1, 2].map((c) => `<i class="${(s.coins >> c) & 1 ? 'got' : ''}"></i>`).join('');
    $('lvl-normal').style.width = s.best + '%';
    $('lvl-normal-txt').textContent = s.best + '%';
    $('lvl-practice').style.width = s.practice + '%';
    $('lvl-practice-txt').textContent = s.practice + '%';
    $('lvl-meta').textContent = `${Math.round(lv.seconds)}s long · ${s.attempts} attempts · ${s.jumps} jumps` + (s.done ? ' · completed' : '');
    const card = $('level-card');
    card.style.background = `linear-gradient(160deg, ${lv.colors[0][1]}dd, ${lv.colors[0][2]}cc 45%, rgba(8,12,40,0.88))`;
    const fc = $('face').getContext('2d');
    fc.clearRect(0, 0, 120, 120);
    drawFace(fc, lv.diff, 60, 64, 42);
    $('lvl-dots').innerHTML = DATA.levels.map((_, j) => `<i class="${j === selected ? 'on' : ''}"></i>`).join('');
    menuColor.bg = hexToRgb(lv.colors[0][1]);
    menuColor.ground = hexToRgb(lv.colors[0][2]);
  }
  $('lvl-prev').onclick = () => { audio.sfx('click'); selectLevel(selected - 1); };
  $('lvl-next').onclick = () => { audio.sfx('click'); selectLevel(selected + 1); };
  $('btn-start').onclick = () => startLevel(selected, false);
  $('btn-start-practice').onclick = () => startLevel(selected, true);
  let swipeX = null;
  $('screen-levels').addEventListener('touchstart', (e) => { swipeX = e.touches[0].clientX; }, { passive: true });
  $('screen-levels').addEventListener('touchend', (e) => {
    if (swipeX === null) return;
    const dx = e.changedTouches[0].clientX - swipeX;
    if (Math.abs(dx) > 60) selectLevel(selected + (dx < 0 ? 1 : -1));
    swipeX = null;
  });

  // ---------------------------------------------------------------- icon kit
  function iconButton(parent, drawFn, selectedNow, onPick) {
    const b = document.createElement('button');
    if (selectedNow) b.classList.add('sel');
    const c = document.createElement('canvas');
    c.width = 88; c.height = 88;
    b.appendChild(c);
    drawFn(c.getContext('2d'));
    b.onclick = () => { audio.sfx('click'); onPick(); buildIconKit(); };
    parent.appendChild(b);
  }
  function buildIconKit() {
    const ic = save.icon;
    const d = $('kit-designs'); d.innerHTML = '';
    DESIGNS.forEach((_, i) => iconButton(d, (ctx) => {
      drawPlayer(ctx, 'cube', 44, 44, 64, 0, Object.assign({}, ic, { design: i }), 0, false);
    }, ic.design === i, () => { ic.design = i; persist(); }));
    for (const [id, key] of [['kit-primary', 'primary'], ['kit-secondary', 'secondary']]) {
      const el = $(id); el.innerHTML = '';
      COLORS.forEach((col) => iconButton(el, (ctx) => {
        ctx.fillStyle = col; ctx.fillRect(10, 10, 68, 68);
        ctx.strokeStyle = '#000'; ctx.lineWidth = 5; ctx.strokeRect(10, 10, 68, 68);
      }, ic[key] === col, () => { ic[key] = col; persist(); }));
    }
    const pc = $('icon-preview').getContext('2d');
    pc.clearRect(0, 0, 560, 120);
    ['cube', 'rocket', 'ball', 'saucer', 'dart', 'mech', 'crawler'].forEach((m, i) => {
      drawPlayer(pc, m, 45 + i * 78, 60, 56, m === 'dart' ? -0.3 : 0, ic, 0.1, false);
    });
  }

  // ---------------------------------------------------------------- settings
  function syncSettings() {
    const s = save.settings;
    $('set-music').value = $('pause-music').value = s.music;
    $('set-sfx').value = $('pause-sfx').value = s.sfx;
    $('set-percent').checked = s.percent;
    $('set-auto').checked = s.auto;
    $('set-trail').checked = s.trail;
  }
  const onVolume = (el, key) => {
    el.addEventListener('input', () => {
      save.settings[key] = parseFloat(el.value);
      audio.setVolumes(save.settings.music, save.settings.sfx);
      persist();
    });
  };
  onVolume($('set-music'), 'music'); onVolume($('pause-music'), 'music');
  onVolume($('set-sfx'), 'sfx'); onVolume($('pause-sfx'), 'sfx');
  for (const [id, key] of [['set-percent', 'percent'], ['set-auto', 'auto'], ['set-trail', 'trail']]) {
    $(id).addEventListener('change', () => { save.settings[key] = $(id).checked; persist(); });
  }
  $('btn-reset').onclick = () => {
    if (!confirm('Reset all level progress? Your icon and settings are kept.')) return;
    save.levels = {}; save.jumps = 0; save.attempts = 0;
    persist();
    audio.sfx('click');
  };

  // ---------------------------------------------------------------- game
  function colorAt(lv, x) {
    let c = lv.colors[0];
    for (const t of lv.colors) if (t[0] <= x) c = t;
    return c;
  }

  function startLevel(i, practice) {
    audio.unlock();
    const data = DATA.levels[i];
    G = {
      index: i,
      data,
      level: new Level(data),
      practice,
      attempt: 0,
      checkpoints: [],
      particles: [],
      rings: [],
      trail: [],
      orbHits: new Map(),
      coinTimes: {},
      prevCoins: stats(i).coins,
      icon: save.icon,
      settings: save.settings,
      time: 0,
      acc: 0,
      lastCp: 0,
    };
    show('play');
    $('practice-controls').classList.toggle('hidden', !practice);
    restart(false);
  }

  function restart(manual) {
    if (!G) return;
    const p = new Player(G.level, G.data.startMode, G.data.startSpeed);
    G.player = p;
    G.attempt++;
    G.attemptX = 2;
    G.dead = false;
    G.deathTimer = 0;
    G.won = false;
    G.winTimer = 0;
    G.angle = 0;
    G.trail = [];
    G.particles = [];
    G.rings = [];
    G.orbHits = new Map();
    G.coinTimes = {};
    G.runTime = 0;
    G.jumps = 0;
    G.shake = 0;
    G.flash = 0;
    G.acc = 0;
    G.autoStep = 0;
    held.clear();
    pressed = false;
    const c = G.data.colors[0];
    G.bgColor = hexToRgb(c[1]);
    G.groundColor = hexToRgb(c[2]);
    G.cam = { x: p.x - camLead(), y: -2.2 };
    G.ceilAlpha = 0;
    if (G.practice) {
      G.checkpoints = [];
      if (!audio.song || audio.song.data !== DATA.songs.practice) audio.play(DATA.songs.practice);
    } else {
      audio.play(G.data.song, { delay: 0.02 });
    }
    const s = stats(G.index);
    s.attempts++;
    save.attempts++;
    persist();
    if (manual) audio.sfx('click');
  }

  function camLead() { return (R.W / R.U) * 0.3; }

  function respawn() {
    const cp = G.checkpoints[G.checkpoints.length - 1];
    if (!cp) { restart(false); return; }
    G.player = cp.player.clone();
    G.cam = { x: cp.cam.x, y: cp.cam.y };
    G.bgColor = cp.bg.slice();
    G.groundColor = cp.ground.slice();
    G.ceilAlpha = cp.ceil;
    G.angle = cp.angle;
    G.dead = false;
    G.trail = [];
    G.attempt++;
    G.acc = 0;
    stats(G.index).attempts++;
  }

  function addCheckpoint(manual) {
    if (!G || !G.practice || G.dead || G.won) return;
    const p = G.player;
    G.checkpoints.push({
      player: p.clone(), cam: { x: G.cam.x, y: G.cam.y }, bg: G.bgColor.slice(), ground: G.groundColor.slice(),
      ceil: G.ceilAlpha, angle: G.angle,
    });
    G.lastCp = G.time;
    if (manual) audio.sfx('checkpoint');
  }
  function removeCheckpoint() {
    if (!G || !G.practice) return;
    G.checkpoints.pop();
    audio.sfx('click');
  }
  $('btn-cp-add').onclick = (e) => { e.stopPropagation(); addCheckpoint(true); };
  $('btn-cp-del').onclick = (e) => { e.stopPropagation(); removeCheckpoint(); };
  for (const id of ['btn-cp-add', 'btn-cp-del', 'btn-pause']) {
    $(id).addEventListener('touchstart', (e) => e.stopPropagation(), { passive: true });
    $(id).addEventListener('mousedown', (e) => e.stopPropagation());
  }

  // ---- pause
  function progressBars(prefix) {
    const s = stats(G.index);
    $(prefix + '-normal').style.width = s.best + '%';
    $(prefix + '-normal-txt').textContent = s.best + '%';
    $(prefix + '-practice').style.width = s.practice + '%';
    $(prefix + '-practice-txt').textContent = s.practice + '%';
  }
  function pause() {
    if (!G || G.won) return;
    show('pause');
    $('pause-name').textContent = G.data.name;
    $('btn-toggle-practice').classList.toggle('on', G.practice);
    progressBars('pause');
    syncSettings();
    if (audio.ctx) audio.ctx.suspend();
  }
  function resume() {
    show('play');
    if (audio.ctx) audio.ctx.resume();
    G.acc = 0;
    last = performance.now();
  }
  $('btn-pause').onclick = (e) => { e.stopPropagation(); pause(); };
  $('btn-resume').onclick = resume;
  $('btn-restart').onclick = () => { resume(); restart(true); };
  $('btn-toggle-practice').onclick = () => {
    if (audio.ctx) audio.ctx.resume();
    const i = G.index;
    startLevel(i, !G.practice);
  };
  $('btn-exit').onclick = () => { if (audio.ctx) audio.ctx.resume(); exitToLevels(); };
  function exitToLevels() {
    audio.stop(0.2);
    show('levels');
  }
  $('btn-again').onclick = () => startLevel(G.index, G.practice);
  $('btn-done').onclick = exitToLevels;

  // ---- events from the physics
  function burst(x, y, n, colors, speed, life, size) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = speed * (0.3 + Math.random() * 0.7);
      G.particles.push({
        x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: life * (0.5 + Math.random() * 0.5), max: life,
        color: colors[i % colors.length], size: size * (0.5 + Math.random()), shrink: true, grav: 0,
      });
    }
  }
  function ring(x, y, color, r0, r1, life) { G.rings.push({ x, y, color, r0, r1, life, max: life }); }

  function handleEvents(p) {
    for (const ev of p.events) {
      const cx = p.x + 0.5, cy = p.y + 0.5;
      if (ev === 'jump' || ev === 'flip') {
        G.jumps++;
        if (p.mode === 'cube' || p.mode === 'mech' || p.mode === 'ball') burst(cx - 0.3, cy - 0.5 * p.g, 4, ['#fff'], 2, 0.3, 0.12);
      } else if (ev === 'orb') {
        for (const o of G.level.near(p.x)) if (p.used[o.id] && o.t.startsWith('orb_') && !G.orbHits.has(o.id)) G.orbHits.set(o.id, G.time);
        G.jumps++;
      } else if (ev === 'pad') {
        burst(cx, p.y, 8, ['#ffe23a', '#fff'], 4, 0.4, 0.12);
      } else if (ev === 'portal') {
        ring(cx, cy, 'rgba(255,255,255,0.9)', 0.4, 2.2, 0.35);
      } else if (ev === 'coin') {
        for (let c = 0; c < 3; c++) if (((p.coins >> c) & 1) && G.coinTimes[c] === undefined) G.coinTimes[c] = G.time;
        audio.sfx('coin');
        ring(cx, cy, '#ffc928', 0.3, 1.8, 0.4);
      } else if (ev === 'tele') {
        G.teleFx = { x: p.x, y0: p.tele[0], y1: p.tele[1], t: G.time };
      }
    }
    p.events.length = 0;
  }

  function die() {
    const p = G.player;
    G.dead = true;
    G.deathTimer = G.practice ? 0.65 : 1.0;
    const cx = p.x + 0.5, cy = p.y + 0.5;
    burst(cx, cy, 34, [G.icon.primary, G.icon.secondary, '#fff'], 9, 0.8, 0.22);
    ring(cx, cy, G.icon.primary, 0.3, 3, 0.5);
    ring(cx, cy, '#fff', 0.2, 1.8, 0.35);
    G.shake = 0.25;
    audio.sfx('death');
    const pct = Math.min(99, Math.floor((p.x / G.level.length) * 100));
    const s = stats(G.index);
    if (G.practice) s.practice = Math.max(s.practice, pct);
    else {
      if (pct > s.best && pct >= 1) showToast(`New best: ${pct}%`);
      s.best = Math.max(s.best, pct);
    }
    s.jumps += G.jumps; save.jumps += G.jumps; G.jumps = 0;
    persist();
    if (!G.practice) audio.stop(0.15);
  }

  function win() {
    const p = G.player;
    G.won = true;
    G.winTimer = 1.6;
    G.flash = 0.6;
    for (let i = 0; i < 4; i++) ring(p.x + 0.5, p.y + 0.5, i % 2 ? '#fff' : G.icon.primary, 0.5 + i * 0.4, 6 + i * 2, 0.8 + i * 0.15);
    burst(p.x + 0.5, p.y + 0.5, 60, ['#fff', '#ffe23a', G.icon.primary, G.icon.secondary], 12, 1.2, 0.2);
    audio.stop(1.2);
    audio.sfx('win');
    const s = stats(G.index);
    s.jumps += G.jumps; save.jumps += G.jumps;
    let reward = '';
    if (G.practice) {
      s.practice = 100;
    } else {
      if (!s.done) reward = `+${G.data.stars} &#9733;`;
      s.done = true;
      s.best = 100;
      const newCoins = p.coins & ~s.coins;
      s.coins |= p.coins;
      if (newCoins) reward += (reward ? ' &nbsp; ' : '') + 'New coins!';
    }
    persist();
    G.reward = reward;
  }

  function showComplete() {
    show('complete');
    const p = G.player;
    $('complete-title').textContent = G.practice ? 'Practice Complete!' : 'Level Complete!';
    const secs = G.runTime;
    $('complete-stats').innerHTML =
      `<span>Attempts</span><span>${G.attempt}</span>` +
      `<span>Jumps</span><span>${G.jumpsTotalRun || 0}</span>` +
      `<span>Time</span><span>${Math.floor(secs / 60)}:${String(Math.floor(secs % 60)).padStart(2, '0')}</span>`;
    $('complete-coins').innerHTML = [0, 1, 2].map((c) => `<i class="${(p.coins >> c) & 1 && !G.practice ? 'got' : ''}"></i>`).join('');
    $('complete-reward').innerHTML = G.reward || (G.practice ? 'Now try it in normal mode!' : '');
  }

  let toastTimer = null;
  function showToast(text) {
    const t = $('toast');
    t.textContent = text;
    t.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add('hidden'), 1400);
  }

  // ---- per-frame update
  function update(dt) {
    G.time += dt;
    const p = G.player;
    if (!G.dead && !G.won) {
      G.acc += dt;
      let steps = 0;
      while (G.acc >= STEP && steps < 30) {
        let h = held.size > 0;
        let pr = pressed;
        if (G.auto) {
          // Debug autoplay: one recorded input per two physics steps.
          const i = Math.floor(G.autoStep / 2);
          h = G.auto[i] === 1;
          pr = h && G.autoStep % 2 === 0 && G.auto[i - 1] !== 1;
          G.autoStep++;
        }
        step(p, G.level, h || pr, pr);
        pressed = false;
        G.acc -= STEP;
        steps++;
        G.runTime += STEP;
        if (p.events.length) handleEvents(p);
        updateAngle(p, STEP);
        if (p.dead) { die(); break; }
        if (p.won) { G.jumpsTotalRun = G.jumps; win(); break; }
      }
      if (G.practice && G.settings.auto && !G.dead && G.time - G.lastCp > 2.5 &&
          (p.onGround || CEIL_MODES.has(p.mode)) && p.x > 4) addCheckpoint(false);
    } else if (G.dead) {
      G.deathTimer -= dt;
      if (G.deathTimer <= 0) {
        if (G.practice) respawn(); else restart(false);
      }
    } else if (G.won) {
      p.x += SPEEDS[p.speed] * dt;
      G.winTimer -= dt;
      if (G.winTimer <= 0 && screen === 'play') showComplete();
    }

    // camera
    const lead = camLead();
    G.cam.x = p.x - lead;
    const corridor = CEIL_MODES.has(p.mode);
    let ty;
    if (corridor) ty = -1.0;
    else {
      const view = R.H / R.U;
      ty = Math.max(-2.2, Math.min(G.cam.y, p.y - view * 0.25));
      if (p.y + 1 > G.cam.y + view * 0.72) ty = p.y + 1 - view * 0.72;
      if (p.y < G.cam.y + view * 0.25) ty = Math.max(-2.2, p.y - view * 0.25);
    }
    G.cam.y += (ty - G.cam.y) * Math.min(1, dt * 5);
    G.ceilAlpha += ((corridor ? 1 : 0) - G.ceilAlpha) * Math.min(1, dt * 6);

    // colours
    const c = colorAt(G.data, p.x);
    const k = Math.min(1, dt * 2.5);
    G.bgColor = mix(G.bgColor, hexToRgb(c[1]), k);
    G.groundColor = mix(G.groundColor, hexToRgb(c[2]), k);
    G.pulse = G.practice ? audio.pulse() * 0.5 : audio.pulse();

    // trail
    if (!G.dead) {
      G.trail.push([p.x + 0.5 - (p.mode === 'dart' ? 0.2 : 0.45), p.y + 0.5]);
      const max = p.mode === 'dart' ? 60 : 14;
      while (G.trail.length > max) G.trail.shift();
      if (p.onGround && (p.mode === 'cube' || p.mode === 'mech') && Math.random() < 0.5) {
        G.particles.push({
          x: p.x + 0.1, y: p.g > 0 ? p.y + 0.08 : p.y + 0.92, vx: -2 - Math.random() * 2, vy: (Math.random() * 1.5) * p.g,
          life: 0.3, max: 0.3, color: G.icon.primary, size: 0.1, shrink: true, grav: 0,
        });
      }
      if (p.mode === 'rocket' || p.mode === 'saucer') {
        G.particles.push({
          x: p.x + 0.05, y: p.y + 0.35, vx: -4, vy: (Math.random() - 0.5) * 2, life: 0.35, max: 0.35,
          color: Math.random() < 0.5 ? '#ffb43a' : '#ff6a2a', size: 0.14, shrink: true, grav: 0,
        });
      }
    }
    for (const q of G.particles) { q.x += q.vx * dt; q.y += q.vy * dt; q.vx *= 0.97; q.vy *= 0.97; q.life -= dt; }
    G.particles = G.particles.filter((q) => q.life > 0);
    for (const r of G.rings) r.life -= dt;
    G.rings = G.rings.filter((r) => r.life > 0);
    G.shake = Math.max(0, G.shake - dt);
    G.flash = Math.max(0, G.flash - dt * 1.5);
  }

  function updateAngle(p, dt) {
    const g = p.g;
    const sp = SPEEDS[p.speed];
    if (p.mode === 'cube') {
      if (p.onGround) {
        const q = Math.PI / 2;
        const target = Math.round(G.angle / q) * q;
        G.angle += (target - G.angle) * Math.min(1, dt * 30);
      } else {
        G.angle += g * 7.4 * dt;
      }
    } else if (p.mode === 'rocket') {
      G.angle = -Math.atan2(p.vy, sp) * 0.8;
    } else if (p.mode === 'dart') {
      G.angle = -Math.atan2(p.vy, sp);
    } else if (p.mode === 'ball') {
      G.angle += g * sp * 1.6 * dt;
    } else if (p.mode === 'saucer') {
      G.angle = -p.vy * 0.015;
    } else {
      G.angle = 0;
    }
  }

  // ---------------------------------------------------------------- main loop
  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (G && (screen === 'play' || screen === 'complete')) {
      if (screen === 'play') update(dt);
      else G.time += dt;
      R.draw(G);
    } else if (G && screen === 'pause') {
      R.draw(G);
    } else {
      menuTime += dt;
      menuShown.bg = mix(menuShown.bg, menuColor.bg, Math.min(1, dt * 2));
      menuShown.ground = mix(menuShown.ground, menuColor.ground, Math.min(1, dt * 2));
      R.drawMenuBackground(menuTime, menuShown.bg, menuShown.ground, audio.pulse());
      if (screen === 'main') drawMenuRunner(menuTime);
    }
    requestAnimationFrame(frame);
  }

  function drawMenuRunner(t) {
    const U = R.U;
    const phase = t % 1.25;
    const air = phase < 0.42;
    const h = air ? 21 * phase - 50 * phase * phase : 0;
    const x = R.W * 0.18;
    const y = R.H - (2.2 + h + 0.5) * U;
    drawPlayer(R.ctx, 'cube', x, y, U * 0.98, air ? (phase / 0.42) * Math.PI : 0, save.icon, t, false);
  }

  // The menu cycles through each level's colours.
  setInterval(() => {
    if (screen === 'main' || screen === 'icons' || screen === 'settings') {
      const lv = DATA.levels[Math.floor(Math.random() * DATA.levels.length)];
      menuColor.bg = hexToRgb(lv.colors[0][1]);
      menuColor.ground = hexToRgb(lv.colors[0][2]);
    }
  }, 6000);

  show('main');
  requestAnimationFrame(frame);

  // Expose a tiny hook for automated smoke tests.
  window.NeonPulse = {
    startLevel,
    autoplay(i, inputs) { startLevel(i, false); G.auto = inputs; G.autoStep = 0; },
    get game() { return G; },
    get screen() { return screen; },
  };
})();
