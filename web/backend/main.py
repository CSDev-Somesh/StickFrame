"""StickFrame Web API — FastAPI backend that wraps the Python engine."""
import os, sys, uuid, tempfile, shutil, json, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Ensure engine is importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# Fresh-engine loader (same as preview lab)
_ENGINE_LOCK = threading.Lock()

def fresh_engine():
    """Purge engine/compiler modules from sys.modules, then import fresh."""
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
                if "deadlock" in str(e).lower() and attempt < 2:
                    import time
                    time.sleep(0.05 * (attempt + 1))
                    continue
                raise

app = FastAPI(title="StickFrame API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RENDER_DIR = Path("/tmp/stickframe-renders")
RENDER_DIR.mkdir(exist_ok=True)

class RenderRequest(BaseModel):
    script: str
    width: int = 800
    height: int = 600
    fps: int = 24

class RenderResponse(BaseModel):
    job_id: str
    status: str
    frames: int = 0
    duration: float = 0.0
    video_url: str = ""

@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "StickFrame"}

@app.post("/api/render", response_model=RenderResponse)
def render(req: RenderRequest):
    StickFrameEngine, _ = fresh_engine()

    job_id = str(uuid.uuid4())[:8]
    job_dir = RENDER_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    # Write script to temp file
    sf_path = job_dir / "scene.sf"
    sf_path.write_text(req.script)

    output_path = str(job_dir / "output.mp4")

    try:
        e = StickFrameEngine(fps=req.fps, width=req.width, height=req.height)
        info = e.load_and_render_script(str(sf_path), output_path)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))

    return RenderResponse(
        job_id=job_id,
        status="done",
        frames=info["frames"],
        duration=info["duration"],
        video_url=f"/api/render/{job_id}/video",
    )

@app.get("/api/render/{job_id}/video")
def get_video(job_id: str):
    video_path = RENDER_DIR / job_id / "output.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Render job not found")
    return FileResponse(str(video_path), media_type="video/mp4",
                        filename=f"stickframe_{job_id}.mp4")

@app.get("/api/render/{job_id}/status")
def get_status(job_id: str):
    video_path = RENDER_DIR / job_id / "output.mp4"
    sf_path = RENDER_DIR / job_id / "scene.sf"
    if not sf_path.exists():
        raise HTTPException(status_code=404, detail="Render job not found")
    if video_path.exists():
        size = video_path.stat().st_size
        return {"job_id": job_id, "status": "done", "size_bytes": size}
    return {"job_id": job_id, "status": "processing"}

@app.get("/api/examples")
def list_examples():
    examples_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    examples = {}
    for f in sorted(examples_dir.glob("*.sf")):
        examples[f.stem] = f.read_text()
    return {"examples": examples}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)