"""Generate small synthetic .bvh files for pipeline testing (no network needed).

Writes two fixtures into scripts/data/:
  - punch.bvh : a 2D right-cross punch (front view)
  - wave.bvh  : a simple arm wave
Each is a valid BVH (CMU-style channels) produced deterministically.
"""
import math
import os
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)

# Joint order (depth-first) + channel count
#   hips: 6 channels (Xpos Ypos Zpos Zrot Xrot Yrot)
#   every other joint: 3 (Zrot Xrot Yrot)
def hierarchy() -> str:
    return """HIERARCHY
ROOT hips
{
\tOFFSET 0 0 0
\tCHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
\tJOINT spine
\t{
\t\tOFFSET 0 8 0
\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\tJOINT chest
\t\t{
\t\t\tOFFSET 0 6 0
\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\tJOINT neck
\t\t\t{
\t\t\t\tOFFSET 0 5 0
\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\tJOINT head
\t\t\t\t{
\t\t\t\t\tOFFSET 0 4 0
\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\t}
\t\t\t}
\t\t\tJOINT lshoulder
\t\t\t{
\t\t\t\tOFFSET -4 3 0
\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\tJOINT lelbow
\t\t\t\t{
\t\t\t\t\tOFFSET -6 0 0
\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\t\tJOINT lhand
\t\t\t\t\t{
\t\t\t\t\t\tOFFSET -5 0 0
\t\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t\tJOINT rshoulder
\t\t\t{
\t\t\t\tOFFSET 4 3 0
\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\tJOINT relbow
\t\t\t\t{
\t\t\t\t\tOFFSET 6 0 0
\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\t\tJOINT rhand
\t\t\t\t\t{
\t\t\t\t\t\tOFFSET 5 0 0
\t\t\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t}
\tJOINT lhip
\t{
\t\tOFFSET -3 0 0
\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\tJOINT lknee
\t\t{
\t\t\tOFFSET 0 -12 0
\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\tJOINT lankle
\t\t\t{
\t\t\t\tOFFSET 0 -12 0
\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t}
\t\t}
\t}
\tJOINT rhip
\t{
\t\tOFFSET 3 0 0
\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\tJOINT rknee
\t\t{
\t\t\tOFFSET 0 -12 0
\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\tJOINT rankle
\t\t\t{
\t\t\t\tOFFSET 0 -12 0
\t\t\t\tCHANNELS 3 Zrotation Xrotation Yrotation
\t\t\t}
\t\t}
\t}
}
"""

# Joint order in the channel stream (depth-first, matching hierarchy()):
JOINT_ORDER = ["hips", "spine", "chest", "neck", "head",
               "lshoulder", "lelbow", "lhand",
               "rshoulder", "relbow", "rhand",
               "lhip", "lknee", "lankle",
               "rhip", "rknee", "rankle"]
HIPS_CH = 6
OTHER_CH = 3


def _frame(vals: dict) -> list:
    """Assemble a 54-value frame row from {joint: (z,x,y) rot degrees} + hips pos."""
    row = []
    for j in JOINT_ORDER:
        if j == "hips":
            px, py, pz, rz, rx, ry = vals.get(j, (0, 0, 0, 0, 0, 0))
            row += [px, py, pz, rz, rx, ry]
        else:
            rz, rx, ry = vals.get(j, (0, 0, 0))
            row += [rz, rx, ry]
    return row


def make_punch() -> str:
    """Right cross: arm sweeps up/out and back over ~1.2s (36 frames @30fps)."""
    n = 36
    fps = 30.0
    frames = []
    for i in range(n):
        t = i / (n - 1)  # 0..1
        # ease in/out envelope for the punch (sine squared)
        env = math.sin(t * math.pi) ** 2
        rshoulder_z = 12 + 55 * env          # sweep arm out/up in screen plane
        rshoulder_x = -8 * env               # slight forward reach (mostly hidden)
        relbow_z = -15 - 40 * env            # extend elbow (flatten) mid-punch
        rhand_z = 5 * env
        # body counter-rotate slightly (wind-up)
        chest_z = -3 * env
        spine_x = 6 + 4 * env                # lean forward a touch
        hips = (0, 0, 0, 0, 0, 0)
        frame = {
            "hips": hips,
            "spine": (0, spine_x, 0),
            "chest": (chest_z, 0, 0),
            "neck": (0, -2 * env, 0),
            "head": (0, 0, 0),
            "lshoulder": (0, 0, 0),
            "lelbow": (0, 10, 0),
            "lhand": (0, 0, 0),
            "rshoulder": (rshoulder_z, rshoulder_x, 0),
            "relbow": (relbow_z, 0, 0),
            "rhand": (rhand_z, 0, 0),
            "lhip": (0, 0, 0),
            "lknee": (0, 5, 0),
            "lankle": (0, 0, 0),
            "rhip": (0, 0, 0),
            "rknee": (0, 5, 0),
            "rankle": (0, 0, 0),
        }
        frames.append(_frame(frame))
    return _wrap(hierarchy(), frames, n, fps)


def make_wave() -> str:
    """Right hand raises and waves side-to-side over ~2s (60 frames)."""
    n = 60
    fps = 30.0
    frames = []
    for i in range(n):
        t = i / (n - 1)
        # raise arm 0..0.4, wave 0.4..1
        raise_env = min(t / 0.4, 1.0)
        wave = max(0.0, min((t - 0.4) / 0.6, 1.0))
        wave_ang = 15 * math.sin(wave * math.pi * 6) * wave
        rshoulder_z = 15 + 110 * (raise_env ** 0.7)
        relbow_z = -20 - 10 * raise_env
        rhand_z = wave_ang
        spine_x = 4
        frame = {
            "hips": (0, 0, 0, 0, 0, 0),
            "spine": (0, spine_x, 0),
            "chest": (0, 0, 0),
            "neck": (0, -2, 0),
            "head": (0, 0, 0),
            "lshoulder": (0, 0, 0),
            "lelbow": (0, 10, 0),
            "lhand": (0, 0, 0),
            "rshoulder": (rshoulder_z, -5, 0),
            "relbow": (relbow_z, 0, 0),
            "rhand": (rhand_z, 0, 0),
            "lhip": (0, 0, 0),
            "lknee": (0, 5, 0),
            "lankle": (0, 0, 0),
            "rhip": (0, 0, 0),
            "rknee": (0, 5, 0),
            "rankle": (0, 0, 0),
        }
        frames.append(_frame(frame))
    return _wrap(hierarchy(), frames, n, fps)


def _wrap(hier: str, frames: list, n: int, fps: float) -> str:
    lines = [hier.rstrip(), "MOTION", f"Frames: {n}", f"Frame Time: {1.0/fps:.6f}"]
    for f in frames:
        lines.append(" ".join(f"{v:.3f}" for v in f))
    return "\n".join(lines)


if __name__ == "__main__":
    punch = make_punch()
    wave = make_wave()
    (OUT_DIR / "punch.bvh").write_text(punch)
    (OUT_DIR / "wave.bvh").write_text(wave)
    print(f"Wrote {OUT_DIR / 'punch.bvh'} ({len(punch.splitlines())} lines)")
    print(f"Wrote {OUT_DIR / 'wave.bvh'} ({len(wave.splitlines())} lines)")
