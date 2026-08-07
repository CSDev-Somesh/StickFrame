# StickFrame — Resume Note (2026-08-03)

## Status: mid-session checkpoint

## What's running
- Frontend: http://localhost:3000 (Next.js, background proc — may need restart after reboot)
- Backend:  http://localhost:8001 (FastAPI on 8001 — SurrealDB docker was killed, port 8000 free)
  - Restart: `cd /home/kali/StickFrame && .venv/bin/python -c "import uvicorn; uvicorn.run('web.backend.main:app', host='0.0.0.0', port=8001)"`
- Frontend restart: `cd /home/kali/StickFrame/web/frontend && npm run dev`
- .env.local already points frontend to :8001

## Built this session (movie mode — phase 1)
- Engine: dialogue bubble rendering (speak → bubble, dormant — muted movie for now)
- Engine: `bg.set(color=...)` timeline event → per-frame background change
- Engine: follow-camera starts at target x (was panning in from edge — bug fixed)
- Compiler already had: `action` blocks (custom in-script moves), multi-scene timelines, camera cuts via `closeup.activate`
- Demo: /home/kali/StickFrame/scripts/movie_duel.sf — 2 scenes, custom uppercut action, bg change, camera cut. 228 frames @ 9.5s. Verified: renders, no bubbles, bg + cut work.
- Verify scripts: /tmp/hermes-verify-muted-movie.py (left on disk), /tmp/hermes-verify-movie-mode.py

## OPEN DECISION (Somesh + Hermes)
User wrote kungfu.sf-style script with 15 actions; engine only knows 7
(idle, walk, run, jump, wave, punch, fall). Unknown actions are SILENTLY
IGNORED (generator_system.py:107 `if action_name not in GENERATORS: return`).

12 missing actions in his script: turn, stance, adjust_outfit, step_left,
hand_wave, spin, low_stance, block, kick, spin_air, land, slide, energy_pose, bow

Two options proposed:
1. Define them as `action` blocks in the .sf (script carries moves, no Python)
2. Add as Python generators (looks better faster, but hardcoding)

Plus: make unknown actions ERROR LOUDLY instead of silent ignore? (one-line change)

## User prefs
- Muted movie for now: actions only, no dialogue. BGM/voices/dialogue = future.
- Goal: any .sf → full stickman movie, no hardcoded actions.
- Verified end-to-end through the actual render button path (POST /api/render → MP4).
