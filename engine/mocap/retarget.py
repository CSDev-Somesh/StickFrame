"""Mocap retargeter — map a BVH skeleton's motion onto StickFrame's 2D rig.

Approach (position-based FK inversion):
  1. For each frame, project mocap world positions to the screen plane
     (y-down) and subtract the hips root so the figure is local.
  2. Resolve each of our 25 bone tips to a semantic mocap joint via an
     alias table (handles CMU / HDM05 / generic namin g).
  3. Solve each bone's parent-relative angle from the vector between its
     parent's tip joint and its own tip joint — the exact inverse of how
     compute_forward_kinematics() consumes angles.

Key property: bone angles are SCALE-INVARIANT (only directions matter), so
no unit/scaling dance with the mocap data is needed. Bones without a mapped
joint keep the rest pose, so partial skeletons still load.

Output per frame is the same dict shape the procedural generators produce:
    {bone_name: radians} for all 25 bones.
"""

import math
from typing import Dict, List, Optional, Tuple

from engine.animation.skeleton import build_bipedal_skeleton

# ─── Semantic slot → our bone whose TIP that joint is ───────────────
# e.g. the moc joint 'chest' is the tip of our 'spine' bone.
SLOT_TO_BONE = {
    "hips":     "hips",
    "chest":    "spine",
    "neck":     "chest",
    "head":     "neck",
    "head_top": "head",
    "lshoulder": "left_shoulder", "rshoulder": "right_shoulder",
    "lelbow":   "left_upper_arm",     "relbow": "right_upper_arm",
    "lwrist":   "left_forearm",       "rwrist": "right_forearm",
    "lhand":    "left_wrist",         "rhand": "right_wrist",
    "lhand_end": "left_hand",         "rhand_end": "right_hand",
    "lhip":     "left_hip",           "rhip": "right_hip",
    "lknee":    "left_upper_leg",     "rknee": "right_upper_leg",
    "lankle":   "left_lower_leg",     "rankle": "right_lower_leg",
    "lfoot":    "left_ankle",         "rfoot": "right_ankle",
    "ltoe":     "left_foot",          "rtoe": "right_foot",
}

# Candidate names (lowercase) searchable for each slot.
# NOTE: real mocap names the BONE segment, and the joint we need is that
# segment's BASE. E.g. CMU's "lupperarm" base = shoulder, "llowerarm" base =
# elbow, "lhand" base = wrist, "lupleg" base = hip, "llowleg" base = knee,
# "lfoot" base = ankle, "ltoes" base = toes. We search the names in order and
# take the first hit, so ordering encodes the base-vs-tip preference.
SEARCH = {
    "hips":     ["hips", "hip", "pelvis", "root", "hroot", "hipjoint", "pelvisjoint"],
    "chest":    ["chest", "upperback", "thorax", "spine1", "spine2", "spine", "lowerback", "midback", "upperchest"],
    "neck":     ["neck", "lowerneck", "upperneck", "neck1", "neck_01", "lowerneckend"],
    "head":     ["head", "upperneck", "neck_end", "skullbase"],
    "head_top": ["head_end", "headtop", "head", "skullbase", "lefthead", "leftheadtop"],
    # left arm: shoulder segment base == shoulder joint; forearm base == elbow;
    # hand base == wrist; end site == hand tip
    "lshoulder": ["lupperarm", "leftshoulder", "leftarm", "lshoulder", "lefshoulder", "lclavicle", "shoulder.l", "left_shoulder"],
    "rshoulder": ["rupperarm", "rightshoulder", "rightarm", "rshoulder", "rightshoulder", "rclavicle", "shoulder.r", "right_shoulder"],
    "lelbow":   ["leftforearm", "leftlegarm", "llowerarm", "lelbow", "lefelbow", "left_elbow", "elbow.l", "l_elbow", "leftelbow"],
    "relbow":   ["rightforearm", "right lowerarm", "rlowerarm", "relbow", "rightelbow", "right_elbow", "elbow.r", "r_elbow"],
    "lwrist":   ["lefthand", "lhand", "leftwrist", "lwrist", "left_wrist", "wrist.l", "l_hand", "leftindex1"],
    "rwrist":   ["righthand", "rhand", "rightwrist", "rwrist", "right_wrist", "wrist.r", "r_hand"],
    "lhand":    ["lhand", "leftindex1", "lefthand", "left_hand", "hand.l", "lhand_end"],
    "rhand":    ["rhand", "rightindex1", "righthand", "right_hand", "hand.r", "rhand_end"],
    "lhip":     ["leftupleg", "lupleg", "lhip", "left_hip", "lefthip", "lhipjoint", "l_thigh", "thigh.l"],
    "rhip":     ["rightupleg", "rupleg", "rhip", "right_hip", "righthip", "rhipjoint", "r_thigh", "thigh.r"],
    "lknee":    ["leftleg", "llowleg", "lknee", "left_knee", "lefknee", "knee.l", "l_knee"],
    "rknee":    ["rightleg", "rlowleg", "rknee", "right_knee", "rightknee", "knee.r", "r_knee"],
    "lankle":   ["leftfoot", "lfoot", "leftankle", "lankle", "left_ankle", "lefankle", "ankle.l", "l_ankle"],
    "rankle":   ["rightfoot", "rfoot", "rightankle", "rankle", "right_ankle", "ankle.r", "r_ankle"],
    "lfoot":    ["lefttoebase", "ltoes", "ltoe", "left_foot", "leffoot", "l_foot", "foot.l", "lfoot"],
    "rfoot":    ["righttoebase", "rtoes", "rtoe", "right_foot", "rightfoot", "r_foot", "foot.r", "rfoot"],
    "ltoe":     ["ltoes", "lefttoebase", "ltoe", "left_toe", "l_foot_end", "ltoebase_end"],
    "rtoe":     ["rtoes", "righttoebase", "rtoe", "right_toe", "r_foot_end", "rtoebase_end"],
}


