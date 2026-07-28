"""Procedural animation generators — all actions are math, no keyframes

Each generator is a function(time, params) → dict of bone_name → angle.
Walk uses FABRIK IK for foot placement — feet plant on ground, no sliding.
"""

import math
from typing import Dict, Any, Tuple
from engine.animation.fabrik import FabrikChain


def _R(deg: float) -> float:
    return deg * math.pi / 180.0


# ─── Pre-built IK chains for walk ──────────────────────────

_left_leg_chain: FabrikChain = None
_right_leg_chain: FabrikChain = None

def _get_leg_chains() -> Tuple[FabrikChain, FabrikChain]:
    """Get or create leg IK chains. Built once and cached."""
    global _left_leg_chain, _right_leg_chain
    if _left_leg_chain is None:
        _left_leg_chain = FabrikChain()
        _left_leg_chain.add_bone(16)  # upper leg
        _left_leg_chain.add_bone(16)  # lower leg
        _left_leg_chain.add_bone(6)   # foot
        _left_leg_chain.set_initial_pose([90, 0, 0])
    if _right_leg_chain is None:
        _right_leg_chain = FabrikChain()
        _right_leg_chain.add_bone(16)
        _right_leg_chain.add_bone(16)
        _right_leg_chain.add_bone(6)
        _right_leg_chain.set_initial_pose([90, 0, 0])
    return _left_leg_chain, _right_leg_chain


# ─── IDLE ──────────────────────────────────────────────────

def gen_idle(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
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
        'left_upper_leg': _R(92), 'left_lower_leg': _R(-3), 'left_foot': 0.0,
        'right_upper_leg': _R(88), 'right_lower_leg': _R(3), 'right_foot': 0.0,
        'hips': 0.0,
    }


# ─── WALK — FABRIK-BASED FOOT PLACEMENT ───────────────────

def gen_walk(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Walk using FABRIK IK for foot placement.
    
    Algorithm per frame:
      1. Determine which foot is stance vs swing based on gait cycle
      2. Stance foot stays planted at its landing position
      3. Swing foot lifts and moves toward next landing position
      4. FABRIK solves hip→knee→ankle angles to reach foot targets
      5. Hips adjust height based on leg extension
    
    Parameters: speed, stride, step_height
    """
    p = params or {}
    speed = p.get('speed', 1.2)
    stride = p.get('stride', 55)
    step_h = p.get('step_height', 12)
    bounce = p.get('bounce', 3)
    
    s = t * speed
    
    # Gait cycle: each leg cycles through stance→swing
    # left leg cycle = s (0 to 1 = one full step pair)
    # right leg cycle = s + 0.5 (offset by half)
    left_phase = s % 1.0        # 0-1: left leg gait cycle
    right_phase = (s + 0.5) % 1.0  # 0-1: right leg (offset)
    
    # Step landing positions
    # Each full cycle (s goes from 0 to 1) moves one stride forward
    # Number of completed steps determines landing positions
    steps_completed = int(s)  # how many full stride cycles completed
    body_x = s * stride * 0.8  # body moves forward continuously
    
    # Gait: 0-0.6 = stance, 0.6-1.0 = swing
    def get_foot_target(phase, side_offset):
        """Get foot target position for a leg at its current phase."""
        # Foot offset from body center (side_to_side)
        lateral = side_offset * 10  # ±10px left/right
        
        # Forward position: during stance, foot stays planted at landing spot
        # During swing, foot moves from last landing to next landing
        if phase < 0.6:  # STANCE — foot planted
            foot_progress = 0  # no forward movement, foot stays
            lift = 0
        else:  # SWING — foot lifts and moves forward
            swing_prog = (phase - 0.6) / 0.4  # 0→1 during swing
            foot_progress = swing_prog
            # Lift follows arc: up at start, down at end
            lift = math.sin(swing_prog * math.pi) * step_h
        
        # Landing positions
        last_landing = (steps_completed + (0 if side_offset < 0 else 0.5)) * stride
        next_landing = last_landing + stride
        
        foot_x = body_x + lateral  # default: follows body
        
        if phase < 0.6:  # Stance: foot planted at last landing
            foot_x = last_landing + lateral
        else:  # Swing: interpolate toward next landing
            foot_x = last_landing + foot_progress * stride + lateral
        
        foot_y = 40 - lift  # ground at y=40 below hips
        
        return foot_x, foot_y
    
    lfx, lfy = get_foot_target(left_phase, -1)
    rfx, rfy = get_foot_target(right_phase, 1)
    
    # Solve left leg IK
    l_chain, r_chain = _get_leg_chains()
    l_chain.set_base(0, 0)
    l_chain.set_initial_pose([90, 0, 0])
    l_chain.solve(lfx, lfy, tolerance=1.0)
    l_angles = l_chain.get_angles()
    
    # Solve right leg IK
    r_chain.set_base(0, 0)
    r_chain.set_initial_pose([90, 0, 0])
    r_chain.solve(rfx, rfy, tolerance=1.0)
    r_angles = r_chain.get_angles()
    
    # Body bob and arm swing (sine waves for these)
    double_s = math.sin(s * math.pi * 2)
    arm_swing = math.sin(s * math.pi) * _R(25)
    arm_swing_opp = math.sin(s * math.pi + math.pi) * _R(25)
    
    return {
        'spine': _R(-88) + double_s * _R(2),
        'neck': 0.0,
        'head': double_s * _R(1),
        'left_upper_arm': _R(185) - arm_swing,
        'left_forearm': _R(10) + arm_swing * 0.6,
        'left_hand': -arm_swing * 0.4,
        'right_upper_arm': _R(175) - arm_swing_opp,
        'right_forearm': _R(-10) + arm_swing_opp * 0.6,
        'right_hand': -arm_swing_opp * 0.4,
        'left_upper_leg': l_angles[0] if len(l_angles) > 0 else _R(90),
        'left_lower_leg': l_angles[1] if len(l_angles) > 1 else 0.0,
        'left_foot': l_angles[2] if len(l_angles) > 2 else 0.0,
        'right_upper_leg': r_angles[0] if len(r_angles) > 0 else _R(90),
        'right_lower_leg': r_angles[1] if len(r_angles) > 1 else 0.0,
        'right_foot': r_angles[2] if len(r_angles) > 2 else 0.0,
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