"""Skeletal animation — bone hierarchy, forward kinematics

v3 rig — rebuilt per the reference sheet (Stickman_Rig_Optimal_Design.jpg):
  Balanced Design • Clean Silhouette • Physical Realism • Maximum Expressiveness

All lengths are expressed in HEAD UNITS (H), where 1H = head diameter.
Reference proportions:
    Head      1.0 H   (perfect circle, dominates silhouette)
    Neck      0.25 H  (single joint, no floating neck)
    Torso     1.5 H   (spine + chest joint — bending/twisting/breathing)
    Upper arm 1.0 H   |  Forearm 1.0 H
    Upper leg 1.3 H   |  Lower leg 1.3 H
    Foot      0.4 H   (points forward, flat on ground)
    Total     ~5 H    (head 20% / torso 30% / legs 50%)
    Shoulders ≈ head width, hips slightly narrower, hips = root = COM
    Neutral stance: feet shoulder-width, knees unlocked, arms relaxed
    with a small gap from the torso, head centered over hips.
"""

import math
from typing import List, Tuple
from engine.core.components import BoneDef, Skeleton, ActionClip


# One head unit — the head circle's diameter at scale=1 (head_radius=7).
HEAD_UNIT = 14.0


def build_bipedal_skeleton(scale: float = 1.0) -> Skeleton:
    """Create the v3 stickman skeleton per the optimal-rig reference sheet.

    Coordinate system: screen (x→right, y↓down).
    Angle 0° = right, 90° = down, 180° = left, -90° (270°) = up.
    All angles are RELATIVE to the parent bone's world angle.

    Bone hierarchy:
        hips (root) ──spine── chest── neck── head
           ├─left_hip──upper_leg──lower_leg──ankle──foot
           ├─right_hip─upper_leg──lower_leg──ankle──foot
        chest ──left_shoulder──upper_arm──forearm──wrist──hand
        chest ──right_shoulder─upper_arm──forearm──wrist──hand

    Key v3 changes vs v2 (per reference):
      - Head-unit proportions: neck 0.25H, torso 1.5H, legs 1.3H+1.3H
      - Shoulders spread = head diameter, sit slightly below the neck
      - Hips slightly narrower than shoulders, hips is the root/COM
      - Feet point FORWARD (straight down in front view), flat on ground
      - Feet planted shoulder-width apart (knees unlocked, slight bend)
      - Wrist + ankle joints, hands simple (direction only)
    """
    s = scale
    R = math.radians
    H = HEAD_UNIT * s  # head unit at this scale

    bones = [
        # ── Torso (1.5H total): hips → spine → chest → neck (0.25H) → head.
        # Center-line dots per the reference:
        #   1. NECK joint — smooth head movement
        #   2. SHOULDER-CONNECTION dot — chest tip, where the two shoulder
        #      lines originate (drawn by the renderer)
        #   3. CHEST joint — at the MIDDLE of the torso (the bending/
        #      twisting pivot), clearly separated from the connection dot
        # Spine carries hips up to the mid-torso chest joint.
        BoneDef("hips",  0.0,        -1, 0.0),                 # 0 root / COM
        BoneDef("spine", 0.75 * H,    0, R(-90), thickness=1.0),   # 1 torso: thickest
        BoneDef("chest", 0.75 * H,    1, 0.0, thickness=1.0),      # 2 torso: thickest
        BoneDef("neck",  0.23 * H,    2, 0.0, thickness=0.8),      # 3 SHORT neck (5-10% shorter)
        BoneDef("head",  0.6 * H,     3, 0.0),                 # 4 stub slightly LONGER
        # than the head radius (0.5H) so the head circle bottom floats just
        # ABOVE the neck tip — the neck joint dot stays visible below the
        # head instead of being swallowed by the circle

        # ── Shoulders: spread slightly WIDER than the head (0.72H each side
        # vs head radius 0.5H) — the head read ~10% oversized against the
        # body, so broadening the shoulder line fixes the perceived ratio
        # without shrinking the head below the reference 1H. Joints sit
        # clearly below the head circle; arms hang from here.
        BoneDef("left_shoulder",  0.72 * H, 2, R(-132), thickness=0.9),  # 5 out-DOWN-left
        BoneDef("right_shoulder", 0.72 * H, 2, R(132), thickness=0.9),   # 6 out-DOWN-right

        # ── Left arm: upper ~0.7H, forearm ~0.7H (user review: reference
        # 1H+1H and 0.85H+0.85H both read too LONG — hands must end around
        # HIP level, not mid-thigh), wrist joint, simple hand.
        # Dots: only WRIST + HAND render (see NO_DOT).
        BoneDef("left_upper_arm", 0.7 * H,  5, R(-38), thickness=0.85),  # 7 hangs down
        BoneDef("left_forearm",   0.7 * H,  7, R(25), thickness=0.8),    # 8 elbow bend
        BoneDef("left_wrist",     0.15 * H, 8, 0.0, thickness=0.55),     # 9 wrist joint (thin)
        BoneDef("left_hand",      0.25 * H, 9, 0.0, thickness=0.5),      # 10 direction (thinnest)

        # ── Right arm (mirror)
        BoneDef("right_upper_arm", 0.7 * H,  6, R(38), thickness=0.85),  # 11
        BoneDef("right_forearm",   0.7 * H,  11, R(-25), thickness=0.8), # 12
        BoneDef("right_wrist",     0.15 * H, 12, 0.0, thickness=0.55),   # 13 wrist joint (thin)
        BoneDef("right_hand",      0.25 * H, 13, 0.0, thickness=0.5),    # 14 direction (thinnest)

        # ── Pelvis: hips slightly narrower than shoulders (root's children)
        # — widened a few px for a grounded stance (director review: hips
        # were too narrow, offset the legs outward slightly)
        BoneDef("left_hip",  0.28 * H, 0, R(99)),              # 15 down, out-left
        BoneDef("right_hip", 0.28 * H, 0, R(81)),              # 16 down, out-right

        # ── Left leg: 1.3H + 1.3H, knees UNLOCKED (12° bend so the knee
        # reads — idle rest pose, matches gen_idle so feet stay planted),
        # feet FORWARD with a visible toe-out angle
        BoneDef("left_upper_leg", 1.3 * H, 15, R(8), thickness=0.9),    # 17 slight out (stance)
        BoneDef("left_lower_leg", 1.3 * H, 17, R(-12), thickness=0.8),  # 18 relaxed knee bend
        BoneDef("left_ankle",     0.15 * H, 18, 0.0, thickness=0.75),   # 19 ankle joint
        BoneDef("left_foot",      0.32 * H, 19, R(25), thickness=0.7),  # 20 toe OUT-left (+5° outward)

        # ── Right leg (mirror)
        BoneDef("right_upper_leg", 1.3 * H, 16, R(-6), thickness=0.9),   # 21
        BoneDef("right_lower_leg", 1.3 * H, 21, R(9), thickness=0.8),    # 22 relaxed knee bend
        BoneDef("right_ankle",     0.15 * H, 22, 0.0, thickness=0.75),   # 23
        BoneDef("right_foot",      0.32 * H, 23, R(-25), thickness=0.7), # 24 toe OUT-right (+5° outward)
    ]
    return Skeleton(bones=bones,
                    world_angles=[0.0] * len(bones),
                    world_positions=[(0.0, 0.0)] * len(bones))