def _rest_pose(skel) -> Dict[str, float]:
    """Default angles (radians) from the built skeleton — used as fallback
    for bones with no mapped mocapoint so nothing freezes."""
    return {b.name: b.default_angle for b in skel.bones}


def _resolve_slot(slot: str, available_lower: Dict[str, str]) -> Optional[str]:
    """First candidate name present in the mocap joint set (case-insensitive).

    available_lower maps lowercase joint name -> its actual name in the BVH.
    Returns the ACTUAL name (so we can look up its position), or None.
    """
    for cand in SEARCH.get(slot, [slot]):
        if cand in available_lower:
            return available_lower[cand]
    return None


def _solve_pose(pts: Dict[str, Tuple[float, float]],
                skel,
                rest: Dict[str, float]) -> Dict[str, float]:
    """Recover parent-relative bone angles from mapped tip positions.

    pts: {bone_name: (x, y)} — the desired SCREEN position of each bone's tip.
    skel: build_bipedal_skeleton(). rest: fallback pose dict.
    Returns {bone_name: radians} covering ALL 25 bones.
    """
    names = [b.name for b in skel.bones]
    parent_name = {b.name: (names[b.parent_index] if b.parent_index >= 0 else None)
                   for b in skel.bones}

    world: Dict[str, float] = {}
    angles: Dict[str, float] = {}

    for b in skel.bones:  # already parent-before-child
        pn = parent_name[b.name]
        if pn is None:
            world[b.name] = 0.0
            angles[b.name] = 0.0
            continue
        # parent tip position = pts[pn]; our tip = pts[b.name]
        pp = pts.get(pn)
        cp = pts.get(b.name)
        # If either is missing — OR they coincide (degenerate vector, e.g. a
        # head-top joint absent in a minimal skeleton) — fall back to the rest
        # angle so the pose stays valid (no wild atan2(0,0)).
        if pp is None or cp is None:
            angles[b.name] = rest[b.name]
            world[b.name] = world[pn] + rest[b.name]
            continue
        dx, dy = cp[0] - pp[0], cp[1] - pp[1]
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            angles[b.name] = rest[b.name]
            world[b.name] = world[pn] + rest[b.name]
            continue
        world_angle = math.atan2(dy, dx)
        world[b.name] = world_angle
        angles[b.name] = world_angle - world[pn]

    return angles


