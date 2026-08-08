"""Mocap → ActionClip importer — turn BVH motion into engine animation clips.

Reuses StickFrame's existing ActionClip/Keyframe data structures so captured
motion plays through the keyframe AnimationPlayer — the exact same path as
avatar-captured clips and custom .sf actions. A folder of .bvh files becomes
an "action library" the engine can attach to characters.
"""

import os
from typing import Dict, List, Optional

from engine.core.components import ActionClip, Keyframe
from engine.mocap import bvh as bvh_mod
from engine.mocap.retarget import clip_to_poses


def bvh_to_action_clip(
    bvh_path: str,
    name: Optional[str] = None,
    loop: bool = False,
    view: str = "front",
    every_n: int = 1,
    fps: Optional[float] = None,
) -> ActionClip:
    """Convert a .bvh file into a StickFrame ActionClip.

    Args:
        bvh_path: Path to the .bvh file.
        name: Clip name (defaults to the file's stem).
        loop: True → clip wraps (set for continuous motions like walk/idle).
        view: 'front' or 'side' projection of mocap to the 2D plane.
        every_n: subsample factor (1 = keep every frame).
        fps: output fps for keyframe timing (default: clip's frame rate).

    Returns:
        ActionClip with one Keyframe per sampled frame per bone.
    """
    clip = bvh_mod.load_bvh(bvh_path)
    poses = clip_to_poses(clip, view=view, every_n=every_n)
    if not poses:
        raise ValueError(f"No frames parsed from {bvh_path}")

    out_fps = fps or (1.0 / clip.frame_time if clip.frame_time > 0 else 30.0)
    dt = 1.0 / out_fps * every_n
    n_frames = len(poses)

    # Build keyframes per bone
    bone_kfs: Dict[str, List[Keyframe]] = {}
    base_bones = set(poses[0].keys())
    for bone in base_bones:
        kfs = []
        for i, pose in enumerate(poses):
            kfs.append(Keyframe(time=i * dt, angle=float(pose.get(bone, 0.0))))
        if loop and len(kfs) >= 2:
            kfs[-1] = Keyframe(time=(n_frames - 1) * dt, angle=kfs[0].angle)
        bone_kfs[bone] = kfs

    duration = max((n_frames - 1) * dt, 0.0) or clip.duration() or 1.0
    return ActionClip(
        name=name or os.path.splitext(os.path.basename(bvh_path))[0],
        duration=duration,
        loop=loop,
        bone_keyframes=bone_kfs,
    )


def load_mocap_library(
    folder: str,
    loop_names: Optional[List[str]] = None,
    view: str = "front",
    every_n: int = 1,
) -> Dict[str, ActionClip]:
    """Import every .bvh in `folder` into a library of ActionClips.

    Returns {clip_name: ActionClip}. Clip name = file stem. Files listed in
    loop_names loop; everything else plays once.
    """
    loops = set(loop_names or ())
    library: Dict[str, ActionClip] = {}
    if not os.path.isdir(folder):
        return library
    for fname in sorted(os.listdir(folder)):
        if not fname.lower().endswith(".bvh"):
            continue
        path = os.path.join(folder, fname)
        stem = os.path.splitext(fname)[0]
        try:
            clip = bvh_to_action_clip(path, name=stem, loop=(stem in loops),
                                      view=view, every_n=every_n)
            library[stem] = clip
        except Exception as ex:
            print(f"  [skip] {fname}: {ex}")
    return library


def bvh_to_clip(path: str, name: Optional[str] = None, loop: bool = False,
                view: str = "front", every_n: int = 1) -> ActionClip:
    """Thin alias for bvh_to_action_clip (keeps call sites short)."""
    return bvh_to_action_clip(path, name=name, loop=loop, view=view, every_n=every_n)


def merge_rest_into(pose: Dict[str, float], default_pose: Dict[str, float]) -> Dict[str, float]:
    """Fill any bone missing from a captured pose with its rest value."""
    out = dict(default_pose)
    out.update(pose)
    return out