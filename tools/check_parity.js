#!/usr/bin/env node
// Replays the solver's winning inputs (tools/solutions/*.json) through the
// JavaScript engine and checks that it ends in exactly the same state as the
// Python reference physics. Run after tools/solve.py:
//
//   node tools/check_parity.js

'use strict';
const fs = require('fs');
const path = require('path');
const Engine = require('../web/js/engine.js');

const data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'levels', 'levels.json'), 'utf8'));
const dir = path.join(__dirname, 'solutions');
let failed = 0;
for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.json')).sort()) {
  const sol = JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8'));
  const lvlData = data.levels[sol.level];
  const lvl = new Engine.Level(lvlData);
  const p = new Engine.Player(lvl, lvlData.startMode, lvlData.startSpeed);
  let prev = 0;
  outer: for (const v of sol.inputs) {
    const h = v === 1;
    for (let i = 0; i < sol.every; i++) {
      Engine.step(p, lvl, h, h && !prev && i === 0);
      if (p.dead || p.won) break outer;
    }
    prev = v;
  }
  const same = p.won === sol.final.won && p.x === sol.final.x && p.y === sol.final.y && p.vy === sol.final.vy;
  console.log(`${same ? 'OK  ' : 'FAIL'} ${lvlData.name}: js won=${p.won} x=${p.x} y=${p.y}` +
    (same ? '' : ` | python won=${sol.final.won} x=${sol.final.x} y=${sol.final.y}`));
  if (!same) failed++;
}
process.exit(failed ? 1 : 0);
