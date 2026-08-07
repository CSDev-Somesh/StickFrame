"""StickFrame Live Preview Lab — real-time stickman design feedback loop.

How it works:
  - Every /api/preview request builds a FRESH engine (engine modules are
    re-imported from disk), so editing engine code shows up on the next poll.
  - The web page polls every ~600ms with a cache-buster and re-renders.
  - Camera follows the character so walk/run stay centered.

Run:
  .venv/bin/python web/backend/preview_lab.py
  → http://localhost:8080
"""

import io
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, Response

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FPS = 60
CANVAS = 640

app = FastAPI(title="StickFrame Preview Lab", version="0.1.0")


# ─── Fresh-engine loader (live code reload) ───────────────────

# The purge + re-import mutates global sys.modules, so concurrent requests
# (browser poll + API calls) must serialize — otherwise one thread deletes
# modules another is mid-import of → KeyError 500s.
_ENGINE_LOCK = threading.Lock()

def fresh_engine():
    """Purge engine/compiler modules from sys.modules, then import fresh.

    This is what makes the preview 'real-time': every request reflects the
    current state of the code on disk, no server restart needed.
    """
    with _ENGINE_LOCK:
        for attempt in range(3):
            try:
                for mod in list(sys.modules):
                    if mod == "engine" or mod.startswith("engine.") or \
                       mod == "compiler" or mod.startswith("compiler."):
                        del sys.modules[mod]
                from engine import StickFrameEngine
                from engine.core.components import Camera
                return StickFrameEngine, Camera
            except RuntimeError as e:
                # Python 3.13 importlib can raise _DeadlockError when a
                # hot-reload import races another thread's partial import.
                # It's transient — purge again and retry.
                if "deadlock" in str(e).lower() and attempt < 2:
                    import time
                    time.sleep(0.05 * (attempt + 1))
                    continue
                raise


def engine_version() -> str:
    """Latest mtime across engine+compiler source — used to detect code edits."""
    newest = 0.0
    for base in (ROOT / "engine", ROOT / "compiler"):
        for f in base.rglob("*.py"):
            newest = max(newest, f.stat().st_mtime)
    return f"{newest:.3f}"


# ─── Rendering ────────────────────────────────────────────────

def render_preview(action: str, t: float, scale: float, joints: bool,
                   width: int, height: int, show_floor: bool,
                   parts: str = "all") -> bytes:
    StickFrameEngine, Camera = fresh_engine()

    e = StickFrameEngine(fps=FPS, width=width, height=height)
    # Place, then snap hips so the BOTTOM of the foot circles rests exactly on
    # the floor line (ground_offset is computed from the skeleton rest pose).
    eid = e.create_character("hero", x=width / 2, y=0.0,
                             head_color="#FFD700", body_color="#333333",
                             scale=scale)
    # Part-by-part rig viewer: restrict rendering to the requested body parts
    # (comma-separated, e.g. "head,legs"). "all" = full body.
    if parts and parts != "all":
        e.entities[eid]["appearance"].visible_parts = set(
            p.strip() for p in parts.split(",") if p.strip())
    phys = e.entities[eid]["physics"]
    e.entities[eid]["position"].y = (height - 20) - phys.ground_offset
    # Camera follows the character horizontally only — y pinned to screen
    # center so the character stays grounded on the fixed floor line
    e.create_entity({"camera": Camera(target_entity=eid, smooth_speed=0.0,
                                      active=True, follow_y=False,
                                      current_y=height / 2), "name": "cam"})

    e.play_action(eid, action)

    # Step physics+animation until we reach time t
    steps = int(round(t * FPS))
    dt = 1.0 / FPS
    frame = None
    for _ in range(steps):
        frame = e.step(dt)

    # Always render one frame (even at t=0)
    if frame is None:
        frame = e.step(dt)

    # Optional subtle floor line so foot placement is easy to judge
    if show_floor:
        from PIL import ImageDraw
        d = ImageDraw.Draw(frame)
        gy = height - 20
        d.line([(20, gy), (width - 20, gy)], fill="#CCCCCC", width=2)

    buf = io.BytesIO()
    frame.save(buf, format="PNG")
    return buf.getvalue()


# ─── API ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(PAGE_HTML)


@app.get("/api/actions")
def actions():
    _, _ = fresh_engine()
    from engine.animation.generators import GENERATORS, generator_names
    out = {}
    for name in generator_names():
        _, has_pos, defaults = GENERATORS[name]
        dur = defaults.get("duration", 2.0)
        loop = name in ("idle", "walk", "run")
        out[name] = {"duration": dur, "loop": loop, "moves": has_pos}
    return {"actions": out, "version": engine_version()}


@app.get("/api/preview")
def preview(
    action: str = Query("idle"),
    t: float = Query(0.0, ge=0.0, le=10.0),
    scale: float = Query(4.0, ge=4.0, le=8.0),
    joints: int = Query(1, ge=0, le=1),
    floor: int = Query(1, ge=0, le=1),
    parts: str = Query("all"),
    w: int = Query(CANVAS, ge=200, le=1024),
    h: int = Query(CANVAS, ge=200, le=1024),
):
    try:
        png = render_preview(action, t, scale, bool(joints), w, h, bool(floor), parts)
    except Exception as ex:
        return Response(status_code=500, content=f"render error: {ex}")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store", "X-Engine-Version": engine_version()})


# ─── Page ─────────────────────────────────────────────────────

PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>StickFrame — Live Preview Lab</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { height:100%; }
  body {
    background:#ffffff;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    display:flex; flex-direction:column;
    color:#222;
  }
  header {
    padding:10px 18px;
    border-bottom:1px solid #eee;
    display:flex; align-items:center; gap:14px; flex-wrap:wrap;
    background:#fafafa;
  }
  header h1 { font-size:16px; font-weight:600; }
  .badge {
    font-size:11px; padding:3px 9px; border-radius:999px;
    background:#e8f5e9; color:#1b5e20; border:1px solid #a5d6a7;
  }
  .badge.flash { background:#fff3e0; color:#e65100; border-color:#ffcc80; }
  #version { font-size:11px; color:#888; }
  .controls {
    display:flex; gap:16px; align-items:center; flex-wrap:wrap;
    padding:10px 18px; border-bottom:1px solid #eee; background:#fff;
  }
  .ctl { display:flex; align-items:center; gap:6px; font-size:13px; }
  .ctl label { color:#555; font-weight:500; }
  select, input[type=range] { accent-color:#222; }
  select {
    padding:4px 8px; border:1px solid #ccc; border-radius:6px;
    font-size:13px; background:#fff;
  }
  button {
    padding:5px 14px; border:1px solid #222; background:#222; color:#fff;
    border-radius:6px; font-size:13px; cursor:pointer;
  }
  button:hover { background:#444; }
  .part {
    padding:4px 10px; border:1px solid #bbb; background:#fff; color:#333;
    border-radius:999px; font-size:12px;
  }
  .part.active { background:#222; color:#fff; border-color:#222; }
  .part.full { border-style:dashed; }
  .part.full.active { background:#e65100; border-color:#e65100; color:#fff; }
  .stage {
    flex:1; display:flex; align-items:center; justify-content:center;
    min-height:0; padding:10px;
  }
  #stickman {
    max-width:100%; max-height:100%;
    image-rendering:auto;
    box-shadow:0 0 0 1px #f0f0f0;
  }
  footer {
    padding:8px 18px; font-size:11px; color:#999;
    border-top:1px solid #eee; background:#fafafa;
  }
</style>
</head>
<body>
<header>
  <h1>StickFrame — Live Preview Lab</h1>
  <span class="badge" id="livebadge">● LIVE</span>
  <span id="version">engine v-</span>
</header>

<div class="controls">
  <div class="ctl">
    <label>Scale</label>
    <input type="range" id="scale" min="4.0" max="8.0" step="0.1" value="4.0">
    <span id="scaleval">4.0</span>
  </div>
  <div class="ctl">
    <label><input type="checkbox" id="joints" checked> Joints</label>
    <label><input type="checkbox" id="floor" checked> Floor</label>
  </div>
  <div class="ctl" id="partbox">
    <label>Parts:</label>
    <button class="part" data-part="head">Head</button>
    <button class="part" data-part="torso">Torso</button>
    <button class="part" data-part="arms">Arms</button>
    <button class="part" data-part="legs">Legs</button>
    <button id="fullbody" class="part full" data-part="all">Full Body</button>
  </div>
</div>

<div class="stage">
  <img id="stickman" alt="stickman preview">
</div>

<footer>
  Edit engine code on disk → this preview updates automatically (polls every 600ms).
</footer>

<script>
const img = document.getElementById('stickman');
const scaleEl = document.getElementById('scale');
const scaleVal = document.getElementById('scaleval');
const jointsEl = document.getElementById('joints');
const floorEl = document.getElementById('floor');
const versionEl = document.getElementById('version');
const badge = document.getElementById('livebadge');

let engineV = '';
const ACTION = 'idle';

// ── Part-by-part rig viewer ─────────────────────────────
// Clicking a part shows ONLY that part (solo view). Full Body shows
// everything. Real-time: refresh() runs on every click + every 600ms poll.
const partButtons = document.querySelectorAll('.part[data-part]');
const fullBtn = document.getElementById('fullbody');
let visibleParts = new Set(['head', 'torso', 'arms', 'legs']); // full body default

function updatePartUI() {
  const allOn = visibleParts.size === 4;
  partButtons.forEach(btn => {
    btn.classList.toggle('active', visibleParts.size === 1 && visibleParts.has(btn.dataset.part));
  });
  fullBtn.classList.toggle('active', allOn);
}

function partsParam() {
  if (visibleParts.size === 0) return 'none';
  if (visibleParts.size === 4) return 'all';
  return [...visibleParts].join(',');
}

// Solo view: click a part -> ONLY that part renders
partButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    visibleParts = new Set([btn.dataset.part]);
    updatePartUI();
    refresh();
  });
});

// Full Body: show everything
fullBtn.addEventListener('click', () => {
  visibleParts = new Set(['head', 'torso', 'arms', 'legs']);
  updatePartUI();
  refresh();
});
updatePartUI();

function refresh() {
  const q = new URLSearchParams({
    action: ACTION,
    t: 0.0,
    scale: scaleEl.value,
    joints: jointsEl.checked ? '1' : '0',
    floor: floorEl.checked ? '1' : '0',
    parts: partsParam(),
  });
  img.src = '/api/preview?' + q.toString() + '&_=' + Date.now();
}

// Poll for new engine code — flash badge when a change is detected
setInterval(async () => {
  try {
    const r = await fetch('/api/actions');
    const data = await r.json();
    if (data.version !== engineV) {
      engineV = data.version;
      versionEl.textContent = 'engine v-' + data.version.slice(-6);
      badge.textContent = '● ENGINE UPDATED';
      badge.classList.add('flash');
      setTimeout(() => {
        badge.textContent = '● LIVE';
        badge.classList.remove('flash');
      }, 1500);
    }
  } catch (e) {}
}, 600);

// Refresh image every 600ms (always, so code edits appear within ~1s)
setInterval(refresh, 600);

scaleEl.addEventListener('input', () => {
  scaleVal.textContent = scaleEl.value;
  refresh();
});
jointsEl.addEventListener('change', refresh);
floorEl.addEventListener('change', refresh);

refresh();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
