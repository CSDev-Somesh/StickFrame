"""Procedural animation generators — all actions are math, no keyframes

Each generator is a function(time, params) → dict of bone_name → angle.
"""

import math
from typing import Dict, Callable, Any


def _R(deg): return math.radians(deg)

# ─── IDLE ──────────────────────────────────────────────────

def gen_idle(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Natural standing with breathing micro-motion"""
    p = params or {}
    speed = p.get('speed', 1.0)
    s = t * speed
    
    return {
        'spine': _R(-90) + math.sin(s * 1.5) * _R(1),
        'neck': 0.0,
        'head': math.sin(s * 1.5 + 0.5) * _R(1),
        'left_upper_arm': _R(185) + math.sin(s * 1.2) * _R(2),
        'left_forearm': _R(5) + math.sin(s * 1.3) * _R(2),
        'left_hand': 0.0,
        'right_upper_arm': _R(175) + math.sin(s * 1.2 + math.pi) * _R(2),
        'right_forearm': _R(-5) + math.sin(s * 1.3 + math.pi) * _R(2),
        'right_hand': 0.0,
        'left_upper_leg': _R(92),
        'left_lower_leg': _R(-3),
        'left_foot': 0.0,
        'right_upper_leg': _R(88),
        'right_lower_leg': _R(3),
        'right_foot': 0.0,
        'hips': 0.0,
    }


# ─── WALK ──────────────────────────────────────────────────

def gen_walk(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Sine-wave walk. Parameters: speed, stride, step_height, bounce"""
    p = params or {}
    speed = p.get('speed', 1.2)
    stride = p.get('stride', 55)
    step_h = p.get('step_height', 12)
    bounce = p.get('bounce', 3)
    
    s = t * speed
    swing = math.sin(s * math.pi)
    swing_opp = math.sin(s * math.pi + math.pi)
    lift = abs(math.sin(s * math.pi))
    lift_opp = abs(math.sin(s * math.pi + math.pi))
    double = math.sin(s * math.pi * 2)
    
    return {
        'spine': _R(-88) + double * _R(2),
        'neck': 0.0,
        'head': double * _R(1),
        'left_upper_arm': _R(185) - swing * _R(25),
        'left_forearm': _R(10) + swing * _R(15),
        'left_hand': -swing * _R(10),
        'right_upper_arm': _R(175) - swing_opp * _R(25),
        'right_forearm': _R(-10) + swing_opp * _R(15),
        'right_hand': -swing_opp * _R(10),
        'left_upper_leg': _R(90) + swing * _R(35),
        'left_lower_leg': -swing * _R(20),
        'left_foot': lift * _R(10),
        'right_upper_leg': _R(90) + swing_opp * _R(35),
        'right_lower_leg': -swing_opp * _R(20),
        'right_foot': lift_opp * _R(10),
        'hips': 0.0,
    }


# ─── RUN ───────────────────────────────────────────────────

def gen_run(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Running — faster, bigger movements, more bounce"""
    p = params or {}
    speed = p.get('speed', 2.0)
    stride = p.get('stride', 80)
    step_h = p.get('step_height', 18)
    bounce = p.get('bounce', 8)
    
    s = t * speed
    swing = math.sin(s * math.pi)
    swing_opp = math.sin(s * math.pi + math.pi)
    lift = abs(math.sin(s * math.pi))
    double = math.sin(s * math.pi * 2)
    
    return {
        'spine': _R(-95) + double * _R(3),  # lean forward
        'neck': _R(-5),
        'head': _R(-5) + double * _R(2),
        'left_upper_arm': _R(195) - swing * _R(45),  # bigger arm swing
        'left_forearm': _R(30) + swing * _R(25),
        'left_hand': -swing * _R(20),
        'right_upper_arm': _R(165) - swing_opp * _R(45),
        'right_forearm': _R(-30) + swing_opp * _R(25),
        'right_hand': -swing_opp * _R(20),
        'left_upper_leg': _R(90) + swing * _R(50),  # bigger leg swing
        'left_lower_leg': -swing * _R(35),
        'left_foot': lift * _R(15),
        'right_upper_leg': _R(90) + swing_opp * _R(50),
        'right_lower_leg': -swing_opp * _R(35),
        'right_foot': lift * _R(15),
        'hips': 0.0,
    }


# ─── JUMP ──────────────────────────────────────────────────

def gen_jump(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Jump — crouch then spring, comes back down"""
    p = params or {}
    height = p.get('height', 50)
    duration = p.get('duration', 0.8)
    
    progress = min(t / duration, 1.0)
    
    # Jump curve: crouch → extend → float → land
    if progress < 0.25:  # crouch
        phase = progress / 0.25
        crouch = phase
        body_y = crouch * 10
        spine_lean = _R(10) * crouch
        arm_up = crouch * _R(40)
        leg_crouch = crouch * _R(20)
    elif progress < 0.45:  # spring up
        phase = (progress - 0.25) / 0.2
        body_y = 10 - phase * height
        spine_lean = _R(10) * (1 - phase)
        arm_up = _R(40) * (1 - phase) + phase * _R(100)
        leg_crouch = _R(20) * (1 - phase)
    elif progress < 0.7:  # float
        phase = (progress - 0.45) / 0.25
        body_y = -height * (1 - phase * 0.1)
        spine_lean = 0
        arm_up = _R(100)
        leg_crouch = _R(-10)
    else:  # land
        phase = (progress - 0.7) / 0.3
        body_y = -height * (1 - phase) * 0.9 + phase * 10
        spine_lean = _R(5) * phase
        arm_up = _R(100) * (1 - phase)
        leg_crouch = _R(-10) * (1 - phase) + phase * _R(20)
    
    return {
        'spine': _R(-90) + spine_lean,
        'neck': _R(5),
        'head': _R(5),
        'left_upper_arm': _R(185) - arm_up,
        'left_forearm': _R(5) - arm_up * 0.3,
        'left_hand': 0.0,
        'right_upper_arm': _R(175) + arm_up,
        'right_forearm': _R(-5) + arm_up * 0.3,
        'right_hand': 0.0,
        'left_upper_leg': _R(90) + leg_crouch,
        'left_lower_leg': -leg_crouch * 0.5,
        'left_foot': 0.0,
        'right_upper_leg': _R(90) + leg_crouch,
        'right_lower_leg': -leg_crouch * 0.5,
        'right_foot': 0.0,
        'hips': 0.0,
    }, body_y


# ─── WAVE ──────────────────────────────────────────────────

def gen_wave(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Right arm waves — arm raises, hand oscillates"""
    p = params or {}
    duration = p.get('duration', 2.0)
    
    progress = min(t / duration, 1.0)
    
    # Arm raise
    if progress < 0.2:
        arm_angle = _R(175) + (progress / 0.2) * _R(-75)  # 175 → 100
        forearm = _R(-5) + (progress / 0.2) * _R(-55)     # -5 → -60
    else:
        wobble = math.sin((t - 0.2 * duration) * 10) * _R(20)
        arm_angle = _R(100) + wobble * 0.3
        forearm = _R(-60) + wobble
    
    return {
        'spine': _R(-90),
        'neck': _R(5),
        'head': _R(5),
        'left_upper_arm': _R(185),
        'left_forearm': _R(5),
        'left_hand': 0.0,
        'right_upper_arm': arm_angle,
        'right_forearm': forearm,
        'right_hand': math.sin(t * 12) * _R(10),
        'left_upper_leg': _R(92),
        'left_lower_leg': _R(-3),
        'left_foot': 0.0,
        'right_upper_leg': _R(88),
        'right_lower_leg': _R(3),
        'right_foot': 0.0,
        'hips': 0.0,
    }


# ─── PUNCH ─────────────────────────────────────────────────

def gen_punch(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Right arm punches forward"""
    p = params or {}
    duration = p.get('duration', 0.4)
    
    progress = min(t / duration, 1.0)
    
    if progress < 0.15:  # wind up
        arm = _R(175) - (progress / 0.15) * _R(95)
        fore = _R(-5) + (progress / 0.15) * _R(85)
        lean = _R(0) - (progress / 0.15) * _R(-5)
    elif progress < 0.5:  # extend
        arm = _R(80) + ((progress - 0.15) / 0.35) * _R(-30)
        fore = _R(80) + ((progress - 0.15) / 0.35) * _R(-100)
        lean = _R(-5) + ((progress - 0.15) / 0.35) * _R(-5)
    else:  # retract
        arm = _R(50) + ((progress - 0.5) / 0.5) * _R(125)
        fore = _R(-20) + ((progress - 0.5) / 0.5) * _R(15)
        lean = _R(-10) + ((progress - 0.5) / 0.5) * _R(10)
    
    return {
        'spine': _R(-90) + lean,
        'neck': 0.0,
        'head': 0.0,
        'left_upper_arm': _R(185),
        'left_forearm': _R(5),
        'left_hand': 0.0,
        'right_upper_arm': arm,
        'right_forearm': fore,
        'right_hand': 0.0,
        'left_upper_leg': _R(92),
        'left_lower_leg': _R(-3),
        'left_foot': 0.0,
        'right_upper_leg': _R(88),
        'right_lower_leg': _R(3),
        'right_foot': 0.0,
        'hips': 0.0,
    }


# ─── FALL ──────────────────────────────────────────────────

def gen_fall(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Fall backward"""
    p = params or {}
    duration = p.get('duration', 1.0)
    
    progress = min(t / duration, 1.0)
    angle = progress * _R(90)
    
    return {
        'spine': _R(-90) + angle,
        'neck': angle * 0.5,
        'head': angle * 0.5,
        'left_upper_arm': _R(185) + angle * 0.7,
        'left_forearm': _R(5) + angle * 0.3,
        'left_hand': 0.0,
        'right_upper_arm': _R(175) - angle * 0.7,
        'right_forearm': _R(-5) - angle * 0.3,
        'right_hand': 0.0,
        'left_upper_leg': _R(92) + angle * 0.5,
        'left_lower_leg': _R(-3) + angle * 0.3,
        'left_foot': 0.0,
        'right_upper_leg': _R(88) - angle * 0.5,
        'right_lower_leg': _R(3) - angle * 0.3,
        'right_foot': 0.0,
        'hips': 0.0,
    }, progress * 40  # y offset


# ─── REGISTRY ──────────────────────────────────────────────

# Each entry: (generator_fn, has_position_offset, default_params)
GENERATORS = {
    'idle':  (gen_idle,  False, {'speed': 1.0}),
    'walk':  (gen_walk,  True,  {'speed': 1.2, 'stride': 55, 'step_height': 12, 'bounce': 3}),
    'run':   (gen_run,   True,  {'speed': 2.0, 'stride': 80, 'step_height': 18, 'bounce': 8}),
    'jump':  (gen_jump,  True,  {'height': 50, 'duration': 0.8}),
    'wave':  (gen_wave,  False, {'duration': 2.0}),
    'punch': (gen_punch, False, {'duration': 0.4}),
    'fall':  (gen_fall,  True,  {'duration': 1.0}),
}


def get_generator(name: str):
    """Get a generator function by name."""
    if name not in GENERATORS:
        raise KeyError(f"Unknown generator: {name}. Available: {list(GENERATORS.keys())}")
    return GENERATORS[name]

def generator_names() -> list:
    return list(GENERATORS.keys())