def _clip_forward(clip) -> tuple:
    """Horizontal unit vector of the subject's ANATOMICAL forward.

    Travel direction is wrong when the mocap has a pelvis yaw (a body can
    travel along one world axis while facing another, as CMU often does).
    The body's forward is perpendicular to the hips lateral axis
    (LHip - RHip), flipped so it points along the direction of travel.

    Returns (fx, fz) unit in the XZ plane, or (1.0, 0.0) if unknown.
    """
    accx = accz = 0.0
    cnt = 0
    n = clip.n_frames()
    skip = max(1, n // 8)
    for f in range(0, n, skip):
        pos3 = clip.world_positions(f)
        av = {k.lower(): k for k in pos3}
        ln = _resolve_slot("lhip", av)
        rn = _resolve_slot("rhip", av)
        if not ln or not rn:
            continue
        lx, lz = pos3[ln][0] - pos3[rn][0], pos3[ln][2] - pos3[rn][2]
        L = math.hypot(lx, lz)
        if L < 1e-4:
            continue
        lx, lz = lx / L, lz / L
        # forward (horizontal) = up × lateral = (lz, -lx), since
        # up=(0,1,0) and lateral=(lx, 0, lz) → (1·lz, 0·lx−0·lz, −1·lx).
        accx += lz
        accz += -lx
        cnt += 1
    if cnt == 0:
        return (1.0, 0.0)
    fxx, fzz = accx / cnt, accz / cnt
    L = math.hypot(fxx, fzz)
    if L < 1e-6:
        return (1.0, 0.0)

    # Sign: point forward along the direction of travel
    r0 = clip.world_positions(0).get(clip.root.name, [0, 0, 0])
    r1 = clip.world_positions(n - 1).get(clip.root.name, [0, 0, 0])
    dx, dz = r1[0] - r0[0], r1[2] - r0[2]
    if dx * fxx + dz * fzz < 0:
        fxx, fzz = -fxx, -fzz
    return (fxx / L, fzz / L)


def _clip_heading(clip) -> tuple:
    """Backward-compatible alias for _clip_forward."""
    return _clip_forward(clip)


def pose_from_frame(clip, frame: int, view: str = "front",
                    full_skeleton=None, heading=None) -> Dict[str, float]:
    """Convert one BVH frame into a 25-bone StickFrame pose.

    Returns the same dict shape generators emit ({bone_name: radians}).
    """
    skel = full_skeleton if full_skeleton is not None else build_bipedal_skeleton(1.0)
    rest = _rest_pose(skel)

    pos3 = clip.world_positions(frame) if hasattr(clip, 'world_positions') else clip
    # Case-insensitive name lookup: real mocap joins vary in case.
    available = {k.lower(): k for k in pos3}

    # Flatten to screen.
    if view == "front":
        # screen x = lateral (X), y = -vertical (Y up -> down)
        two = {k: (v[0], -v[1]) for k, v in pos3.items()}
    else:
        # 'side'/walk: screen x = distance along the subject's heading
        # (sagittal plane). This keeps the stride readable regardless of the
        # world axis the mo cap subject walked along.
        hx, hz = heading if heading is not None else (1.0, 0.0)
        two = {}
        for k, v in pos3.items():
            two[k] = (v[0] * hx + v[2] * hz, -v[1])

    # hips reference = the root joint, whichever name it goes by
    hname = _resolve_slot("hips", available)
    if hname and hname in two:
        hips_x, hips_y = two[hname]
    else:
        first = next(iter(two.values()), (0.0, 0.0))
        hips_x, hips_y = first

    # Map every slot to a joint position -> bone tip position (relative to hips)
    pts = {}
    for slot, bone in SLOT_TO_BONE.items():
        join_name = _resolve_slot(slot, available)
        if join_name and join_name in two:
            pts[bone] = (two[join_name][0] - hips_x, two[join_name][1] - hips_y)

    # hips root point (origin)
    pts.setdefault("hips", (0.0, 0.0))

    return _solve_pose(pts, skel, rest)


def clip_to_poses(clip, view: str = "front", every_n: int = 1,
                  full_skeleton=None) -> List[Dict[str, float]]:
    """Sample every frame (or every_n-th) of a BVHClip into pose dicts.

    For 'side' view the subject's heading is computed once from the whole
    clip so all frames share the same projection plane.
    """
    skel = full_skeleton if full_skeleton is not None else build_bipedal_skeleton(1.0)
    heading = _clip_heading(clip) if view != "front" else None
    out = []
    for f in range(0, clip.n_frames(), every_n or 1):
        out.append(pose_from_frame(clip, f, view=view, full_skeleton=skel,
                                   heading=heading))
    return out