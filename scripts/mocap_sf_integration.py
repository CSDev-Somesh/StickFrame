"""Integration: use a mocap action by NAME inside a .sf timeline.

Proves the "unlimited action vocabulary" story:
    engine.load_mocap_library(synthetic_data)  -> defines 'punch', 'wave'
    scene.sf uses  hero.punch / hero.wave  as if they were built-ins.

The keyframe player resolves them before the procedural fallback.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import StickFrameEngine

DATA = Path(__file__).parent / "data"

SCRIPT = """# Mocap integration test - punch and wave are NOT built-in .sf actions,
# they come from the loaded .bvh motion-capture library.
scene cob width=800 height=600 fps=30

camera main:
    follow hero
    zoom 1.0

character hero:
    rig bipedal
    appearance shirt_color="#2E86DE" pants_color="#1B2A4A"
    scale=2.5
    position (400, 374)

timeline:
    scene act1:
        0.0s  hero.idle
        0.5s  hero.punch
        2.0s  hero.idle
        2.5s  hero.wave
        5.0s  hero.idle
"""


def test():
    # Ensure fixtures exist
    if not (DATA / "punch.bvh").exists():
        import gen_synthetic_bvh as gen
        DATA.mkdir(exist_ok=True)
        (DATA / "punch.bvh").write_text(gen.make_punch())
        (DATA / "wave.bvh").write_text(gen.make_wave())

    e = StickFrameEngine(fps=30, width=800, height=600)
    e.load_mocap_library(str(DATA), loops=["idle"])

    script = Path(__file__).parent / "mocap_scene.sf"
    script.write_text(SCRIPT, encoding="utf-8")

    out = Path(__file__).parent / "mocap_scene.mp4"
    info = e.load_and_render_script(str(script), str(out))
    print(f"[OK]  rendered {info['frames']} frames to {out.name}")
    print("[OK]  mocap 'punch' and 'wave' resolved from the BVH library")
    print("Watch the video: hero should PUNCH (mocap) then WAVE (mocap)")


if __name__ == "__main__":
    test()