def compute_forward_kinematics(skeleton: Skeleton, base_x: float = 0.0, base_y: float = 0.0) -> None:
    """Compute world-space bone tip positions from bone angles.

    Traverses hierarchy top-down. For each bone:
      world_angle = parent_world_angle + bone.default_angle
      tip = parent_tip + (cos(world_angle)*length, sin(world_angle)*length)
    """
    n = len(skeleton.bones)
    skeleton.world_positions = [(0.0, 0.0)] * n
    skeleton.world_angles = [0.0] * n

    for i, bone in enumerate(skeleton.bones):
        if bone.parent_index < 0:
            parent_angle = 0.0
            px, py = base_x, base_y
        else:
            parent_angle = skeleton.world_angles[bone.parent_index]
            px, py = skeleton.world_positions[bone.parent_index]

        world_angle = parent_angle + bone.default_angle
        skeleton.world_angles[i] = world_angle

        tip_x = px + math.cos(world_angle) * bone.length
        tip_y = py + math.sin(world_angle) * bone.length
        skeleton.world_positions[i] = (tip_x, tip_y)


def apply_action_to_skeleton(skeleton: Skeleton, clip: ActionClip, time: float) -> None:
    """Apply keyframed bone angles from an action clip to the skeleton."""
    from engine.animation.easing import interpolate_keyframes

    for i, bone in enumerate(skeleton.bones):
        kfs = clip.bone_keyframes.get(bone.name)
        if kfs:
            keyframe_data = [(k.time, k.angle, 'linear') for k in kfs]
            angle = interpolate_keyframes(
                keyframe_data,
                time % clip.duration if clip.loop else min(time, clip.duration)
            )
            skeleton.bones[i].default_angle = angle


def get_all_bone_segments(skeleton: Skeleton) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Get all bone segments as (start, end) pairs for rendering."""
    segments = []
    for i, bone in enumerate(skeleton.bones):
        if bone.length <= 0:
            continue  # skip zero-length bones (hips pivot)
        tip = skeleton.world_positions[i]
        if bone.parent_index < 0:
            base = (0.0, 0.0)
        else:
            base = skeleton.world_positions[bone.parent_index]
        segments.append((base, tip))
    return segments


def get_bone_tip_world(skeleton: Skeleton, bone_name: str) -> Tuple[float, float]:
    for i, bone in enumerate(skeleton.bones):
        if bone.name == bone_name:
            return skeleton.world_positions[i]
    return (0.0, 0.0)
