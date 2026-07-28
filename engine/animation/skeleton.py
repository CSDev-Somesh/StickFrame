"""Skeletal animation — bone hierarchy, forward kinematics"""

import math
from typing import List, Optional, Tuple

from engine.core.components import BoneDef, Skeleton, Keyframe, ActionClip


def build_bipedal_skeleton(scale: float = 1.0) -> Skeleton:
    """Create a standard bipedal stickman skeleton.
    
    Bone hierarchy (parent → child):
        hips (root)
        ├── spine → neck → head
        ├── left_upper_arm → left_forearm → left_hand
        ├── right_upper_arm → right_forearm → right_hand
        ├── left_upper_leg → left_lower_leg → left_foot
        └── right_upper_leg → right_lower_leg → right_foot
    """
    s = scale
    bones = [
        BoneDef("hips", 5 * s, -1, 0.0),           # 0: root
        BoneDef("spine", 15 * s, 0, 0.0),           # 1
        BoneDef("neck", 4 * s, 1, 0.0),             # 2
        BoneDef("head", 12 * s, 2, 0.0),            # 3
        BoneDef("left_upper_arm", 15 * s, 1, math.radians(-30)),   # 4
        BoneDef("left_forearm", 13 * s, 4, math.radians(-45)),     # 5
        BoneDef("left_hand", 5 * s, 5, 0.0),         # 6
        BoneDef("right_upper_arm", 15 * s, 1, math.radians(30)),   # 7
        BoneDef("right_forearm", 13 * s, 7, math.radians(45)),     # 8
        BoneDef("right_hand", 5 * s, 8, 0.0),        # 9
        BoneDef("left_upper_leg", 16 * s, 0, math.radians(-10)),   # 10
        BoneDef("left_lower_leg", 16 * s, 10, math.radians(5)),    # 11
        BoneDef("left_foot", 6 * s, 11, 0.0),        # 12
        BoneDef("right_upper_leg", 16 * s, 0, math.radians(10)),   # 13
        BoneDef("right_lower_leg", 16 * s, 13, math.radians(-5)),  # 14
        BoneDef("right_foot", 6 * s, 14, 0.0),       # 15
    ]
    return Skeleton(bones=bones,
                    world_angles=[0.0] * len(bones),
                    world_positions=[(0.0, 0.0)] * len(bones))


def compute_forward_kinematics(skeleton: Skeleton, base_x: float = 0.0, base_y: float = 0.0) -> None:
    """Compute world-space bone tip positions from bone angles.
    
    Traverses hierarchy top-down. Each bone's world position is computed
    from its parent's world position + its own length at the accumulated angle.
    """
    n = len(skeleton.bones)
    skeleton.world_positions = [(0.0, 0.0)] * n
    skeleton.world_angles = [0.0] * n
    
    for i, bone in enumerate(skeleton.bones):
        if bone.parent_index < 0:
            # Root bone — position at base
            parent_angle = 0.0
            px, py = base_x, base_y
        else:
            parent_angle = skeleton.world_angles[bone.parent_index]
            px, py = skeleton.world_positions[bone.parent_index]
        
        # Accumulate angle: parent world angle + this bone's local angle
        world_angle = parent_angle + bone.default_angle
        skeleton.world_angles[i] = world_angle
        
        # Tip position = parent position + rotated bone vector
        tip_x = px + math.cos(world_angle) * bone.length
        tip_y = py + math.sin(world_angle) * bone.length
        skeleton.world_positions[i] = (tip_x, tip_y)


def apply_action_to_skeleton(skeleton: Skeleton, clip: ActionClip, time: float) -> None:
    """Apply keyframed bone angles from an action clip to the skeleton.
    
    Modifies skeleton.bones[i].default_angle for each bone that has
    keyframes in the clip.
    """
    from engine.animation.easing import interpolate_keyframes
    
    for i, bone in enumerate(skeleton.bones):
        kfs = clip.bone_keyframes.get(bone.name)
        if kfs:
            keyframe_data = [(k.time, k.angle, 'linear') for k in kfs]
            angle = interpolate_keyframes(keyframe_data, time % clip.duration if clip.loop else min(time, clip.duration))
            skeleton.bones[i].default_angle = angle


def get_bone_tip_world(skeleton: Skeleton, bone_name: str) -> Tuple[float, float]:
    """Get the world-space tip position of a named bone"""
    for i, bone in enumerate(skeleton.bones):
        if bone.name == bone_name:
            return skeleton.world_positions[i]
    return (0.0, 0.0)


def get_all_bone_segments(skeleton: Skeleton) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Get all bone segments as (start, end) pairs for rendering.
    
    For each bone, the segment goes from the bone's base to its tip.
    The base of a bone is the tip of its parent (or origin for root).
    """
    segments = []
    for i, bone in enumerate(skeleton.bones):
        tip = skeleton.world_positions[i]
        if bone.parent_index < 0:
            base = (0.0, 0.0)  # will be offset by entity position
        else:
            base = skeleton.world_positions[bone.parent_index]
        segments.append((base, tip))
    return segments
