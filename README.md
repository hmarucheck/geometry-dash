# Neon Pulse

An original rhythm auto-runner platformer, written in several languages. Your
icon slides forward on its own to the beat; you click or tap to get past
spikes, saws, portals and gravity flips. Every level has its own soundtrack,
and both the browser and desktop versions generate the music from note data.

Neon Pulse is inspired by the rhythm-platformer genre. It is **not** affiliated
with or a copy of any existing game: the levels, art, music and names are all
original.

## Play it

### In a browser (HTML / CSS / JavaScript)

Open `web/index.html` in any modern browser. You don't need to install
anything or run a server. It works with mouse, keyboard and touch screens.

### On the desktop (Python + pygame)

```bash
cd python
pip install -r requirements.txt
python3 play.py
```

Both versions use the same levels, physics and songs.

## Controls

| Action | Keys |
| --- | --- |
| Jump / fly / flip | Click, tap, `Space`, `↑`, `W` (hold for continuous jumps) |
| Pause | `Esc` or `P` |
| Restart | `R` |
| Practice checkpoint (place / remove) | `Z` / `X`, or the on-screen buttons |
| Fullscreen | `F` |

## Features

- **8 levels** from Easy to Demon: *First Light, Neon Steps, Gravity Well,
  Skyline Drift, Zigzag Rush, Iron Stride, Crystal Cavern, Final Voltage*
- **A different song for every level**, each with its own tempo, key, scale,
  drums and instruments, plus menu and practice tracks
- **7 forms**, each with its own controls:
  | Form | Control |
  | --- | --- |
  | Cube | Tap to jump, hold to keep bouncing |
  | Rocket | Hold to rise, release to fall |
  | Ball | Tap to flip gravity while touching the ground |
  | Saucer | Tap to flap upwards (works in mid-air) |
  | Dart | Hold to fly diagonally up, release to fly diagonally down |
  | Mech | Hold longer for a higher jump |
  | Crawler | Tap to teleport straight to the floor or ceiling |
- **Portals:** form portals, gravity portals (up, down, flip) and five speed
  portals (0.8× to 1.85×)
- **Orbs:** yellow, pink, red, blue (flip), green (flip and dash) and black
  (slam down). Click while touching one.
- **Pads:** yellow, pink, red and blue (flip). These trigger on contact.
- **Hazards:** spikes, small spikes, hanging spikes and spinning saws
- **3 secret coins** per level, plus stars for completing levels
- **Practice mode** with checkpoints, optional auto-checkpoints and its own
  music
- **Icon kit:** 10 cube designs, 16 primary and 16 secondary colours, used
  across all 7 forms
- Attempt counter, progress bar, best % in normal and practice mode, jump
  stats, colour changes during levels, beat-pulsing objects, particles and
  death/victory effects
- Progress saves automatically (browser storage on the web, and
  `~/.neonpulse_save.json` on desktop)

## Every level is proven beatable

The levels are not hand-tuned by trial and error. `tools/build_levels.py`
grows each level one obstacle pattern at a time. After each pattern, a bot
(`tools/solve.py`) plays it with the real physics. The bot controls two
copies of the player at once: one gets its inputs on time and the other gets
them **3–6 frames late** (depending on difficulty). A pattern only stays if
both survive, starting from at least a quarter of the ways the player could
reasonably arrive. That rules out frame-perfect jumps and patterns that only
work with one lucky approach. Coins are checked the same way.

## Languages and layout

| Part | Language | Files |
| --- | --- | --- |
| Browser game | JavaScript, HTML, CSS | `web/` |
| Real-time music synth | JavaScript (Web Audio API) | `web/js/audio.js` |
| Desktop game | Python (pygame) | `python/neonpulse/game.py` |
| Offline music synth | Python (numpy) | `python/neonpulse/synth.py` |
| Reference physics | Python, ported line-by-line to JS | `python/neonpulse/physics.py`, `web/js/engine.js` |
| Level generator and composer | Python | `tools/build_levels.py`, `tools/compose.py` |
| Beatability prover | Python | `tools/solve.py` |
| Physics parity checker | JavaScript (Node) | `tools/check_parity.js` |
| Level data (shared) | JSON | `levels/levels.json` (also `web/js/levels.js`) |

## Rebuilding the levels

```bash
python3 tools/build_levels.py      # regenerate levels + songs (uses all CPU cores, takes several minutes)
python3 tools/solve.py --coins     # re-check every level and coin from scratch
node tools/check_parity.js         # check the JavaScript physics matches Python exactly
```

To change a level, edit its entry in `LEVELS` in `tools/build_levels.py`
(sections, speed, colours and song settings), then rebuild.
