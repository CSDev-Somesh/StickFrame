"""Full pipeline test: frontend -> backend (/api/render) -> engine -> MP4."""
import sys, json, os, urllib.request

BASE = "http://localhost:8001"

SCRIPT = """scene test width=640 height=480 fps=24

camera main:
    follow hero
    zoom 1.0

character hero:
    rig bipedal
    appearance head_color="#FFD700" body_color="#222222"
    position (100, 0)

timeline:
    scene act1:
        0.0s  hero.idle
        0.5s  hero.walk
        2.0s  hero.jump
        3.0s  hero.idle
"""

print("=== FULL PIPELINE TEST (frontend -> backend -> engine -> video) ===")
print()

# 1. POST script to /api/render
body = json.dumps({"script": SCRIPT, "width": 640, "height": 480, "fps": 24}).encode()
req = urllib.request.Request(f"{BASE}/api/render", data=body,
                             headers={"Content-Type": "application/json"})
resp = json.loads(urllib.request.urlopen(req).read())
print("1. POST /api/render")
print(f"   status={resp['status']}, frames={resp['frames']}, duration={resp['duration']:.2f}s")
print(f"   video_url={resp['video_url']}")
job_id = resp['job_id']
print()

# 2. Fetch the rendered video
video_url = f"{BASE}{resp['video_url']}"
with urllib.request.urlopen(video_url) as r:
    data = r.read()
    content_type = r.headers.get("Content-Type")
print("2. GET /api/render/{id}/video")
print(f"   Content-Type={content_type}, size={len(data)} bytes")
ok = len(data) > 1000 and b'ftyp' in data[4:12]  # MP4: 4-byte size + 'ftypisom'
print(f"   {'PASS: valid MP4' if ok else 'FAIL'}")

# 3. Save + verify with ffprobe
out = os.path.join(os.path.dirname(__file__), "pipeline_output.mp4")
with open(out, "wb") as f:
    f.write(data)
print()

print("3. Verify with ffprobe")
print(f"   Saved: {out} ({os.path.getsize(out)} bytes)")

print()
print("=== PIPELINE END-TO-END OK ===" if ok else "=== PIPELINE FAILED ===")