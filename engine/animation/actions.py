"""Built-in action library"""

import math
from engine.core.components import ActionClip, Keyframe


def _R(deg): return math.radians(deg)


def create_idle() -> ActionClip:
    """Standing idle with natural arm hang"""
    clip = ActionClip("idle", 2.0, loop=True)
    # Subtle body sway
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, _R(-90)),
        Keyframe(1.0, _R(-88)),
        Keyframe(2.0, _R(-90)),
    ]
    # Arms hang naturally with micro-movement
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, _R(185)), Keyframe(2.0, _R(185)),
    ]
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, _R(175)), Keyframe(2.0, _R(175)),
    ]
    clip.bone_keyframes["left_forearm"] = [
        Keyframe(0.0, _R(5)), Keyframe(1.0, _R(8)), Keyframe(2.0, _R(5)),
    ]
    clip.bone_keyframes["right_forearm"] = [
        Keyframe(0.0, _R(-5)), Keyframe(1.0, _R(-8)), Keyframe(2.0, _R(-5)),
    ]
    return clip


def create_walk() -> ActionClip:
    """Walking cycle — realistic gait with forward movement"""
    clip = ActionClip("walk", 0.8, loop=True)
    R = _R

    # Body: slight lean forward + bounce
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, R(-85)),   # lean forward
        Keyframe(0.2, R(-82)),
        Keyframe(0.4, R(-85)),   # upright-ish
        Keyframe(0.6, R(-88)),
        Keyframe(0.8, R(-85)),
    ]

    # Left arm: swings forward (toward right/down) and back (toward left/up)
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, R(155)),   # forward swing
        Keyframe(0.2, R(170)),
        Keyframe(0.4, R(210)),   # back swing
        Keyframe(0.6, R(185)),
        Keyframe(0.8, R(155)),   # forward again
    ]
    clip.bone_keyframes["left_forearm"] = [
        Keyframe(0.0, R(-20)),
        Keyframe(0.2, R(0)),
        Keyframe(0.4, R(30)),
        Keyframe(0.6, R(10)),
        Keyframe(0.8, R(-20)),
    ]

    # Right arm: opposite phase to left
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, R(200)),   # back swing
        Keyframe(0.2, R(185)),
        Keyframe(0.4, R(150)),   # forward swing
        Keyframe(0.6, R(165)),
        Keyframe(0.8, R(200)),
    ]
    clip.bone_keyframes["right_forearm"] = [
        Keyframe(0.0, R(25)),
        Keyframe(0.2, R(5)),
        Keyframe(0.4, R(-15)),
        Keyframe(0.6, R(0)),
        Keyframe(0.8, R(25)),
    ]

    # Left leg: forward step → back
    clip.bone_keyframes["left_upper_leg"] = [
        Keyframe(0.0, R(55)),    # forward
        Keyframe(0.2, R(75)),
        Keyframe(0.4, R(120)),   # back
        Keyframe(0.6, R(95)),
        Keyframe(0.8, R(55)),
    ]
    clip.bone_keyframes["left_lower_leg"] = [
        Keyframe(0.0, R(-30)),
        Keyframe(0.2, R(-10)),
        Keyframe(0.4, R(15)),
        Keyframe(0.6, R(-5)),
        Keyframe(0.8, R(-30)),
    ]

    # Right leg: opposite phase
    clip.bone_keyframes["right_upper_leg"] = [
        Keyframe(0.0, R(120)),   # back
        Keyframe(0.2, R(95)),
        Keyframe(0.4, R(55)),    # forward
        Keyframe(0.6, R(75)),
        Keyframe(0.8, R(120)),
    ]
    clip.bone_keyframes["right_lower_leg"] = [
        Keyframe(0.0, R(15)),
        Keyframe(0.2, R(-5)),
        Keyframe(0.4, R(-30)),
        Keyframe(0.6, R(-10)),
        Keyframe(0.8, R(15)),
    ]

    # Forward movement
    clip.position_keyframes["x"] = [
        Keyframe(0.0, 0), Keyframe(0.4, 30), Keyframe(0.8, 60),
    ]
    clip.position_keyframes["y"] = [
        Keyframe(0.0, 0), Keyframe(0.2, -4), Keyframe(0.4, 0),
        Keyframe(0.6, -4), Keyframe(0.8, 0),
    ]
    return clip


