"""Procedural animation generators — all actions are math, no keyframes

Each generator is a function(time, params) → dict of bone_name → angle.
Angles are RELATIVE to the bone's parent world angle (matches the v3
skeleton hierarchy: shoulders/hips are real bones now).

v3 update (per optimal-rig reference sheet):
  - Leg rest pose: feet point FORWARD (0°), shoulder-width stance (±14°)
  - Arms rest: upper arm hangs at -70°/+70° from the shoulder bone
  - FABRIK leg chains mirror the full leg: hip + upper + lower + ankle + foot
  - All lengths scale-aware: chain bones are rebuilt when character
    scale changes, and the IK targets the ACTUAL ground distance
    (passed in as 'ground' by the engine).

Walk uses FABRIK IK for foot placement — feet plant on ground, no sliding.
NOTE: FABRIK returns ABSOLUTE chain angles; we convert to parent-relative
before returning so the skeleton FK reproduces the solved pose.
"""

import math
from typing import Dict, Any, Tuple
from engine.animation.fabrik import FabrikChain


def _R(deg: float) -> float:
    return deg * math.pi / 180.0


# Rest pose for every bone in the v3 skeleton (must match skeleton.py's
# BoneDef defaults). Generators spread this and override only what they
# animate, so all 25 bones always get a value and nothing freezes.
#
# Sign conventions (all angles parent-relative, y↓, 0°=right/forward):
#   arms & shoulders swing FORWARD  → left −Δ, right −Δ
#   shoulders SHRUG up              → left +Δ, right −Δ
#   hip bones SPREAD wider          → left +Δ, right −Δ
_REST = {
    'hips': 0.0, 'spine': _R(-90), 'chest': 0.0, 'neck': 0.0, 'head': 0.0,
    'left_shoulder': _R(-132), 'right_shoulder': _R(132),
    'left_upper_arm': _R(-38), 'right_upper_arm': _R(38),
    'left_forearm': _R(25), 'right_forearm': _R(-25),
    'left_wrist': 0.0, 'right_wrist': 0.0,
    'left_hand': 0.0, 'right_hand': 0.0,
    'left_hip': _R(99), 'right_hip': _R(81),
    'left_upper_leg': _R(8), 'right_upper_leg': _R(-6),
    'left_lower_leg': _R(-12), 'right_lower_leg': _R(9),
    'left_ankle': 0.0, 'right_ankle': 0.0,
    'left_foot': _R(25), 'right_foot': _R(-25),
}


# ─── Pre-built IK chains for walk ──────────────────────────

_left_leg_chain: FabrikChain = None
_right_leg_chain: FabrikChain = None
_chain_scale: float = 0.0   # scale the cached chains were built for


def _get_leg_chains(scale: float = 1.0) -> Tuple[FabrikChain, FabrikChain]:
    """Get or create leg IK chains, rebuilt whenever the character scale
    changes (bone lengths must match the rendered skeleton — otherwise IK
    solves a tiny chain and feet float above the ground).

    Chain bones mirror the FULL leg from hips → foot tip in head units:
      hip(0.25H) + upper(1.3H) + lower(1.3H) + ankle(0.15H) + foot(0.32H)
    so the solved reach matches the skeleton exactly and the end effector
    is the foot TIP (what the ground contact actually is).
    """
    global _left_leg_chain, _right_leg_chain, _chain_scale
    if _left_leg_chain is None or _chain_scale != scale:
        _chain_scale = scale
        H = 14.0 * scale
        _left_leg_chain = FabrikChain()
        _left_leg_chain.add_bone(0.25 * H)  # hip (down, out)
        _left_leg_chain.add_bone(1.3 * H)   # upper leg
        _left_leg_chain.add_bone(1.3 * H)   # lower leg
        _left_leg_chain.add_bone(0.15 * H)  # ankle
        _left_leg_chain.add_bone(0.32 * H)  # foot
        _left_leg_chain.set_initial_pose([97, 14, -7, 0, 20])
        _right_leg_chain = FabrikChain()
        _right_leg_chain.add_bone(0.25 * H)
        _right_leg_chain.add_bone(1.3 * H)
        _right_leg_chain.add_bone(1.3 * H)
        _right_leg_chain.add_bone(0.15 * H)
        _right_leg_chain.add_bone(0.32 * H)
        _right_leg_chain.set_initial_pose([83, -14, 7, 0, -20])
    return _left_leg_chain, _right_leg_chain


