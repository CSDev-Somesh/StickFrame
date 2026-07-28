"""Built-in action library — predefined animation clips for the bipedal skeleton"""

import math
from engine.core.components import ActionClip, Keyframe


def create_idle() -> ActionClip:
    """Standing idle — subtle breathing motion"""
    clip = ActionClip("idle", duration=2.0, loop=True)
    # Spine sways slightly
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, 0.0),
        Keyframe(1.0, math.radians(1)),
        Keyframe(2.0, 0.0),
    ]
    # Arms hang slightly
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, math.radians(-30)),
        Keyframe(1.0, math.radians(-28)),
        Keyframe(2.0, math.radians(-30)),
    ]
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, math.radians(30)),
        Keyframe(1.0, math.radians(28)),
        Keyframe(2.0, math.radians(30)),
    ]
    return clip


def create_walk() -> ActionClip:
    """Walking cycle — alternating arm/leg swing"""
    clip = ActionClip("walk", duration=1.0, loop=True)
    
    # Core body bounce
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, math.radians(-2)),
        Keyframe(0.25, math.radians(2)),
        Keyframe(0.5, math.radians(-2)),
        Keyframe(0.75, math.radians(2)),
        Keyframe(1.0, math.radians(-2)),
    ]
    
    # Arms swing opposite to legs
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, math.radians(-50)),
        Keyframe(0.25, math.radians(30)),
        Keyframe(0.5, math.radians(-50)),
        Keyframe(0.75, math.radians(30)),
        Keyframe(1.0, math.radians(-50)),
    ]
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, math.radians(50)),
        Keyframe(0.25, math.radians(-30)),
        Keyframe(0.5, math.radians(50)),
        Keyframe(0.75, math.radians(-30)),
        Keyframe(1.0, math.radians(50)),
    ]
    clip.bone_keyframes["left_forearm"] = [
        Keyframe(0.0, math.radians(-20)),
        Keyframe(0.5, math.radians(20)),
        Keyframe(1.0, math.radians(-20)),
    ]
    clip.bone_keyframes["right_forearm"] = [
        Keyframe(0.0, math.radians(20)),
        Keyframe(0.5, math.radians(-20)),
        Keyframe(1.0, math.radians(20)),
    ]
    
    # Legs
    clip.bone_keyframes["left_upper_leg"] = [
        Keyframe(0.0, math.radians(30)),
        Keyframe(0.25, math.radians(-10)),
        Keyframe(0.5, math.radians(-30)),
        Keyframe(0.75, math.radians(10)),
        Keyframe(1.0, math.radians(30)),
    ]
    clip.bone_keyframes["right_upper_leg"] = [
        Keyframe(0.0, math.radians(-30)),
        Keyframe(0.25, math.radians(10)),
        Keyframe(0.5, math.radians(30)),
        Keyframe(0.75, math.radians(-10)),
        Keyframe(1.0, math.radians(-30)),
    ]
    clip.bone_keyframes["left_lower_leg"] = [
        Keyframe(0.0, math.radians(-10)),
        Keyframe(0.5, math.radians(10)),
        Keyframe(1.0, math.radians(-10)),
    ]
    clip.bone_keyframes["right_lower_leg"] = [
        Keyframe(0.0, math.radians(10)),
        Keyframe(0.5, math.radians(-10)),
        Keyframe(1.0, math.radians(10)),
    ]
    
    return clip


def create_jump() -> ActionClip:
    """Jump — crouch then spring up"""
    clip = ActionClip("jump", duration=0.8, loop=False)
    
    # Spine: crouch → extend
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, math.radians(10)),
        Keyframe(0.2, math.radians(20)),
        Keyframe(0.35, math.radians(-5)),
        Keyframe(0.8, math.radians(-2)),
    ]
    
    # Arms up
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, math.radians(-40)),
        Keyframe(0.2, math.radians(-80)),
        Keyframe(0.35, math.radians(-120)),
        Keyframe(0.8, math.radians(-60)),
    ]
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, math.radians(40)),
        Keyframe(0.2, math.radians(80)),
        Keyframe(0.35, math.radians(120)),
        Keyframe(0.8, math.radians(60)),
    ]
    
    # Legs: crouch → extend
    clip.bone_keyframes["left_upper_leg"] = [
        Keyframe(0.0, math.radians(20)),
        Keyframe(0.2, math.radians(40)),
        Keyframe(0.35, math.radians(-10)),
        Keyframe(0.8, math.radians(5)),
    ]
    clip.bone_keyframes["right_upper_leg"] = [
        Keyframe(0.0, math.radians(-20)),
        Keyframe(0.2, math.radians(-40)),
        Keyframe(0.35, math.radians(10)),
        Keyframe(0.8, math.radians(-5)),
    ]
    
    return clip


def create_wave() -> ActionClip:
    """Wave hand — raise right arm and wave"""
    clip = ActionClip("wave", duration=1.5, loop=False)
    
    # Right arm raises
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, math.radians(30)),
        Keyframe(0.3, math.radians(150)),
        Keyframe(1.5, math.radians(150)),
    ]
    clip.bone_keyframes["right_forearm"] = [
        Keyframe(0.0, math.radians(45)),
        Keyframe(0.3, math.radians(-60)),
        Keyframe(0.5, math.radians(-30)),
        Keyframe(0.7, math.radians(-60)),
        Keyframe(0.9, math.radians(-30)),
        Keyframe(1.5, math.radians(-60)),
    ]
    
    return clip


def create_fall() -> ActionClip:
    """Fall backwards"""
    clip = ActionClip("fall", duration=1.0, loop=False)
    
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, 0.0),
        Keyframe(0.3, math.radians(30)),
        Keyframe(0.6, math.radians(60)),
        Keyframe(1.0, math.radians(90)),
    ]
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, math.radians(-30)),
        Keyframe(0.5, math.radians(60)),
        Keyframe(1.0, math.radians(90)),
    ]
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, math.radians(30)),
        Keyframe(0.5, math.radians(-60)),
        Keyframe(1.0, math.radians(-90)),
    ]
    
    return clip


def create_punch() -> ActionClip:
    """Throw a punch with right arm"""
    clip = ActionClip("punch", duration=0.5, loop=False)
    
    # Right arm: wind up → extend
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, math.radians(30)),
        Keyframe(0.1, math.radians(-90)),
        Keyframe(0.25, math.radians(-60)),
        Keyframe(0.5, math.radians(30)),
    ]
    clip.bone_keyframes["right_forearm"] = [
        Keyframe(0.0, math.radians(45)),
        Keyframe(0.1, math.radians(90)),
        Keyframe(0.25, math.radians(-10)),
        Keyframe(0.5, math.radians(45)),
    ]
    
    # Body shifts forward
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, 0.0),
        Keyframe(0.1, math.radians(5)),
        Keyframe(0.25, math.radians(10)),
        Keyframe(0.5, 0.0),
    ]
    
    return clip


# Registry of all built-in actions
BUILTIN_ACTIONS = {
    'idle': create_idle,
    'walk': create_walk,
    'jump': create_jump,
    'wave': create_wave,
    'fall': create_fall,
    'punch': create_punch,
}


def get_action(name: str) -> ActionClip:
    """Get a built-in action by name."""
    factory = BUILTIN_ACTIONS.get(name)
    if factory:
        return factory()
    raise KeyError(f"Unknown action: {name}. Available: {list(BUILTIN_ACTIONS.keys())}")


def register_action(name: str, factory) -> None:
    """Register a custom action factory."""
    BUILTIN_ACTIONS[name] = factory
