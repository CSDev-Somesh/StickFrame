"""Skeletal animation — bone hierarchy, forward kinematics"""

import math
from typing import List, Tuple
from engine.core.components import BoneDef, Skeleton, ActionClip


def build_bipedal_skeleton(scale: float = 1.0) -> Skeleton:
    """Create a standard bipedal stickman skeleton.
    
    Coordinate system: screen (x→right, y↓down).
    Angle 0° = right, 90° = down, 180° = left, -90° (270°) = up.
    
    Bone hierarchy:
        hips (root) ──spine── neck── head
           │
           ├──left_upper_arm──forearm──hand
           ├──right_upper_arm──forearm──hand
           ├──left_upper_leg──lower_leg──foot
           └──right_upper_leg──lower_leg──foot
    
    All angles are relative to parent bone's world angle.
    """
    s = scale
    R90 = math.radians(90)    # down
    R180 = math.radians(180)  # left
    Rm90 = math.radians(-90)  # up
    
    bones = [
        BoneDef("hips",  0 * s, -1, 0.0),            # 0: root (invisible pivot)
        BoneDef("spine", 25 * s, 0, Rm90),            # 1: goes UP from hips
        BoneDef("neck",  5 * s, 1, 0.0),              # 2: continues UP (inherits -90° from spine)
        BoneDef("head",  14 * s, 2, 0.0),             # 3: head continues up
        
        # Left arm — hangs DOWN and slightly LEFT from shoulder
        BoneDef("left_upper_arm",  15 * s, 1, math.radians(185)),   # 4
        BoneDef("left_forearm",    13 * s, 4, math.radians(10)),    # 5: slight bend
        BoneDef("left_hand",       5 * s, 5, 0.0),                  # 6
        
        # Right arm — hangs DOWN and slightly RIGHT from shoulder
        BoneDef("right_upper_arm", 15 * s, 1, math.radians(175)),   # 7
        BoneDef("right_forearm",   13 * s, 7, math.radians(-10)),   # 8
        BoneDef("right_hand",      5 * s, 8, 0.0),                  # 9
        
        # Left leg — goes DOWN and slightly LEFT from hips
        BoneDef("left_upper_leg",  16 * s, 0, math.radians(95)),    # 10
        BoneDef("left_lower_leg",  16 * s, 10, math.radians(-5)),   # 11: slight knee bend
        BoneDef("left_foot",       6 * s, 11, 0.0),                # 12
        
        # Right leg — goes DOWN and slightly RIGHT from hips
        BoneDef("right_upper_leg", 16 * s, 0, math.radians(85)),    # 13
        BoneDef("right_lower_leg", 16 * s, 13, math.radians(5)),    # 14
        BoneDef("right_foot",      6 * s, 14, 0.0),                # 15
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