# ─── IDLE ──────────────────────────────────────────────────

def gen_idle(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    p = params or {}
    speed = p.get('speed', 1.0)
    s = t * speed
    breath = math.sin(s * 1.5)
    return {
        **_REST,
        'spine': _R(-90) + breath * _R(1),
        'chest': math.sin(s * 1.5 + 1.0) * _R(1.5),  # breathing — chest
        # joint rises/falls subtly; this is the torso-twist/breathe pivot
        'head': math.sin(s * 1.5 + 0.5) * _R(1),
        # shoulders ride the breath: ribcage expands → shoulders shrug up
        # a degree, mirrored so the chest widens rather than leaning
        'left_shoulder': _R(-132) + breath * _R(1),
        'right_shoulder': _R(132) - breath * _R(1),
        # arms hang naturally from the shoulder bones with a small gap —
        # clearly relaxed elbows (30° bend), slight asymmetry (right arm
        # ~3° more open) so the pose doesn't read as mirrored/robotic
        'left_upper_arm': _R(-38) + math.sin(s * 1.2) * _R(2),
        'left_forearm': _R(30) + math.sin(s * 1.3) * _R(2),   # relaxed elbow
        'right_upper_arm': _R(41) + math.sin(s * 1.2 + math.pi) * _R(2),
        'right_forearm': _R(-23) + math.sin(s * 1.3 + math.pi) * _R(2),
        # wrists trail the forearm sway a beat late — dead weight, not driven
        'left_wrist': math.sin(s * 1.3 - 0.6) * _R(2),
        'right_wrist': math.sin(s * 1.3 + math.pi - 0.6) * _R(2),
        # legs and ankles stay in rest pose — idle IS the rest pose
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

    FABRIK get_angles() returns ABSOLUTE segment directions (chain base at
    origin). The skeleton FK expects parent-relative angles, so we convert:
      rel[0] = abs[0] - 0          (hip bone, hips world angle = 0)
      rel[i] = abs[i] - abs[i-1]   (each following bone)
    """
    p = params or {}
    scale = p.get('scale', 1.0)
    speed = p.get('speed', 1.2)
    # Stride scales with LEG REACH, not an arbitrary constant — the IK foot
    # targets must stay within the chain's reachable envelope or feet float.
    # Full leg chain = 3.32H = 46.5px at scale 1; natural stride ≈ 45% of that.
    leg_reach = 46.5 * scale
    stride = p.get('stride', 22) * scale          # ~0.45 × leg reach
    step_h = p.get('step_height', 5) * scale      # lift proportional too
    bounce = p.get('bounce', 1.5) * scale
    ground = p.get('ground', 40.0 * scale)  # hips→ground distance (scale-aware)
    lateral = 0.2 * 14.0 * scale                  # ~0.2H: shoulder-width feet

    s = t * speed

    # Gait cycle: each leg cycles through stance→swing
    left_phase = s % 1.0            # 0-1: left leg gait cycle
    right_phase = (s + 0.5) % 1.0   # 0-1: right leg (offset)

    steps_completed = int(s)
    body_x = s * stride * 0.8

    # Gait: 0-0.6 = stance, 0.6-1.0 = swing
    def get_foot_target(phase, side_offset):
        """Get foot target position for a leg at its current phase."""
        if phase < 0.6:  # STANCE — foot planted
            foot_progress = 0
            lift = 0
        else:  # SWING — foot lifts and moves forward
            swing_prog = (phase - 0.6) / 0.4
            foot_progress = swing_prog
            lift = math.sin(swing_prog * math.pi) * step_h

        last_landing = (steps_completed + (0 if side_offset < 0 else 0.5)) * stride
        next_landing = last_landing + stride

        # Foot targets are in the IK chain's local space (base = hip). The
        # body has already advanced by body_x, so subtract it — the planted
        # foot then stays at a FIXED world position (behind the advancing
        # hip) instead of drifting forward with the body, which would push
        # it outside the chain's reachable envelope and float the foot.
        if phase < 0.6:  # Stance: foot planted at last landing
            foot_x = last_landing - body_x + lateral * side_offset
        else:  # Swing: interpolate toward next landing
            foot_x = last_landing - body_x + foot_progress * stride + lateral * side_offset

        foot_y = ground - lift  # ground below hips, minus swing lift

        # Clamp to the chain's reachable envelope: at ground level the leg
        # can only reach ±sqrt(L² - ground²) horizontally. Beyond that,
        # FABRIK stretches toward the target and the foot LIFTS off the
        # ground — pull x inward so the foot stays planted instead.
        chain_len = 46.5 * scale
        max_x = math.sqrt(max(chain_len * chain_len - foot_y * foot_y, 0.0)) * 0.97
        foot_x = max(-max_x, min(max_x, foot_x))

        return foot_x, foot_y

    lfx, lfy = get_foot_target(left_phase, -1)
    rfx, rfy = get_foot_target(right_phase, 1)

    # Solve left leg IK
    l_chain, r_chain = _get_leg_chains(scale)
    l_chain.set_base(0, 0)
    l_chain.set_initial_pose([97, 14, -7, 0, 20])
    l_chain.solve(lfx, lfy, tolerance=1.0)
    l_angles = l_chain.get_angles()

    # Solve right leg IK
    r_chain.set_base(0, 0)
    r_chain.set_initial_pose([83, -14, 7, 0, -20])
    r_chain.solve(rfx, rfy, tolerance=1.0)
    r_angles = r_chain.get_angles()

    # Convert ABSOLUTE chain angles → parent-relative skeleton angles.
    # Chain mirrors the full leg: [hip, upper, lower, ankle, foot], and
    # the skeleton's hips bone has world angle 0 (root), so:
    #   rel[0] = abs[0] - 0          (hip bone)
    #   rel[i] = abs[i] - abs[i-1]   (each following bone)
    if len(l_angles) >= 5:
        l_hip = l_angles[0]
        l_upper = l_angles[1] - l_angles[0]
        l_lower = l_angles[2] - l_angles[1]
        l_ankle = l_angles[3] - l_angles[2]
        l_foot = l_angles[4] - l_angles[3]
    else:
        l_hip, l_upper, l_lower, l_ankle, l_foot = _R(97), _R(14), _R(-7), 0.0, _R(20)
    if len(r_angles) >= 5:
        r_hip = r_angles[0]
        r_upper = r_angles[1] - r_angles[0]
        r_lower = r_angles[2] - r_angles[1]
        r_ankle = r_angles[3] - r_angles[2]
        r_foot = r_angles[4] - r_angles[3]
    else:
        r_hip, r_upper, r_lower, r_ankle, r_foot = _R(83), _R(-14), _R(7), 0.0, _R(-20)

    # Body bob and arm swing (sine waves for these)
    double_s = math.sin(s * math.pi * 2)
    arm_swing = math.sin(s * math.pi) * _R(25)
    arm_swing_opp = math.sin(s * math.pi + math.pi) * _R(25)
    # Counter-rotation: the torso twists opposite the pelvis each step, and
    # the shoulder bones carry that twist to the arms (left arm leads while
    # the right leg leads). Scaled down from the arm swing — the shoulder
    # girdle rotates far less than the limb hanging off it.
    chest_twist = arm_swing * 0.12

    return {
        **_REST,
        'spine': _R(-88) + double_s * _R(2),
        'chest': chest_twist,
        'head': double_s * _R(1),
        'left_shoulder': _R(-132) - arm_swing * 0.15,
        'right_shoulder': _R(132) - arm_swing_opp * 0.15,
        'left_upper_arm': _R(-38) - arm_swing,
        'left_forearm': _R(10) + arm_swing * 0.6,
        # wrist lags the forearm (soft tissue drag), hand follows the wrist
        'left_wrist': -arm_swing * 0.2,
        'left_hand': -arm_swing * 0.4,
        'right_upper_arm': _R(38) - arm_swing_opp,
        'right_forearm': _R(-10) + arm_swing_opp * 0.6,
        'right_wrist': -arm_swing_opp * 0.2,
        'right_hand': -arm_swing_opp * 0.4,
        # legs come straight from the IK solution (hip → ankle → foot)
        'left_hip': l_hip,
        'left_upper_leg': l_upper,
        'left_lower_leg': l_lower,
        'left_ankle': l_ankle,
        'left_foot': l_foot,
        'right_hip': r_hip,
        'right_upper_leg': r_upper,
        'right_lower_leg': r_lower,
        'right_ankle': r_ankle,
        'right_foot': r_foot,
        'hips': -chest_twist,   # pelvis counter-rotates against the chest
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
    # Running counter-rotates the torso hard — shoulders and pelvis fight
    # each other to cancel the angular momentum of the swinging limbs.
    twist = swing * _R(7)

    return {
        **_REST,
        'spine': _R(-95) + double * _R(3),  # lean forward
        'chest': twist,
        'neck': _R(-5),
        'head': _R(-5) + double * _R(2),
        'left_shoulder': _R(-132) - swing * _R(8),
        'right_shoulder': _R(132) - swing_opp * _R(8),
        'left_upper_arm': _R(-38) - swing * _R(45),  # bigger arm swing
        'left_forearm': _R(30) + swing * _R(25),
        # sprinter's arm: wrist stays firm, hand drives through
        'left_wrist': -swing * _R(8),
        'left_hand': -swing * _R(20),
        'right_upper_arm': _R(38) - swing_opp * _R(45),
        'right_forearm': _R(-30) + swing_opp * _R(25),
        'right_wrist': -swing_opp * _R(8),
        'right_hand': -swing_opp * _R(20),
        # hip bones swing with the stride — the pelvis drops on the swing
        # side (Trendelenburg tilt) which the hip bone angle expresses
        'left_hip': _R(99) + swing * _R(5),
        # Thigh swing is measured from the HIP bone (world ~99°, pointing
        # down-out), not from the pelvis — so ±25° keeps the leg inside a
        # 74°–124° world arc. The v2 value of ±50° was relative to a
        # 0° parent and throws the thigh past horizontal on this rig.
        'left_upper_leg': _R(8) + swing * _R(25),
        # Knee only ever flexes one way: a constant 18° bend keeps it from
        # hyperextending at the extremes of the swing.
        'left_lower_leg': _R(-18) - swing * _R(18),
        # ankle dorsiflexes on lift, plantarflexes on push-off
        'left_ankle': lift * _R(12) - _R(4),
        'left_foot': _R(20) + lift * _R(15),
        'right_hip': _R(81) + swing_opp * _R(5),
        'right_upper_leg': _R(-6) + swing_opp * _R(25),
        'right_lower_leg': _R(18) - swing_opp * _R(18),
        'right_ankle': -(lift * _R(12) - _R(4)),
        'right_foot': _R(-20) + lift * _R(15),
        'hips': -twist,
    }


# ─── JUMP ──────────────────────────────────────────────────

def gen_jump(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Jump poses — crouch → reach → tuck → land
    Physics handles the actual vertical movement, this just poses bones.
    """
    p = params or {}
    duration = p.get('duration', 0.8)

    progress = min(t / duration, 1.0)

    if progress < 0.2:  # crouch
        phase = progress / 0.2
        crouch = phase
        spine_lean = _R(5) * crouch
        arm_up = crouch * _R(30)
        leg_crouch = crouch * _R(25)
    elif progress < 0.4:  # spring up
        phase = (progress - 0.2) / 0.2
        spine_lean = _R(5) * (1 - phase)
        arm_up = _R(30) * (1 - phase) + phase * _R(80)
        leg_crouch = _R(25) * (1 - phase)
    elif progress < 0.6:  # float / tuck
        phase = (progress - 0.4) / 0.2
        arm_up = _R(80)
        spine_lean = 0
        leg_crouch = -_R(5) * (1 + phase * 0.5)  # legs tuck slightly
    elif progress < 0.8:  # coming down
        phase = (progress - 0.6) / 0.2
        arm_up = _R(80) * (1 - phase * 0.5)
        spine_lean = phase * _R(3)
        leg_crouch = -_R(7) * (1 - phase) + phase * _R(10)
    else:  # land
        phase = (progress - 0.8) / 0.2
        leg_crouch = _R(10) + phase * _R(15)  # deep crouch on land
        arm_up = _R(40) * (1 - phase)
        spine_lean = _R(3) * (1 - phase)

    return {
        **_REST,
        'spine': _R(-90) + spine_lean,
        'neck': _R(5) * (1 - progress),
        'head': _R(5) * (1 - progress),
        # shoulders lift with the arms — a big arm raise is half scapula
        'left_shoulder': _R(-132) - arm_up * 0.25,
        'right_shoulder': _R(132) + arm_up * 0.25,
        'left_upper_arm': _R(-38) - arm_up,
        'left_forearm': _R(5) - arm_up * 0.3,
        'left_wrist': -arm_up * 0.15,
        'left_hand': -arm_up * 0.2,
        'right_upper_arm': _R(38) + arm_up,
        'right_forearm': _R(-5) + arm_up * 0.3,
        'right_wrist': arm_up * 0.15,
        'right_hand': arm_up * 0.2,
        # crouch spreads the hips slightly (weight-bearing squat stance)
        'left_hip': _R(99) + leg_crouch * 0.12,
        'left_upper_leg': _R(8) + leg_crouch,
        'left_lower_leg': _R(-12) - leg_crouch * 0.6,
        # ankle absorbs the crouch: deeper squat = more dorsiflexion, and
        # it plantarflexes (points) during the airborne tuck
        'left_ankle': leg_crouch * 0.4,
        'left_foot': _R(20),
        'right_hip': _R(81) - leg_crouch * 0.12,
        'right_upper_leg': _R(-6) + leg_crouch,
        'right_lower_leg': _R(9) - leg_crouch * 0.6,
        'right_ankle': -leg_crouch * 0.4,
        'right_foot': _R(-20),
    }


# ─── WAVE ──────────────────────────────────────────────────

def gen_wave(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Right arm waves — arm raises, hand oscillates"""
    p = params or {}
    duration = p.get('duration', 2.0)

    progress = min(t / duration, 1.0)

    # Arm raise
    if progress < 0.2:
        raise_phase = progress / 0.2
        arm_angle = _R(38) + raise_phase * _R(-100)  # 38 → -62
        forearm = _R(-25) + raise_phase * _R(-55)     # -25 → -80
    else:
        raise_phase = 1.0
        wobble = math.sin((t - 0.2 * duration) * 10) * _R(20)
        arm_angle = _R(-35) + wobble * 0.3
        forearm = _R(-80) + wobble

    return {
        **_REST,
        'spine': _R(-90),
        'neck': _R(5),
        'head': _R(5),
        # raising an arm overhead rotates the scapula upward — the shoulder
        # joint itself lifts ~20°, without which the arm looks socket-locked
        'right_shoulder': _R(132) + raise_phase * _R(20),
        'right_upper_arm': arm_angle,
        'right_forearm': forearm,
        # the wave lives in the wrist: hand flicks, wrist carries most of it
        'right_wrist': math.sin(t * 12) * _R(18),
        'right_hand': math.sin(t * 12) * _R(10),
        # the standing half isn't static: weight shifts onto the left leg to
        # counterbalance the raised arm, and the idle arm keeps breathing
        'left_shoulder': _R(-132) - raise_phase * _R(4),
        'left_upper_arm': _R(-38) + math.sin(t * 1.2) * _R(2),
        'left_wrist': math.sin(t * 1.2 - 0.6) * _R(2),
        'left_hip': _R(99) + raise_phase * _R(2),
        'right_hip': _R(81) + raise_phase * _R(2),
        'left_ankle': raise_phase * _R(2),
        'right_ankle': raise_phase * _R(2),
    }


# ─── PUNCH ─────────────────────────────────────────────────

def gen_punch(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Right arm punches forward — fast and snappy"""
    p = params or {}
    duration = p.get('duration', 0.3)  # faster default

    progress = min(t / duration, 1.0)

    if progress < 0.12:  # wind up (quick)
        phase = progress / 0.12
        arm = _R(38) - phase * _R(95)
        fore = _R(-25) + phase * _R(85)
        lean = phase * _R(-5)
        chest_twist = phase * _R(-4)   # chest coils back
        hip_twist = -chest_twist * 0.5
        reach = -phase * 0.3           # punching shoulder pulls BACK
    elif progress < 0.4:  # extend (snap) — chest rotates INTO the punch
        phase = (progress - 0.12) / 0.28
        arm = _R(-25) - phase * _R(40)
        fore = _R(60) - phase * _R(110)
        lean = _R(-5) - phase * _R(5)
        chest_twist = _R(-4) - phase * _R(8)   # shoulder follows chest
        hip_twist = -chest_twist * 0.5          # hip counter-rotates
        reach = -0.3 + phase * 1.3     # shoulder THROWS forward — the last
        # few inches of a punch come from the shoulder, not the elbow
    else:  # retract
        phase = (progress - 0.4) / 0.6
        arm = _R(-65) + phase * _R(135)
        fore = _R(-50) + phase * _R(25)
        lean = _R(-10) + phase * _R(10)
        chest_twist = _R(-12) + phase * _R(12)
        hip_twist = -chest_twist * 0.5
        reach = 1.0 - phase

    return {
        **_REST,
        'spine': _R(-90) + lean,
        'chest': chest_twist,           # torso articulation: chest drives
        # the punch, shoulders follow, hips counter-rotate — power transfer
        'hips': hip_twist,
        # right shoulder drives forward with the strike, left retracts as
        # the guard hand pulls back (equal and opposite, boxing mechanics)
        'right_shoulder': _R(132) + reach * _R(12),
        'left_shoulder': _R(-132) + reach * _R(6),
        'left_upper_arm': _R(-38) + reach * _R(10),   # guard hand chambers
        'left_forearm': _R(25) - reach * _R(15),
        'left_wrist': -reach * _R(6),                 # guard fist tightens
        'right_upper_arm': arm,
        'right_forearm': fore,
        # wrist locks straight at full extension (a bent wrist breaks on
        # impact), stays loose during wind-up and retract
        'right_wrist': (1.0 - abs(reach)) * _R(10),
        # planted feet: rear ankle rolls over for the push-off that drives
        # the hip rotation — punches start from the ground
        'right_ankle': -reach * _R(8),
        'left_ankle': reach * _R(3),
        # hip bones follow the pelvis rotation the push-off generates
        'left_hip': _R(99) + hip_twist * 0.5,
        'right_hip': _R(81) + hip_twist * 0.5,
    }


# ─── FALL ──────────────────────────────────────────────────

def gen_fall(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Fall backward — physics handles the falling trajectory"""
    p = params or {}
    duration = p.get('duration', 0.8)

    progress = min(t / duration, 1.0)
    angle = progress * _R(75)  # max 75° tilt

    return {
        **_REST,
        'spine': _R(-90) + angle,
        'neck': angle * 0.4,
        'head': angle * 0.4,
        # startle reflex: shoulders fly open and up as the arms windmill
        'left_shoulder': _R(-132) + angle * 0.3,
        'right_shoulder': _R(132) - angle * 0.3,
        'left_upper_arm': _R(-38) + angle * 0.6,
        'left_forearm': _R(5) + angle * 0.3,
        # hands flail loosely — wrists lead, no muscle tone in a fall
        'left_wrist': angle * 0.35,
        'left_hand': angle * 0.25,
        'right_upper_arm': _R(38) - angle * 0.6,
        'right_forearm': _R(-5) - angle * 0.3,
        'right_wrist': -angle * 0.35,
        'right_hand': -angle * 0.25,
        # Both legs swing the SAME way — the body rotates backward as a unit
        # and the feet come up together. Mirroring the sign here (as v2 did,
        # when upper_leg hung off a 0° parent) scissors the legs apart on the
        # v3 rig, where each thigh already points out along its hip bone.
        'left_hip': _R(99) + angle * 0.1,
        'left_upper_leg': _R(8) + angle * 0.35,
        'left_lower_leg': _R(-12) - angle * 0.25,   # knees flex, never lock
        # feet leave the ground: ankles go slack and toes drop
        'left_ankle': angle * 0.3,
        'left_foot': _R(20),
        'right_hip': _R(81) - angle * 0.1,
        'right_upper_leg': _R(-6) + angle * 0.35,
        'right_lower_leg': _R(9) - angle * 0.25,
        'right_ankle': -angle * 0.3,
        'right_foot': _R(-20),
    }


# ─── REGISTRY ──────────────────────────────────────────────

# Each entry: (generator_fn, has_position_offset, default_params)
GENERATORS = {
    'idle':  (gen_idle,  False, {'speed': 1.0}),
    'walk':  (gen_walk,  True,  {'speed': 1.2, 'stride': 55, 'step_height': 12, 'bounce': 3}),
    'run':   (gen_run,   True,  {'speed': 2.0, 'stride': 80, 'step_height': 18, 'bounce': 8}),
    'jump':  (gen_jump,  False, {'height': 50, 'duration': 0.8}),
    'wave':  (gen_wave,  False, {'duration': 2.0}),
    'punch': (gen_punch, False, {'duration': 0.4}),
    'fall':  (gen_fall,  False, {'duration': 0.8}),
}


def get_generator(name: str):
    """Get a generator function by name."""
    if name not in GENERATORS:
        raise KeyError(f"Unknown generator: {name}. Available: {list(GENERATORS.keys())}")
    return GENERATORS[name]


def generator_names() -> list:
    return list(GENERATORS.keys())


if __name__ == '__main__':
    from engine.animation.skeleton import build_bipedal_skeleton

    bone_names = {b.name for b in build_bipedal_skeleton().bones}
    assert bone_names == set(_REST), f"_REST out of sync: {bone_names ^ set(_REST)}"

    # Every generator must cover all 25 bones, stay finite, and actually
    # move the new v3 joints somewhere across the action (a joint that
    # never changes AND never leaves rest is a frozen joint).
    for name, (fn, _, defaults) in GENERATORS.items():
        samples = [fn(t * 0.05, defaults) for t in range(40)]
        for pose in samples:
            assert set(pose) == bone_names, f"{name} missing {bone_names - set(pose)}"
            assert all(math.isfinite(v) for v in pose.values()), f"{name} non-finite"
        for joint in ('left_shoulder', 'right_shoulder', 'left_wrist', 'right_wrist',
                      'left_ankle', 'right_ankle', 'left_hip', 'right_hip'):
            vals = [p[joint] for p in samples]
            moved = max(vals) - min(vals) > 1e-6
            posed = abs(vals[0] - _REST[joint]) > 1e-6
            assert moved or posed or name == 'idle', f"{name}: {joint} frozen at rest"

    print(f"OK — {len(GENERATORS)} generators × {len(bone_names)} bones")
