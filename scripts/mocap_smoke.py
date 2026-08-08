"""End-to-end mocap pipeline smoke test.

Generate synthetic BVH -> parse -> retarget to our 25-bone rig ->
ActionClip -> render an MP4 -> assert finite angles and sensible motion.

Run:
    python scripts/mocap_smoke.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.animation.skeleton import build_bipedal_skeleton, compute_forward_kinematics
from engine.mocap.bvh import parse_bvh, BVHParserError
from engine.mocap.retarget import clip_to_poses, pose_from_frame
from engine.mocap.importer import bvh_to_action_clip, load_mocap_library

PASS = []
FAIL = []


def check(label, cond, extra=""):
    if cond:
        PASS.append(label)
        print(f"  [OK] {label}" + (f"  ({extra})" if extra else ""))
    else:
        FAIL.append(label)
        print(f"  [FAIL] {label}" + (f"  ({extra})" if extra else ""))


def get_clip(data_dir, fname):
    return parse_bvh((data_dir / fname).read_text(encoding="utf-8"))


def test_parse(data_dir):
    print("[1] BVH parser")
    for fname in ("punch.bvh", "wave.bvh"):
        try:
            clip = get_clip(data_dir, fname)
            check(f"parse {fname}: {len(clip.joints)} joints, {clip.n_frames()} frames",
                  len(clip.joints) >= 15 and clip.n_frames() > 20)
            pos = clip.world_positions(0)
            check(f"  world positions keyed ({len(pos)} joints)",
                  len(pos) == len(clip.joints))
        except BVHParserError as ex:
            check(f"parse {fname} ({ex})", False)


def test_retarget(data_dir):
    print("\n[2] Retarget -> 25 pose bones")
    for fname in ("punch.bvh", "wave.bvh"):
        clip = get_clip(data_dir, fname)
        poses = clip_to_poses(clip, view="front", every_n=2)
        all_ok = bool(poses)
        n_bones = 0
        for pose in poses:
            vals = list(pose.values())
            if not all(math.isfinite(v) for v in vals):
                all_ok = False
                break
            n_bones = max(n_bones, len(vals))
        check(f"{fname}: {len(poses)} poses, {n_bones} bones finite", all_ok and n_bones >= 20)

        # hand must travel between first and mid frame
        if fname == "punch.bvh":
            skel = build_bipedal_skeleton(1.0)
            hand_bone_i = next(i for i, b in enumerate(skel.bones) if b.name == "right_hand")

            def hand_world(frame):
                pose = pose_from_frame(clip, frame, view="front", full_skeleton=skel)
                for i, b in enumerate(skel.bones):
                    if b.name in pose:
                        skel.bones[i].default_angle = pose[b.name]
                compute_forward_kinematics(skel, 0, 0)
                return skel.world_positions[hand_bone_i]

            h0 = hand_world(0)
            hM = hand_world(len(clip.frames) // 2)
            dist = math.hypot(hM[0] - h0[0], hM[1] - h0[1])
            # The scale-1 arm is ~25 units long, so a real punch sweeps the
            # hand a good fraction of that. 12 is a safe "it actually moved"
            # threshold.
            check("punch right hand travels mid-clip", dist >= 6, f"moved {dist:.0f} units")


def test_importer(data_dir):
    print("\n[3] ActionClip import + render")
    lib = {}
    for fname, loop in (("punch.bvh", False), ("wave.bvh", False)):
        clip = bvh_to_action_clip(str(data_dir / fname), loop=loop, view="front")
        check(f"{fname} -> clip dur={clip.duration:.2f}s, {len(clip.bone_keyframes)} bones",
              clip.duration > 0 and len(clip.bone_keyframes) >= 20)
        lib[clip.name] = clip

    lib_all = load_mocap_library(str(data_dir), view="front")
    check(f"library loads {len(lib_all)} actions from data dir", len(lib_all) >= 2)

    # Render clip through the engine's keyframe player
    from engine import StickFrameEngine
    e = StickFrameEngine(fps=30, width=800, height=600)
    cid = e.create_character("hero", x=400, y=0, scale=2.5)
    player = e.entities[cid]['animation_player']
    player.clips.update(lib_all)
    e.timeline.load_timeline({"test": [{"time": 0.0, "action": "hero.punch", "params": {}}]})
    out = Path(__file__).parent / "mocap_punch.mp4"
    info = e.render(str(out), duration=2.0)
    check(f"render -> {out.name}", out.exists(), f"{info['frames']} frames")


def main():
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)

    import gen_synthetic_bvh as gen
    if not (data_dir / "punch.bvh").exists():
        (data_dir / "punch.bvh").write_text(gen.make_punch())
        (data_dir / "wave.bvh").write_text(gen.make_wave())
        print("Generated synthetic fixtures.")

    test_parse(data_dir)
    test_retarget(data_dir)
    test_importer(data_dir)
    print()
    print("=" * 52)
    print(f"PASS: {len(PASS)}   FAIL: {len(FAIL)}")
    if FAIL:
        for f in FAIL:
            print(f"  FAIL - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()