def create_jump() -> ActionClip:
    clip = ActionClip("jump", 0.8, loop=False)
    R = _R
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, R(-85)), Keyframe(0.2, R(-70)),
        Keyframe(0.35, R(-95)), Keyframe(0.8, R(-90)),
    ]
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, R(185)), Keyframe(0.2, R(220)),
        Keyframe(0.35, R(260)), Keyframe(0.8, R(200)),
    ]
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, R(175)), Keyframe(0.2, R(140)),
        Keyframe(0.35, R(100)), Keyframe(0.8, R(160)),
    ]
    clip.bone_keyframes["left_upper_leg"] = [
        Keyframe(0.0, R(95)), Keyframe(0.2, R(120)),
        Keyframe(0.35, R(70)), Keyframe(0.8, R(90)),
    ]
    clip.bone_keyframes["right_upper_leg"] = [
        Keyframe(0.0, R(85)), Keyframe(0.2, R(60)),
        Keyframe(0.35, R(110)), Keyframe(0.8, R(90)),
    ]
    clip.position_keyframes["y"] = [
        Keyframe(0.0, 0), Keyframe(0.2, -8), Keyframe(0.35, -50),
        Keyframe(0.6, -50), Keyframe(0.8, 0),
    ]
    return clip


def create_wave() -> ActionClip:
    clip = ActionClip("wave", 1.5, loop=False)
    R = _R
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, R(175)), Keyframe(0.3, R(100)),
        Keyframe(1.5, R(100)),
    ]
    clip.bone_keyframes["right_forearm"] = [
        Keyframe(0.0, R(-5)), Keyframe(0.3, R(-60)),
        Keyframe(0.5, R(-40)), Keyframe(0.7, R(-60)),
        Keyframe(0.9, R(-40)), Keyframe(1.1, R(-60)),
        Keyframe(1.3, R(-40)), Keyframe(1.5, R(-60)),
    ]
    return clip


def create_fall() -> ActionClip:
    clip = ActionClip("fall", 1.0, loop=False)
    R = _R
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, R(-90)), Keyframe(0.3, R(-60)),
        Keyframe(0.6, R(-30)), Keyframe(1.0, R(0)),
    ]
    clip.bone_keyframes["left_upper_arm"] = [
        Keyframe(0.0, R(185)), Keyframe(0.5, R(220)),
        Keyframe(1.0, R(250)),
    ]
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, R(175)), Keyframe(0.5, R(140)),
        Keyframe(1.0, R(110)),
    ]
    clip.bone_keyframes["left_upper_leg"] = [
        Keyframe(0.0, R(95)), Keyframe(0.5, R(130)),
        Keyframe(1.0, R(160)),
    ]
    clip.bone_keyframes["right_upper_leg"] = [
        Keyframe(0.0, R(85)), Keyframe(0.5, R(50)),
        Keyframe(1.0, R(20)),
    ]
    clip.position_keyframes["y"] = [
        Keyframe(0.0, 0), Keyframe(0.5, 20), Keyframe(1.0, 50),
    ]
    return clip


def create_punch() -> ActionClip:
    clip = ActionClip("punch", 0.5, loop=False)
    R = _R
    clip.bone_keyframes["right_upper_arm"] = [
        Keyframe(0.0, R(175)), Keyframe(0.1, R(100)),
        Keyframe(0.25, R(80)), Keyframe(0.5, R(175)),
    ]
    clip.bone_keyframes["right_forearm"] = [
        Keyframe(0.0, R(-5)), Keyframe(0.1, R(30)),
        Keyframe(0.25, R(-20)), Keyframe(0.5, R(-5)),
    ]
    clip.bone_keyframes["spine"] = [
        Keyframe(0.0, R(-90)), Keyframe(0.1, R(-85)),
        Keyframe(0.25, R(-80)), Keyframe(0.5, R(-90)),
    ]
    return clip


BUILTIN_ACTIONS = {
    'idle': create_idle, 'walk': create_walk, 'jump': create_jump,
    'wave': create_wave, 'fall': create_fall, 'punch': create_punch,
}

def get_action(name: str) -> ActionClip:
    factory = BUILTIN_ACTIONS.get(name)
    if factory:
        return factory()
    raise KeyError(f"Unknown action: {name}. Available: {list(BUILTIN_ACTIONS.keys())}")

def register_action(name: str, factory) -> None:
    BUILTIN_ACTIONS[name] = factory
