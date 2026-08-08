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

    # Knee drive: the recovery knee flexes hard mid-swing (heel kick up
    # behind), straightening as the leg reaches forward for the next
    # contact. |swing| peaks at mid-swing both directions, so it drives
    # the flex at exactly the right times.
    knee_flex = _R(22) + abs(swing) * _R(52)   # 22°..74° — real runner bend
    # Elbow pump: elbows stay bent ~85° through the whole arm swing,
    # opening slightly at the extremes (a pumping arm never locks).
    elbow_bend = _R(85) - abs(swing) * _R(25)  # 60°..85°

    return {
        **_REST,
        # Forward lean: spine -79 tilts the torso ~10-12° FORWARD into the
        # run (measured: spine -90 ≈ vertical, -88 ≈ +2° forward, so less
        # negative = more forward on this rig). Real runners lean 10–20°;
        # anything under ~8° reads as "upright" on a still frame.
        'spine': _R(-79) + double * _R(3),
        'chest': twist,
        'neck': _R(-5),
        'head': _R(-5) + double * _R(2),
        'left_shoulder': _R(-132) - swing * _R(8),
        'right_shoulder': _R(132) - swing_opp * _R(8),
        'left_upper_arm': _R(-38) - swing * _R(48),  # bigger arm swing
        'left_forearm': elbow_bend,                   # pumps bent, not flails
        # wrist stays firm, hand drives through — sprinter's pump
        'left_wrist': -swing * _R(8),
        'left_hand': -swing * _R(20),
        'right_upper_arm': _R(38) - swing_opp * _R(48),
        'right_forearm': -elbow_bend,
        'right_wrist': -swing_opp * _R(8),
        'right_hand': -swing_opp * _R(20),
        # hip bones swing with the stride — the pelvis drops on the swing
        # side (Trendelenburg tilt) which the hip bone angle expresses
        'left_hip': _R(99) + swing * _R(5),
        # Thigh swing measured from the HIP bone (world ~99°, pointing
        # down-out), so ±25° keeps the leg inside a 74°–124° world arc.
        'left_upper_leg': _R(8) + swing * _R(25),
        # Knee flexes HARD mid-swing (heel kick), straightens at contact —
        # the flex peaks on |swing| so both the drive and recovery read
        'left_lower_leg': -knee_flex,
        # ankle dorsiflexes on lift, plantarflexes on push-off
        'left_ankle': lift * _R(12) - _R(4),
        'left_foot': _R(20) + lift * _R(15),
        'right_hip': _R(81) + swing_opp * _R(5),
        'right_upper_leg': _R(-6) + swing_opp * _R(25),
        'right_lower_leg': knee_flex,
        'right_ankle': -(lift * _R(12) - _R(4)),
        'right_foot': _R(-20) + lift * _R(15),
        'hips': -twist,
    }


# ─── JUMP ──────────────────────────────────────────────────

def gen_jump(t: float, params: Dict[str, Any] = None) -> Dict[str, float]:
    """Jump poses — crouch → spring → tuck → descend → land.

    Physics handles the vertical arc; this poses the bones. The launch
    impulse is DELAYED (play_action sets impulse_time=0.2) so the crouch
    fully reads before the body lifts — without anticipation a jump
    looks like the ground just dropped away.

    Timeline (duration 1.1s ≈ full physics flight: launch@0.2, apex@0.63,
    land@1.06):
      0.00–0.20  CROUCH  — deep knee bend, arms wind UP-back, spine braces
      0.20–0.42  SPRING  — legs extend hard, arms throw UP overhead
      0.42–0.72  AIR     — knees tuck, arms stay up, slight spine arch
      0.72–0.92  DESCEND — legs extend toward landing, arms start down
      0.92–1.10  LAND    — deep absorbing crouch, arms swing back
    """
    p = params or {}
    duration = p.get('duration', 1.1)

    progress = min(t / duration, 1.0)

    if progress < 0.2:  # CROUCH — wind up
        ph = progress / 0.2
        leg_bend = ph * 40           # deep
        arm_wind = ph * 45           # arms swing up-BACK (negative raise)
        lean = -ph * 3               # spine braces slightly back
    elif progress < 0.42:  # SPRING
        ph = (progress - 0.2) / 0.22
        leg_bend = 40 * (1 - ph)
        arm_wind = 45 * (1 - ph) - ph * 100   # whip from back to overhead
        lean = -3 * (1 - ph) + ph * 6         # spine drives forward-up
    elif progress < 0.72:  # AIR — tuck
        ph = (progress - 0.42) / 0.3
        leg_bend = 15 + ph * 20     # knees tuck up
        arm_wind = -100 - ph * 8    # arms stay overhead, slight settle
        lean = 6 - ph * 4
    elif progress < 0.92:  # DESCEND
        ph = (progress - 0.72) / 0.2
        leg_bend = 35 * (1 - ph)    # extend toward landing
        arm_wind = -108 + ph * 30   # arms sweep down-out
        lean = 2 - ph * 2
    else:  # LAND — absorb
        ph = (progress - 0.92) / 0.18
        leg_bend = 45 + ph * 5      # deep crouch on impact
        arm_wind = -78 - ph * 30    # arms swing back for balance
        lean = ph * 4

    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'neck': _R(lean * 0.5),
        'head': _R(lean * 0.5),
        # shoulders ride the arm raise (scapula rotation)
        'left_shoulder': _R(-132) + arm_wind * 0.2,
        'right_shoulder': _R(132) - arm_wind * 0.2,
        # arm_wind positive = arms wind UP-BACK (hand near shoulder);
        # negative = arms overhead / sweeping down (hand above head)
        'left_upper_arm': _R(-38) + _R(arm_wind),
        'left_forearm': _R(10) + _R(arm_wind * 0.35),
        'left_wrist': _R(arm_wind * 0.15),
        'left_hand': _R(arm_wind * 0.2),
        'right_upper_arm': _R(38) - _R(arm_wind),
        'right_forearm': _R(-10) - _R(arm_wind * 0.35),
        'right_wrist': -_R(arm_wind * 0.15),
        'right_hand': -_R(arm_wind * 0.2),
        # leg_bend = knee flexion; thigh drives forward on spring
        'left_hip': _R(99) + _R(leg_bend * 0.12),
        'left_upper_leg': _R(8) + _R(leg_bend * 0.9),
        'left_lower_leg': _R(-12) - _R(leg_bend * 0.75),
        'left_ankle': _R(leg_bend * 0.25),
        'left_foot': _R(20),
        'right_hip': _R(81) - _R(leg_bend * 0.12),
        'right_upper_leg': _R(-6) + _R(leg_bend * 0.9),
        'right_lower_leg': _R(9) - _R(leg_bend * 0.75),
        'right_ankle': -_R(leg_bend * 0.25),
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


# ─── SIT / STAND UP / KNEEL / LIE DOWN / GET UP ────────────
# One-shot height-driven actions. Each returns (pose, y_offset) where
# y_offset is the total hips descent in px from the height the action
# STARTED at (positive = down). Engine.step applies it to position.y and
# moves the physics ground to follow.
#
# Geometry targets (hips rest height above floor ≈ 46 * scale px):
#   sit:      hips ≈ 22 * scale above floor, knees up-forward, feet planted
#   kneel:    knees ON floor, hips ≈ 18 * scale above floor, shins flat back
#   lie_down: whole body horizontal ON floor, hips ≈ 2 * scale above floor
# sit ↔ stand_up and lie_down ↔ get_up are exact reversals (shared pose
# functions), so chaining them is perfectly continuous.

def _ease(p: float) -> float:
    """Smoothstep — zero velocity at both ends (no jerk)."""
    return p * p * (3 - 2 * p)


def _sit_pose(progress: float, scale: float):
    """Shared sit pose: progress 0 = standing, 1 = seated on the floor.

    Legs: thighs fold to nearly horizontal (world ~10°), shins drop to
    plant the feet on the floor, torso relaxes back a few degrees, hands
    come toward the knees. Feet land exactly on the floor line.
    """
    e = _ease(progress)
    drop = 33.5 * scale * e            # hips down to ~50px above floor (ground sit)
    # Per-side thigh/shin/foot deltas: the v3 hip bones are mirror images
    # (99° vs 81°), so a shared delta folds the RIGHT leg the wrong way.
    # Targets (world): thigh −24.6° (knees up, 15px above hips), shin 53°
    # (feet planted), foot 15° (flat).
    thigh_l = -141.6 * e
    thigh_r = -89.6 * e
    shin_l = 89.6 * e
    shin_r = 68.6 * e
    ankle = 4 * e
    foot_l = -63 * e
    foot_r = -13 * e                    # pose is _R(-25 - foot_r) → rel −38
    spine = -10 * e                    # torso relaxes back
    hip_spread = 10 * e
    arm_fwd = 30 * e                   # upper arms swing forward
    arm_bend = 38 * e                  # elbows fold (hands to knees)
    return {
        **_REST,
        'hips': _R(0),
        'spine': _R(-90) + _R(spine),
        'neck': _R(-3 * e),
        'head': _R(-3 * e),
        'left_hip': _R(99 + hip_spread),
        'right_hip': _R(81 - hip_spread),
        'left_upper_leg': _R(8 + thigh_l),
        'left_lower_leg': _R(-12 + shin_l),
        'left_ankle': _R(ankle),
        'left_foot': _R(25 + foot_l),
        'right_upper_leg': _R(-6 + thigh_r),
        'right_lower_leg': _R(9 + shin_r),
        'right_ankle': -_R(ankle),
        'right_foot': _R(-25 - foot_r),
        'left_shoulder': _R(-132 + 5 * e),
        'left_upper_arm': _R(-38 - arm_fwd),
        'left_forearm': _R(25 + arm_bend),
        'left_wrist': _R(arm_bend * 0.3),
        'left_hand': _R(arm_bend * 0.4),
        'right_shoulder': _R(132 - 5 * e),
        'right_upper_arm': _R(38 + arm_fwd),
        'right_forearm': _R(-25 - arm_bend),
        'right_wrist': -_R(arm_bend * 0.3),
        'right_hand': -_R(arm_bend * 0.4),
    }, drop


def gen_sit(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 1.2)
    scale = p.get('scale', 1.0)
    return _sit_pose(min(t / dur, 1.0), scale)


def gen_stand_up(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 1.2)
    scale = p.get('scale', 1.0)
    pose, drop = _sit_pose(1.0 - min(t / dur, 1.0), scale)
    return pose, drop - 33.5 * scale   # rise back to standing height


def gen_kneel(t: float, params: Dict[str, Any] = None):
    """Stand → both knees on the floor, shins flat behind, feet pointed.

    Geometry: hips ≈ 36*scale above floor (thighs straight down, knees on
    the floor), shins horizontal behind, feet flat on the floor.
    """
    p = params or {}
    dur = p.get('duration', 1.0)
    scale = p.get('scale', 1.0)
    e = _ease(min(t / dur, 1.0))
    drop = 24.0 * scale * e            # hips down so knees reach the floor
    # Per-side: hip bones mirror (99°/81°) so deltas differ per side.
    # Targets (world): thigh 90° (vertical, knees on floor), shin 180°.
    thigh_l = -21 * e
    thigh_r = 19 * e
    shin_l = 102 * e
    shin_r = 81 * e
    ankle = 45 * e * (1 - e)           # foot flexes on the way down, flattens at rest
    foot = -25 * e                     # feet flatten back along the floor
    spine = -6 * e
    arm_fwd = 14 * e
    arm_bend = 16 * e
    return {
        **_REST,
        'hips': _R(0),
        'spine': _R(-90) + _R(spine),
        'neck': _R(-2 * e),
        'head': _R(-2 * e),
        'left_hip': _R(99 + 4 * e),
        'right_hip': _R(81 - 4 * e),
        'left_upper_leg': _R(8 + thigh_l),
        'left_lower_leg': _R(-12 + shin_l),
        'left_ankle': _R(ankle),
        'left_foot': _R(25 + foot),
        'right_upper_leg': _R(-6 + thigh_r),
        'right_lower_leg': _R(9 + shin_r),
        'right_ankle': -_R(ankle),
        'right_foot': _R(-25 - foot),
        'left_shoulder': _R(-132 + 3 * e),
        'left_upper_arm': _R(-38 - arm_fwd),
        'left_forearm': _R(25 + arm_bend),
        'left_wrist': _R(arm_bend * 0.3),
        'left_hand': _R(arm_bend * 0.4),
        'right_shoulder': _R(132 - 3 * e),
        'right_upper_arm': _R(38 + arm_fwd),
        'right_forearm': _R(-25 - arm_bend),
        'right_wrist': -_R(arm_bend * 0.3),
        'right_hand': -_R(arm_bend * 0.4),
    }, drop


def _lie_pose(progress: float, scale: float):
    """Shared lie-down pose: progress 0 = standing, 1 = lying flat.

    Stage 1 (0→0.35): fold into a sit (same leg geometry as _sit_pose).
    Stage 2 (0.35→1): rotate the whole body back (hips root +90°) while
    the hips descend to the floor; legs unfold along the body, arms swing
    overhead. Exact reversal for get_up.
    """
    c1 = min(progress / 0.35, 1.0)
    c2 = max((progress - 0.35) / 0.65, 0.0)
    f = _ease(c1)     # sit-fold progress
    r = _ease(c2)     # rotation progress
    scale = float(scale)

    drop = 33.5 * scale * f + 12.5 * scale * r      # → 46*scale (hips ON floor)
    rot = 90.0 * r                                   # hips root rotation

    # Legs blend: sit-fold values at the stage boundary → straight along
    # the body (world ~180°) at rest. Hip bones ramp to exactly 90/90 so
    # BOTH legs lie on the body axis; per-side rel offsets cancel the
    # rest-pose asymmetry so each leg ends flat.
    sit_thigh_l, sit_thigh_r = -141.6 * f, -89.6 * f
    sit_shin_l, sit_shin_r = 89.6 * f, 68.6 * f
    sit_ankle, sit_foot_l, sit_foot_r = 4 * f, -63 * f, -13 * f
    thigh_l = sit_thigh_l * (1 - r) - 8 * r          # left thigh rel → 0
    thigh_r = sit_thigh_r * (1 - r) + 6 * r          # right thigh rel → 0
    shin_l = sit_shin_l * (1 - r) + 12 * r           # left shin rel → 0
    shin_r = sit_shin_r * (1 - r) - 9 * r            # right shin rel → 0
    ankle = sit_ankle * (1 - r)                      # ankle rel → 0
    foot_l = sit_foot_l * (1 - r) - 25 * r           # feet flat (rel → 0)
    foot_r = sit_foot_r * (1 - r) - 25 * r

    # Arms blend: rest/sit → overhead along the body. Shoulders ALSO rotate
    # from their hang-down rest (±132°) to point ALONG the body (−5°), so
    # both arms attach at the same height when horizontal — otherwise the
    # right shoulder tip hangs 60px below the left.
    sit_arm_fwd, sit_arm_bend = 30 * f, 38 * f
    arm_fwd_l = sit_arm_fwd * (1 - r) - 33 * r       # rel → −3 (world ~−8°, level)
    arm_fwd_r = sit_arm_fwd * (1 - r) - 41 * r
    arm_bend_l = sit_arm_bend * (1 - r) - 25 * r     # arms straighten along body
    arm_bend_r = sit_arm_bend * (1 - r) - 25 * r
    sh_l = (-132 + 5 * f) * (1 - r) - 5 * r          # −127 → −5 (along body)
    sh_r = (132 - 5 * f) * (1 - r) - 5 * r

    # Torso ends nearly flat (spine world ~5° — slight head-up is natural).
    # Hip bones ramp continuously from the sit spread (109/71) to exactly
    # 90/90 so both legs lie flat along the body axis.
    spine = -10 * f * (1 - r) + 5 * r
    hip_spread = 10 * f * (1 - r)
    hip_fold = 9 * r

    return {
        **_REST,
        'hips': _R(rot),
        'spine': _R(-90) + _R(spine),
        'neck': _R(-3 * f * (1 - r)),
        'head': _R(-3 * f * (1 - r)),
        'left_hip': _R(99 + hip_spread - hip_fold),
        'right_hip': _R(81 - hip_spread + hip_fold),
        'left_upper_leg': _R(8 + thigh_l),
        'left_lower_leg': _R(-12 + shin_l),
        'left_ankle': _R(ankle),
        'left_foot': _R(25 + foot_l),
        'right_upper_leg': _R(-6 + thigh_r),
        'right_lower_leg': _R(9 + shin_r),
        'right_ankle': -_R(ankle),
        'right_foot': _R(-25 - foot_r),
        'left_shoulder': _R(sh_l),
        'left_upper_arm': _R(-38 - arm_fwd_l),
        'left_forearm': _R(25 + arm_bend_l),
        'left_wrist': _R(arm_bend_l * 0.3),
        'left_hand': _R(arm_bend_l * 0.4),
        'right_shoulder': _R(sh_r),
        'right_upper_arm': _R(38 + arm_fwd_r),
        'right_forearm': _R(-25 - arm_bend_r),
        'right_wrist': -_R(arm_bend_r * 0.3),
        'right_hand': -_R(arm_bend_r * 0.4),
    }, drop


def gen_lie_down(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 1.4)
    scale = p.get('scale', 1.0)
    return _lie_pose(min(t / dur, 1.0), scale)


def gen_get_up(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 1.4)
    scale = p.get('scale', 1.0)
    pose, drop = _lie_pose(1.0 - min(t / dur, 1.0), scale)
    return pose, drop - 46.0 * scale   # rise back to standing height


# ─── TURN / CROUCH / SNEAK ────────────────────────────────

def gen_turn(t: float, params: Dict[str, Any] = None):
    """Turn around — pivot in place while the facing direction flips.

    The actual 180° direction change is handled by the `facing` component
    (the timeline handler flips it, and the renderer mirrors the skeleton
    horizontally). This generator only plays a subtle pivot: hips rotate
    one way, chest counter-rotates the other, arms swing out for balance —
    reads as a quick pivot turn, not a robot swivel.
    """
    p = params or {}
    dur = p.get('duration', 0.4)
    e = _ease(min(t / dur, 1.0))
    pivot = math.sin(e * math.pi)          # 0 → 1 → 0 (out and back)
    arm_swing = pivot * 40
    knee = pivot * 10
    return {
        **_REST,
        'hips': _R(pivot * 20),            # hips rotate one way
        'chest': -_R(pivot * 15),          # chest counter-rotates
        'spine': _R(-90) + _R(pivot * 3),
        'neck': _R(pivot * 4),
        'head': _R(pivot * 4),
        'left_shoulder': _R(-132 - arm_swing * 0.2),
        'right_shoulder': _R(132 + arm_swing * 0.2),
        'left_upper_arm': _R(-38 - arm_swing),
        'left_forearm': _R(10 - arm_swing * 0.4),
        'left_wrist': _R(-arm_swing * 0.2),
        'left_hand': _R(-arm_swing * 0.3),
        'right_upper_arm': _R(38 + arm_swing),
        'right_forearm': _R(-10 + arm_swing * 0.4),
        'right_wrist': _R(arm_swing * 0.2),
        'right_hand': _R(arm_swing * 0.3),
        'left_upper_leg': _R(8 + knee),
        'left_lower_leg': _R(-12 - knee * 0.6),
        'right_upper_leg': _R(-6 + knee),
        'right_lower_leg': _R(9 - knee * 0.6),
        'left_ankle': _R(knee * 0.3),
        'right_ankle': -_R(knee * 0.3),
    }


def _crouch_pose(progress: float, scale: float):
    """Shared crouch pose: progress 0 = standing, 1 = full stealth crouch.

    Hips drop to ~74px above floor, thighs near-horizontal, shins steep,
    feet flat, spine leans FORWARD ~30° (unlike sit which relaxes back),
    arms hang low-forward (stealth ready).
    """
    e = _ease(progress)
    drop = 27.5 * scale * e
    # Targets (world): thigh −10° (knees just below hips), shin 60°, foot 15°
    thigh_l = -127 * e
    thigh_r = -75 * e
    shin_l = 82 * e
    shin_r = 61 * e
    ankle = 4 * e
    foot_l = -74 * e
    foot_r = -24 * e
    spine = 30 * e                        # forward lean (less negative = forward)
    neck = 15 * e
    head = 15 * e
    arm_fwd = 45 * e                      # arms hang low-forward
    arm_bend = 20 * e
    return {
        **_REST,
        'hips': _R(0),
        'spine': _R(-90) + _R(spine),
        'neck': _R(neck),
        'head': _R(head),
        'left_hip': _R(99 + 6 * e),
        'right_hip': _R(81 - 6 * e),
        'left_upper_leg': _R(8 + thigh_l),
        'left_lower_leg': _R(-12 + shin_l),
        'left_ankle': _R(ankle),
        'left_foot': _R(25 + foot_l),
        'right_upper_leg': _R(-6 + thigh_r),
        'right_lower_leg': _R(9 + shin_r),
        'right_ankle': -_R(ankle),
        'right_foot': _R(-25 - foot_r),
        'left_shoulder': _R(-132 + 8 * e),
        'left_upper_arm': _R(-38 - arm_fwd * 0.8),
        'left_forearm': _R(25 + arm_bend),
        'left_wrist': _R(arm_bend * 0.3),
        'left_hand': _R(arm_bend * 0.4),
        'right_shoulder': _R(132 - 8 * e),
        'right_upper_arm': _R(38 + arm_fwd * 0.8),
        'right_forearm': _R(-25 - arm_bend),
        'right_wrist': -_R(arm_bend * 0.3),
        'right_hand': -_R(arm_bend * 0.4),
    }, drop


def gen_crouch(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 0.8)
    scale = p.get('scale', 1.0)
    return _crouch_pose(min(t / dur, 1.0), scale)


def gen_sneak(t: float, params: Dict[str, Any] = None):
    """Sneak — crouched slow walk (loop). Flat-footed, low, no bounce.

    Legs use the same FABRIK IK gait as walk (feet plant, no slide) with a
    short stride and tiny step height; the torso holds the crouch. Returns
    (pose, y_offset) — crouch drop ramps in over the first 0.7s, then holds.
    """
    p = dict(params or {})
    dur = p.get('duration', 1.5)
    scale = p.get('scale', 1.0)
    # Short, flat gait params for the shared walk solver
    gait = dict(p)
    gait.setdefault('speed', 0.7)
    gait.setdefault('stride', 26)
    gait.setdefault('step_height', 4)
    gait.setdefault('bounce', 1.5)
    pose = gen_walk(t, gait)
    e = _ease(min(t / 0.7, 1.0))          # crouch ramp-in
    # Override the upright walk torso with the sneak crouch
    pose['spine'] = _R(-90) + _R(24 * e)
    pose['neck'] = _R(12 * e)
    pose['head'] = _R(12 * e)
    pose['left_shoulder'] = _R(-132 + 8 * e)
    pose['right_shoulder'] = _R(132 - 8 * e)
    pose['left_upper_arm'] = _R(-38 - 40 * e)
    pose['right_upper_arm'] = _R(38 + 40 * e)
    pose['left_forearm'] = _R(30 + 20 * e)
    pose['right_forearm'] = _R(-30 - 20 * e)
    return pose, 27.5 * scale * e


# ─── GESTURES: POINT / CLAP / NOD / SHAKE HEAD ─────────────

def gen_point(t: float, params: Dict[str, Any] = None):
    """Point — right arm raises to horizontal-forward and holds."""
    p = params or {}
    dur = p.get('duration', 1.0)
    e = _ease(min(t / dur, 1.0))
    raise_ph = _ease(min(t / 0.4, 1.0))   # arm up in the first 0.4s, then hold
    return {
        **_REST,
        'spine': _R(-88) - _R(2 * raise_ph),
        'neck': _R(4 * raise_ph),
        'head': _R(4 * raise_ph),
        'left_shoulder': _R(-132 + 10 * raise_ph),
        'left_upper_arm': _R(-38 - 55 * raise_ph),   # left arm folds across
        'left_forearm': _R(25 + 60 * raise_ph),
        'left_wrist': _R(18 * raise_ph),
        'left_hand': _R(25 * raise_ph),
        'right_shoulder': _R(132 - 15 * raise_ph),
        'right_upper_arm': _R(38 - 80 * raise_ph),   # right arm points out
        'right_forearm': _R(-25 + 20 * raise_ph),    # straight index
        'right_wrist': _R(-5 * raise_ph),
        'right_hand': _R(-10 * raise_ph),
        'left_hip': _R(99 + 3 * raise_ph),
        'right_hip': _R(81 - 3 * raise_ph),
        'left_ankle': _R(3 * raise_ph),
        'right_ankle': -_R(3 * raise_ph),
    }


def gen_clap(t: float, params: Dict[str, Any] = None):
    """Clap — hands meet in front of the chest three times (t≈0.2/0.5/0.8)."""
    p = params or {}
    dur = p.get('duration', 1.2)
    if t < 0.95:
        gap = 0.15 + 0.85 * abs(math.sin(math.pi * (t - 0.2) / 0.3))
    else:
        gap = 0.15                       # hold the last clap
    # gap: 0.15 = hands together (clap), 1.0 = arms spread
    spread = 30 * (gap - 0.15) / 0.85    # 0..30° swing out from the clap line
    return {
        **_REST,
        'spine': _R(-88),
        'neck': _R(3),
        'head': _R(3),
        'left_shoulder': _R(-132 + 12),
        'left_upper_arm': _R(-38 - 47 - spread),      # elbows out, hands to center
        'left_forearm': _R(25 + 70 - spread * 0.7),   # forearms fold up
        'left_wrist': _R(30 - spread * 0.6),
        'left_hand': _R(35 - spread * 0.6),
        'right_shoulder': _R(132 - 12),
        'right_upper_arm': _R(38 + 47 + spread),
        'right_forearm': _R(-25 - 70 + spread * 0.7),
        'right_wrist': -_R(30 - spread * 0.6),
        'right_hand': -_R(35 - spread * 0.6),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }


def gen_nod(t: float, params: Dict[str, Any] = None):
    """Nod yes — head dips down and up three times, slight torso sway."""
    p = params or {}
    dur = p.get('duration', 1.0)
    prog = min(t / dur, 1.0)
    # 3 nods at t≈0.15, 0.45, 0.75 — head drops ~20° each time
    cycle = 0.3
    if t < 0.9:
        nod_t = (t % cycle) / cycle
        down = 1.0 - math.cos(nod_t * 2 * math.pi)   # 0 → 1 → 0 per nod
    else:
        down = 0.0
    return {
        **_REST,
        'spine': _R(-88) - _R(4 * down),
        'neck': _R(16 * down),
        'head': _R(16 * down),
        'left_shoulder': _R(-132 + 3 * down),
        'right_shoulder': _R(132 - 3 * down),
        'left_upper_arm': _R(-38 + math.sin(t * 3) * 1.5),
        'right_upper_arm': _R(38 + math.sin(t * 3) * 1.5),
        'left_forearm': _R(25 + math.sin(t * 3) * 1.5),
        'right_forearm': _R(-25 - math.sin(t * 3) * 1.5),
        'left_wrist': _R(math.sin(t * 3) * 1.0),
        'right_wrist': -_R(math.sin(t * 3) * 1.0),
        'left_hip': _R(99 + 2 * down),
        'right_hip': _R(81 - 2 * down),
        'left_ankle': _R(2 * down),
        'right_ankle': -_R(2 * down),
    }


def gen_shake_head(t: float, params: Dict[str, Any] = None):
    """Shake head no — head tilts left-right three times (2D 'no')."""
    p = params or {}
    dur = p.get('duration', 1.0)
    prog = min(t / dur, 1.0)
    if t < 0.9:
        shake = math.sin(t * (2 * math.pi / 0.3)) * 18   # ±18° tilt
    else:
        shake = 0.0
    return {
        **_REST,
        'spine': _R(-88) - _R(2 * abs(shake) / 18),
        'neck': _R(shake * 0.4),
        'head': _R(shake),
        'left_shoulder': _R(-132 + 2 * abs(shake) / 18),
        'right_shoulder': _R(132 - 2 * abs(shake) / 18),
        'left_upper_arm': _R(-38 + math.sin(t * 3) * 1.5),
        'right_upper_arm': _R(38 + math.sin(t * 3) * 1.5),
        'left_forearm': _R(25 + math.sin(t * 3) * 1.5),
        'right_forearm': _R(-25 - math.sin(t * 3) * 1.5),
        'left_wrist': _R(math.sin(t * 3) * 1.0),
        'right_wrist': -_R(math.sin(t * 3) * 1.0),
        'left_hip': _R(99 + 2 * abs(shake) / 18),
        'right_hip': _R(81 - 2 * abs(shake) / 18),
        'left_ankle': _R(2 * abs(shake) / 18),
        'right_ankle': -_R(2 * abs(shake) / 18),
    }


# ─── HANDS: PICK UP / PUT DOWN / THROW / CATCH ─────────────

def _pick_pose(progress: float, scale: float):
    """Shared pick-up pose: progress 0 = standing empty-handed,
    1 = standing HOLDING (arm bent at chest). Stages:
      0.00–0.50  bend down, right arm reaches the floor (grab)
      0.50–1.00  rise, arm comes up bent (now holding)
    put_down is the exact reverse (progress 1 = holding, 0 = standing free).
    """
    e = _ease(progress)
    # Stage 1: reach down (0→1 of the reach), Stage 2: rise (1→0 of reach)
    if progress < 0.5:
        reach = _ease(progress / 0.5)
        rise = 0.0
    else:
        reach = 1.0
        rise = _ease((progress - 0.5) / 0.5)
    drop = 20.0 * scale * (reach * (1 - rise))   # deepest at the grab, back up
    spine = 35 * reach * (1 - rise)              # bend forward to reach
    # Right arm: extended down at the grab → bent at the chest when holding
    arm_reach = reach * (1 - rise)               # 1 at grab, 0 when holding
    arm_hold = rise                              # 1 when holding
    thigh = -50 * reach * (1 - rise)             # knees bend on the way down
    shin = 40 * reach * (1 - rise)
    ankle = 3 * reach * (1 - rise)
    foot = -30 * reach * (1 - rise)
    return {
        **_REST,
        'hips': _R(0),
        'spine': _R(-90) + _R(spine),
        'neck': _R(spine * 0.4),
        'head': _R(spine * 0.4),
        'left_hip': _R(99 + 5 * reach * (1 - rise)),
        'right_hip': _R(81 - 5 * reach * (1 - rise)),
        'left_upper_leg': _R(8 + thigh),
        'left_lower_leg': _R(-12 + shin),
        'left_ankle': _R(ankle),
        'left_foot': _R(25 + foot),
        'right_upper_leg': _R(-6 + thigh),
        'right_lower_leg': _R(9 + shin),
        'right_ankle': -_R(ankle),
        'right_foot': _R(-25 - foot),
        'left_shoulder': _R(-132 + 15 * reach * (1 - rise)),
        'left_upper_arm': _R(-38 - 90 * reach * (1 - rise) - 15 * arm_hold),  # left arm swings back on the reach, slight guard when holding
        'left_forearm': _R(25 + 30 * reach * (1 - rise) + 25 * arm_hold),
        'left_wrist': _R(15 * reach * (1 - rise)),
        'left_hand': _R(20 * reach * (1 - rise)),
        'right_shoulder': _R(132 - 10 * arm_hold),
        'right_upper_arm': _R(38 + 95 * arm_reach - 60 * arm_hold),  # down at grab, bent at chest when holding
        'right_forearm': _R(-25 + 55 * arm_reach + 40 * arm_hold),
        'right_wrist': -_R(20 * arm_reach + 10 * arm_hold),
        'right_hand': -_R(25 * arm_reach + 15 * arm_hold),
    }, drop


def gen_pick_up(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 1.4)
    scale = p.get('scale', 1.0)
    return _pick_pose(min(t / dur, 1.0), scale)


def gen_put_down(t: float, params: Dict[str, Any] = None):
    """Reverse of pick_up: starts holding, ends standing empty-handed."""
    p = params or {}
    dur = p.get('duration', 1.4)
    scale = p.get('scale', 1.0)
    pose, drop = _pick_pose(1.0 - min(t / dur, 1.0), scale)
    return pose, drop - 20.0 * scale


def gen_throw(t: float, params: Dict[str, Any] = None):
    """Throw — wind up (arm back, body coils), whip forward, follow through."""
    p = params or {}
    dur = p.get('duration', 1.0)
    prog = min(t / dur, 1.0)
    if prog < 0.35:                       # windup
        ph = _ease(prog / 0.35)
        arm_back = 110 * ph               # right arm swings back-up
        twist = -22 * ph                  # chest coils back
        lean = -6 * ph
    elif prog < 0.7:                      # release
        ph = _ease((prog - 0.35) / 0.35)
        arm_back = 110 * (1 - ph) - 130 * ph   # whips forward-overhead
        twist = -22 * (1 - ph) + 26 * ph
        lean = -6 * (1 - ph) + 10 * ph
    else:                                 # follow through
        ph = _ease((prog - 0.7) / 0.3)
        arm_back = -20 + 30 * ph          # arm follows down-forward
        twist = 26 * (1 - ph)
        lean = 10 * (1 - ph) + 14 * ph
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'chest': _R(twist),
        'hips': -_R(twist * 0.5),
        'neck': _R(lean * 0.5),
        'head': _R(lean * 0.5),
        'left_shoulder': _R(-132 + 8),
        'left_upper_arm': _R(-38 - 20 - twist * 0.8),    # non-throwing arm tucks
        'left_forearm': _R(25 + 40),
        'left_wrist': _R(15),
        'left_hand': _R(20),
        'right_shoulder': _R(132 - 10),
        'right_upper_arm': _R(38 - arm_back),
        'right_forearm': _R(-25 - arm_back * 0.55),
        'right_wrist': -_R(arm_back * 0.25),
        'right_hand': -_R(arm_back * 0.3),
        'left_hip': _R(99 + twist * 0.4),
        'right_hip': _R(81 - twist * 0.4),
        'left_ankle': _R(4),
        'right_ankle': -_R(4),
    }


def gen_catch(t: float, params: Dict[str, Any] = None):
    """Catch — arms raise ready, hands open, then absorb the impact."""
    p = params or {}
    dur = p.get('duration', 1.0)
    prog = min(t / dur, 1.0)
    if prog < 0.3:                        # arms up, ready
        ph = _ease(prog / 0.3)
        arm_up = 85 * ph
        ready = ph
    elif prog < 0.6:                      # catch + absorb
        ph = _ease((prog - 0.3) / 0.3)
        arm_up = 85 * (1 - ph * 0.4)      # arms pull back slightly
        ready = 1.0 - 0.3 * ph
    else:                                 # hold
        arm_up = 51.0
        ready = 0.7
    return {
        **_REST,
        'spine': _R(-88) - _R(4 * (1 - ready) + 2),
        'neck': _R(6 * (1 - ready)),
        'head': _R(6 * (1 - ready)),
        'left_shoulder': _R(-132 + 12),
        'left_upper_arm': _R(-38 - arm_up),
        'left_forearm': _R(25 + 60 + 20 * (1 - ready)),
        'left_wrist': _R(35 * ready),
        'left_hand': _R(40 * ready),      # hand open
        'right_shoulder': _R(132 - 12),
        'right_upper_arm': _R(38 + arm_up),
        'right_forearm': _R(-25 - 60 - 20 * (1 - ready)),
        'right_wrist': -_R(35 * ready),
        'right_hand': -_R(40 * ready),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }


# ─── STRENGTH / COMBAT: PUSH / PULL / BLOCK / DODGE ────────

def gen_push(t: float, params: Dict[str, Any] = None):
    """Push — load arms at the chest, extend both forward, hold."""
    p = params or {}
    dur = p.get('duration', 1.0)
    prog = min(t / dur, 1.0)
    if prog < 0.3:
        ph = _ease(prog / 0.3)
        ext = 0.0
        lean = -6 * ph                    # load back
    elif prog < 0.7:
        ph = _ease((prog - 0.3) / 0.4)
        ext = ph
        lean = -6 * (1 - ph) + 12 * ph    # drive forward
    else:
        ext = 1.0
        lean = 12.0
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'neck': _R(lean * 0.5),
        'head': _R(lean * 0.5),
        'left_shoulder': _R(-132 + 14 * ext),
        'left_upper_arm': _R(-38 - 60 * ext),      # arms drive forward
        'left_forearm': _R(25 + 75 * ext),
        'left_wrist': _R(30 * ext),
        'left_hand': _R(35 * ext),
        'right_shoulder': _R(132 - 14 * ext),
        'right_upper_arm': _R(38 + 60 * ext),
        'right_forearm': _R(-25 - 75 * ext),
        'right_wrist': -_R(30 * ext),
        'right_hand': -_R(35 * ext),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_ankle': _R(3 * ext),
        'right_ankle': -_R(3 * ext),
    }


def gen_pull(t: float, params: Dict[str, Any] = None):
    """Pull — arms extended, haul back to the chest, lean back, hold."""
    p = params or {}
    dur = p.get('duration', 1.0)
    prog = min(t / dur, 1.0)
    if prog < 0.3:
        ph = _ease(prog / 0.3)
        retract = 0.0
        lean = 10 * ph                    # brace into the pull
    elif prog < 0.7:
        ph = _ease((prog - 0.3) / 0.4)
        retract = ph
        lean = 10 * (1 - ph) - 8 * ph     # haul back
    else:
        retract = 1.0
        lean = -8.0
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'neck': _R(lean * 0.5),
        'head': _R(lean * 0.5),
        'left_shoulder': _R(-132 + 14 * (1 - retract)),
        'left_upper_arm': _R(-38 - 60 * (1 - retract) + 15 * retract),  # arms pull IN
        'left_forearm': _R(25 + 75 * (1 - retract) - 55 * retract),
        'left_wrist': _R(30 * (1 - retract)),
        'left_hand': _R(35 * (1 - retract)),
        'right_shoulder': _R(132 - 14 * (1 - retract)),
        'right_upper_arm': _R(38 + 60 * (1 - retract) - 15 * retract),
        'right_forearm': _R(-25 - 75 * (1 - retract) + 55 * retract),
        'right_wrist': -_R(30 * (1 - retract)),
        'right_hand': -_R(35 * (1 - retract)),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }


def gen_block(t: float, params: Dict[str, Any] = None):
    """Block — both forearms up in a guard, fists at face level, hold."""
    p = params or {}
    dur = p.get('duration', 0.6)
    e = _ease(min(t / dur, 1.0))
    return {
        **_REST,
        'spine': _R(-92) - _R(3 * e),
        'neck': _R(4 * e),
        'head': _R(4 * e),
        'left_shoulder': _R(-132 + 18 * e),
        'left_upper_arm': _R(-38 - 70 * e),        # elbows out, guard up
        'left_forearm': _R(25 + 95 * e),           # forearm vertical
        'left_wrist': _R(25 * e),
        'left_hand': _R(30 * e),
        'right_shoulder': _R(132 - 18 * e),
        'right_upper_arm': _R(38 + 70 * e),
        'right_forearm': _R(-25 - 95 * e),
        'right_wrist': -_R(25 * e),
        'right_hand': -_R(30 * e),
        'left_upper_leg': _R(8 + 16 * e),          # slight stance drop
        'left_lower_leg': _R(-12 - 18 * e),
        'right_upper_leg': _R(-6 + 16 * e),
        'right_lower_leg': _R(9 - 18 * e),
        'left_ankle': _R(6 * e),
        'right_ankle': -_R(6 * e),
    }


def gen_dodge(t: float, params: Dict[str, Any] = None):
    """Dodge — quick drop, lean right, arms up, recover."""
    p = params or {}
    dur = p.get('duration', 0.7)
    prog = min(t / dur, 1.0)
    if prog < 0.35:
        ph = _ease(prog / 0.35)
        duck = ph
    elif prog < 0.7:
        ph = _ease((prog - 0.35) / 0.35)
        duck = 1.0 - ph
    else:
        duck = 0.0
    tilt = 14 * duck                       # body tilts to the right
    arm_up = 70 * duck
    return {
        **_REST,
        'hips': _R(tilt),
        'spine': _R(-90) + _R(-8 * duck),
        'neck': _R(-5 * duck),
        'head': _R(-5 * duck),
        'left_shoulder': _R(-132 + 10 * duck),
        'left_upper_arm': _R(-38 - arm_up),
        'left_forearm': _R(25 + 40 * duck),
        'left_wrist': _R(15 * duck),
        'left_hand': _R(20 * duck),
        'right_shoulder': _R(132 - 10 * duck),
        'right_upper_arm': _R(38 + arm_up * 0.7),
        'right_forearm': _R(-25 - 30 * duck),
        'right_wrist': -_R(15 * duck),
        'right_hand': -_R(20 * duck),
        'left_upper_leg': _R(8 + 20 * duck),       # crouch with the duck
        'left_lower_leg': _R(-12 - 22 * duck),
        'right_upper_leg': _R(-6 + 20 * duck),
        'right_lower_leg': _R(9 - 22 * duck),
        'left_ankle': _R(6 * duck),
        'right_ankle': -_R(6 * duck),
    }


# ─── EMOTIONS (loops): HAPPY / SAD / ANGRY / SCARED ────────
# Loops with duration 2.0; all sines use ω = π·k so the phase wraps
# cleanly at t = 2s (no pop). Body-language posture + micro-motion.

def gen_happy(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 2.0)
    s = (t % dur) * 1.0
    bob = math.sin(math.pi * s)            # gentle 2s bounce
    return {
        **_REST,
        'spine': _R(-84) + _R(bob * 1.5),          # chest up
        'chest': _R(bob * 1.5),
        'neck': _R(-6 + bob * 1.0),
        'head': _R(-6 + bob * 1.0),
        'left_shoulder': _R(-132 - 6 - bob * 2),
        'right_shoulder': _R(132 + 6 + bob * 2),
        'left_upper_arm': _R(-38 - 50 - bob * 3),  # arms out
        'left_forearm': _R(25 + 30 + bob * 2),
        'left_wrist': _R(10 + bob * 2),
        'left_hand': _R(15 + bob * 3),
        'right_upper_arm': _R(38 + 50 + bob * 3),
        'right_forearm': _R(-25 - 30 - bob * 2),
        'right_wrist': -_R(10 + bob * 2),
        'right_hand': -_R(15 + bob * 3),
        'left_hip': _R(99 + 4),
        'right_hip': _R(81 - 4),
        'left_ankle': _R(3 + bob * 1.5),
        'right_ankle': -_R(3 + bob * 1.5),
    }


def gen_sad(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 2.0)
    s = (t % dur) * 1.0
    sigh = math.sin(math.pi * s * 0.5)     # slow 4s... use πs → 2s cycle
    sigh = math.sin(math.pi * s)
    return {
        **_REST,
        'spine': _R(-96) + _R(sigh * 1.0),         # slumped
        'chest': _R(sigh * 1.0),
        'neck': _R(14 + sigh * 2),
        'head': _R(14 + sigh * 2),                 # head down
        'left_shoulder': _R(-132 + 14 + sigh * 2), # shrugged up
        'right_shoulder': _R(132 - 14 - sigh * 2),
        'left_upper_arm': _R(-38 + 12 + sigh * 1.5),   # arms hang limp
        'left_forearm': _R(25 + 10 + sigh * 1.5),
        'left_wrist': _R(5 + sigh * 1.0),
        'left_hand': _R(8 + sigh * 1.0),
        'right_upper_arm': _R(38 - 12 - sigh * 1.5),
        'right_forearm': _R(-25 - 10 - sigh * 1.5),
        'right_wrist': -_R(5 + sigh * 1.0),
        'right_hand': -_R(8 + sigh * 1.0),
        'left_hip': _R(99 + 5),
        'right_hip': _R(81 - 5),
        'left_ankle': _R(2 + sigh),
        'right_ankle': -_R(2 + sigh),
    }


def gen_angry(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 2.0)
    s = (t % dur) * 1.0
    tremble = math.sin(math.pi * s * 4)    # fast 0.5s tremble, wraps at 2s
    return {
        **_REST,
        'spine': _R(-78) + _R(tremble * 0.8),      # leaning in, tense
        'chest': _R(5),
        'neck': _R(-8 + tremble * 1.0),
        'head': _R(-8 + tremble * 1.0),            # head forward
        'left_shoulder': _R(-132 - 4 + tremble * 1.5),
        'right_shoulder': _R(132 + 4 - tremble * 1.5),
        'left_upper_arm': _R(-38 - 30 + tremble * 2),
        'left_forearm': _R(25 + 50 + tremble * 2),
        'left_wrist': _R(20 + tremble * 1.5),
        'left_hand': _R(-15 + tremble * 1.5),      # fist curled
        'right_upper_arm': _R(38 + 30 - tremble * 2),
        'right_forearm': _R(-25 - 50 - tremble * 2),
        'right_wrist': -_R(20 + tremble * 1.5),
        'right_hand': -_R(-15 + tremble * 1.5),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_upper_leg': _R(8 + 10),
        'left_lower_leg': _R(-12 - 12),
        'right_upper_leg': _R(-6 + 10),
        'right_lower_leg': _R(9 - 12),
        'left_ankle': _R(4 + tremble),
        'right_ankle': -_R(4 + tremble),
    }


def gen_scared(t: float, params: Dict[str, Any] = None):
    p = params or {}
    dur = p.get('duration', 2.0)
    s = (t % dur) * 1.0
    tremble = math.sin(math.pi * s * 4)
    return {
        **_REST,
        'spine': _R(-95) + _R(tremble * 1.0),      # recoiling
        'neck': _R(-12 + tremble * 1.0),
        'head': _R(-12 + tremble * 1.0),           # head back
        'left_shoulder': _R(-132 + 20 + tremble * 1.5),
        'right_shoulder': _R(132 - 20 - tremble * 1.5),
        'left_upper_arm': _R(-38 - 75 + tremble * 2),   # arms up in front
        'left_forearm': _R(25 + 85 + tremble * 2),
        'left_wrist': _R(35 + tremble * 1.5),
        'left_hand': _R(40 + tremble * 1.5),       # hands open
        'right_upper_arm': _R(38 + 75 - tremble * 2),
        'right_forearm': _R(-25 - 85 - tremble * 2),
        'right_wrist': -_R(35 + tremble * 1.5),
        'right_hand': -_R(40 + tremble * 1.5),
        'left_upper_leg': _R(8 + 18),
        'left_lower_leg': _R(-12 - 20),
        'right_upper_leg': _R(-6 + 18),
        'right_lower_leg': _R(9 - 20),
        'left_ankle': _R(5 + tremble),
        'right_ankle': -_R(5 + tremble),
    }


# ─── COMBAT (EXPANDED) ─────────────────────────────────────

def gen_kick(t: float, params: Dict[str, Any] = None):
    """Kick — right leg drives up and forward (roundhouse/front kick hybrid)."""
    p = params or {}
    dur = p.get('duration', 0.6)
    prog = min(t / dur, 1.0)
    if prog < 0.15:  # chamber (pull knee up)
        ph = _ease(prog / 0.15)
        leg_up = 85 * ph
        lean = -8 * ph
        twist = -6 * ph
    elif prog < 0.4:  # strike (extend leg forward-up)
        ph = _ease((prog - 0.15) / 0.25)
        leg_up = 85 + 45 * ph
        lean = -8 + 6 * ph
        twist = -6 + 12 * ph
    else:  # retract
        ph = _ease((prog - 0.4) / 0.6)
        leg_up = 130 * (1 - ph)
        lean = -2 * (1 - ph)
        twist = 6 * (1 - ph)
    return {
        **_REST,
        'hips': _R(twist * 0.5),
        'spine': _R(-90) + _R(lean),
        'chest': _R(twist),
        'neck': _R(lean * 0.4),
        'head': _R(lean * 0.4),
        # Arms for balance
        'left_shoulder': _R(-132 + 8),
        'left_upper_arm': _R(-38 - 40),
        'left_forearm': _R(25 + 35),
        'left_wrist': _R(12),
        'left_hand': _R(15),
        'right_shoulder': _R(132 - 8),
        'right_upper_arm': _R(38 + 30),
        'right_forearm': _R(-25 - 30),
        'right_wrist': -_R(12),
        'right_hand': -_R(15),
        # Kicking leg
        'right_hip': _R(81 + 8),
        'right_upper_leg': _R(-6 + leg_up),
        'right_lower_leg': _R(9 - leg_up * 0.65),
        'right_ankle': -_R(leg_up * 0.25),
        'right_foot': _R(-20),
        # Support leg
        'left_hip': _R(99 + 6),
        'left_upper_leg': _R(8 + 12),
        'left_lower_leg': _R(-12 - 14),
        'left_ankle': _R(5),
        'left_foot': _R(20),
    }


def gen_uppercut(t: float, params: Dict[str, Any] = None):
    """Uppercut — crouch low, then explode upward with rising fist."""
    p = params or {}
    dur = p.get('duration', 0.5)
    prog = min(t / dur, 1.0)
    if prog < 0.2:  # crouch/load
        ph = _ease(prog / 0.2)
        arm_down = -50 * ph
        crouch = 35 * ph
        lean = -8 * ph
    elif prog < 0.45:  # strike (arm rises, body extends)
        ph = _ease((prog - 0.2) / 0.25)
        arm_down = -50 + 170 * ph
        crouch = 35 * (1 - ph)
        lean = -8 + 18 * ph
    else:  # recover
        ph = _ease((prog - 0.45) / 0.55)
        arm_down = 120 * (1 - ph)
        crouch = 0
        lean = 10 * (1 - ph)
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'neck': _R(lean * 0.5),
        'head': _R(lean * 0.5),
        'chest': _R(lean * 0.3),
        # Striking arm (right)
        'right_shoulder': _R(132 - 15),
        'right_upper_arm': _R(38 + arm_down),
        'right_forearm': _R(-25 - arm_down * 0.5),
        'right_wrist': -_R(arm_down * 0.2),
        'right_hand': -_R(arm_down * 0.25),
        # Guard arm
        'left_shoulder': _R(-132 + 10),
        'left_upper_arm': _R(-38 - 50),
        'left_forearm': _R(25 + 60),
        'left_wrist': _R(20),
        'left_hand': _R(25),
        # Legs (crouch then extend)
        'left_hip': _R(99 + 5),
        'left_upper_leg': _R(8 + crouch * 1.8),
        'left_lower_leg': _R(-12 - crouch * 1.2),
        'left_ankle': _R(crouch * 0.3),
        'left_foot': _R(20),
        'right_hip': _R(81 - 5),
        'right_upper_leg': _R(-6 + crouch * 1.8),
        'right_lower_leg': _R(9 - crouch * 1.2),
        'right_ankle': -_R(crouch * 0.3),
        'right_foot': _R(-20),
    }


def gen_sweep(t: float, params: Dict[str, Any] = None):
    """Leg sweep — crouch low, spin leg out to sweep opponent's feet."""
    p = params or {}
    dur = p.get('duration', 0.8)
    prog = min(t / dur, 1.0)
    if prog < 0.3:  # drop + chamber
        ph = _ease(prog / 0.3)
        drop = 28 * ph
        spin = 0
        leg_out = 0
    elif prog < 0.6:  # sweep (leg extends, body spins)
        ph = _ease((prog - 0.3) / 0.3)
        drop = 28
        spin = 90 * ph
        leg_out = 110 * ph
    else:  # recover
        ph = _ease((prog - 0.6) / 0.4)
        drop = 28 * (1 - ph)
        spin = 90 * (1 - ph)
        leg_out = 110 * (1 - ph)
    return {
        **_REST,
        'hips': _R(spin),
        'spine': _R(-90) + _R(12 * min(prog / 0.3, 1.0)),
        'neck': _R(6),
        'head': _R(6),
        # Arms for balance
        'left_shoulder': _R(-132 - 10),
        'left_upper_arm': _R(-38 - 50 - spin * 0.4),
        'left_forearm': _R(25 + 35),
        'left_wrist': _R(12),
        'left_hand': _R(15),
        'right_shoulder': _R(132 + 10),
        'right_upper_arm': _R(38 + 50 + spin * 0.4),
        'right_forearm': _R(-25 - 35),
        'right_wrist': -_R(12),
        'right_hand': -_R(15),
        # Sweeping leg (right extends out)
        'right_hip': _R(81 + 8),
        'right_upper_leg': _R(-6 + leg_out),
        'right_lower_leg': _R(9 - leg_out * 0.4),
        'right_ankle': -_R(leg_out * 0.2),
        'right_foot': _R(-20),
        # Support leg (left crouches)
        'left_hip': _R(99 + 6),
        'left_upper_leg': _R(8 + drop * 2.2),
        'left_lower_leg': _R(-12 - drop * 1.8),
        'left_ankle': _R(drop * 0.4),
        'left_foot': _R(20),
    }, drop  # height-driven


def gen_slam(t: float, params: Dict[str, Any] = None):
    """Overhead slam — raise arms high, then drive down hard."""
    p = params or {}
    dur = p.get('duration', 0.8)
    prog = min(t / dur, 1.0)
    if prog < 0.25:  # raise arms overhead
        ph = _ease(prog / 0.25)
        arm_up = 110 * ph
        lean = -6 * ph
    elif prog < 0.5:  # slam down
        ph = _ease((prog - 0.25) / 0.25)
        arm_up = 110 * (1 - ph) - 90 * ph
        lean = -6 + 16 * ph
    else:  # follow through
        ph = _ease((prog - 0.5) / 0.5)
        arm_up = -90 + 90 * ph
        lean = 10 * (1 - ph)
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'chest': _R(lean * 0.4),
        'neck': _R(lean * 0.5),
        'head': _R(lean * 0.5),
        # Both arms slam down
        'left_shoulder': _R(-132 + arm_up * 0.15),
        'left_upper_arm': _R(-38 - arm_up),
        'left_forearm': _R(25 + arm_up * 0.4),
        'left_wrist': _R(arm_up * 0.2),
        'left_hand': _R(arm_up * 0.25),
        'right_shoulder': _R(132 - arm_up * 0.15),
        'right_upper_arm': _R(38 + arm_up),
        'right_forearm': _R(-25 - arm_up * 0.4),
        'right_wrist': -_R(arm_up * 0.2),
        'right_hand': -_R(arm_up * 0.25),
        # Legs brace
        'left_hip': _R(99 + 4),
        'left_upper_leg': _R(8 + 14),
        'left_lower_leg': _R(-12 - 16),
        'left_ankle': _R(6),
        'left_foot': _R(20),
        'right_hip': _R(81 - 4),
        'right_upper_leg': _R(-6 + 14),
        'right_lower_leg': _R(9 - 16),
        'right_ankle': -_R(6),
        'right_foot': _R(-20),
    }


def gen_roll(t: float, params: Dict[str, Any] = None):
    """Forward roll — tuck and roll forward 360°."""
    p = params or {}
    dur = p.get('duration', 0.8)
    scale = p.get('scale', 1.0)
    prog = min(t / dur, 1.0)
    # Body rotates 360° around hips axis
    rot = 360 * _ease(prog)
    # Arms tuck in
    tuck = min(prog / 0.2, 1.0) * 80
    # Legs fold
    fold = min(prog / 0.2, 1.0) * 60
    return {
        **_REST,
        'hips': _R(rot),
        'spine': _R(-90),
        'chest': _R(0),
        'neck': _R(-tuck * 0.2),
        'head': _R(-tuck * 0.2),
        # Arms tuck to chest
        'left_shoulder': _R(-132 + tuck * 0.3),
        'left_upper_arm': _R(-38 - tuck),
        'left_forearm': _R(25 + tuck * 0.8),
        'left_wrist': _R(tuck * 0.3),
        'left_hand': _R(tuck * 0.4),
        'right_shoulder': _R(132 - tuck * 0.3),
        'right_upper_arm': _R(38 + tuck),
        'right_forearm': _R(-25 - tuck * 0.8),
        'right_wrist': -_R(tuck * 0.3),
        'right_hand': -_R(tuck * 0.4),
        # Legs fold
        'left_hip': _R(99 + fold * 0.2),
        'left_upper_leg': _R(8 + fold * 1.5),
        'left_lower_leg': _R(-12 - fold * 1.2),
        'left_ankle': _R(fold * 0.3),
        'left_foot': _R(20),
        'right_hip': _R(81 - fold * 0.2),
        'right_upper_leg': _R(-6 + fold * 1.5),
        'right_lower_leg': _R(9 - fold * 1.2),
        'right_ankle': -_R(fold * 0.3),
        'right_foot': _R(-20),
    }


def gen_slide(t: float, params: Dict[str, Any] = None):
    """Slide — drop into a low slide (baseball slide style)."""
    p = params or {}
    dur = p.get('duration', 0.8)
    scale = p.get('scale', 1.0)
    prog = min(t / dur, 1.0)
    if prog < 0.3:  # drop into slide
        ph = _ease(prog / 0.3)
        lean = 45 * ph
        leg_ext = 80 * ph
        drop = 22 * ph
    else:  # hold slide
        lean = 45
        leg_ext = 80
        drop = 22
    return {
        **_REST,
        'hips': _R(0),
        'spine': _R(-90) + _R(lean),
        'chest': _R(lean * 0.3),
        'neck': _R(lean * 0.4),
        'head': _R(lean * 0.4),
        # Arms for balance
        'left_shoulder': _R(-132 - 10),
        'left_upper_arm': _R(-38 - 55),
        'left_forearm': _R(25 + 45),
        'left_wrist': _R(15),
        'left_hand': _R(20),
        'right_shoulder': _R(132 + 10),
        'right_upper_arm': _R(38 + 55),
        'right_forearm': _R(-25 - 45),
        'right_wrist': -_R(15),
        'right_hand': -_R(20),
        # Right leg extends forward
        'right_hip': _R(81 + 5),
        'right_upper_leg': _R(-6 + leg_ext),
        'right_lower_leg': _R(9 - leg_ext * 0.5),
        'right_ankle': -_R(leg_ext * 0.25),
        'right_foot': _R(-20),
        # Left leg folds under
        'left_hip': _R(99 + 8),
        'left_upper_leg': _R(8 + leg_ext * 0.6),
        'left_lower_leg': _R(-12 - leg_ext * 0.8),
        'left_ankle': _R(leg_ext * 0.3),
        'left_foot': _R(20),
    }, drop * scale


# ─── COMBAT VARIANTS ───────────────────────────────────────

def gen_combo(t: float, params: Dict[str, Any] = None):
    """Combo — two-hit combination (left jab then right cross)."""
    p = params or {}
    dur = p.get('duration', 0.9)
    prog = min(t / dur, 1.0)
    # Two punches: 0-0.4 left, 0.4-0.9 right
    if prog < 0.4:
        sub = prog / 0.4
        # Left jab extends then retracts
        ext = math.sin(sub * math.pi)
        alt = -ext   # left forward
        seq = 1
    else:
        sub = (prog - 0.4) / 0.5
        ext = math.sin(sub * math.pi)
        alt = ext    # right forward
        seq = 2
    return {
        **_REST,
        'spine': _R(-88) - _R(ext * 4),
        'chest': _R(-alt * 10 * ext),
        'hips': _R(alt * 5 * ext),
        'neck': _R(ext * 5),
        'head': _R(ext * 5),
        'left_shoulder': _R(-132 + alt * 8),
        'left_upper_arm': _R(-38 - alt * 70),
        'left_forearm': _R(25 - alt * 60),
        'left_wrist': -_R(alt * 12),
        'left_hand': -_R(alt * 15),
        'right_shoulder': _R(132 + alt * 8),
        'right_upper_arm': _R(38 + alt * 70),
        'right_forearm': _R(-25 + alt * 60),
        'right_wrist': _R(alt * 12),
        'right_hand': _R(alt * 15),
        'left_hip': _R(99 + 4),
        'right_hip': _R(81 - 4),
        'left_upper_leg': _R(8 + 12),
        'left_lower_leg': _R(-12 - 14),
        'right_upper_leg': _R(-6 + 12),
        'right_lower_leg': _R(9 - 14),
        'left_ankle': _R(4),
        'right_ankle': -_R(4),
    }


def gen_elbow_strike(t: float, params: Dict[str, Any] = None):
    """Elbow strike — drive elbow forward/up (close combat)."""
    p = params or {}
    dur = p.get('duration', 0.5)
    prog = min(t / dur, 1.0)
    if prog < 0.2:
        ph = _ease(prog / 0.2)
        strike = 0.0  # chamber
        lean = -5 * ph
        seq = 0
    elif prog < 0.5:
        ph = _ease((prog - 0.2) / 0.3)
        strike = -90 * ph   # elbow comes forward/up
        lean = -5 + 10 * ph
        seq = 1
    else:
        ph = _ease((prog - 0.5) / 0.5)
        strike = -90 * (1 - ph)
        lean = 5 * (1 - ph)
        seq = 2
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'chest': _R(10 * seq),
        'neck': _R(lean * 0.4 + seq * 4),
        'head': _R(lean * 0.4 + seq * 4),
        'left_upper_arm': _R(-38 - 50),
        'left_forearm': _R(25 + 85 + 20 * seq),
        'left_wrist': _R(25),
        'left_hand': _R(30),
        # right arm chambers elbow
        'right_shoulder': _R(132 + 20),
        'right_upper_arm': _R(38 + 60 + strike * 0.6),
        'right_forearm': _R(-25 - 70 + strike * 0.4),
        'right_wrist': -_R(25),
        'right_hand': -_R(30),
        'left_hip': _R(99 + 5),
        'right_hip': _R(81 - 5),
        'left_upper_leg': _R(8 + 12),
        'left_lower_leg': _R(-12 - 16),
        'right_upper_leg': _R(-6 + 12),
        'right_lower_leg': _R(9 - 16),
        'left_ankle': _R(5),
        'right_ankle': -_R(5),
    }


def gen_roundhouse_kick(t: float, params: Dict[str, Any] = None):
    """Roundhouse kick — body twist + high spinning leg."""
    p = params or {}
    dur = p.get('duration', 0.8)
    prog = min(t / dur, 1.0)
    if prog < 0.25:  # chamber + twist
        ph = _ease(prog / 0.25)
        spin = 60 * ph
        kick = 70 * ph
        lean = -6 * ph
    elif prog < 0.5:  # strike
        ph = _ease((prog - 0.25) / 0.25)
        spin = 60 + 90 * ph
        kick = 70 + 60 * ph
        lean = -6 + 5 * ph
    else:  # recover
        ph = _ease((prog - 0.5) / 0.5)
        spin = 150 * (1 - ph)
        kick = 130 * (1 - ph)
        lean = -1 * (1 - ph)
    return {
        **_REST,
        'hips': _R(spin * 0.5),
        'spine': _R(-90) + _R(lean),
        'chest': _R(spin * 0.4),
        'neck': _R(lean * 0.4),
        'head': _R(lean * 0.4),
        'left_shoulder': _R(-132 - 15),
        'left_upper_arm': _R(-38 - 50),
        'left_forearm': _R(25 + 40),
        'left_wrist': _R(15),
        'left_hand': _R(20),
        'right_shoulder': _R(132 + 15),
        'right_upper_arm': _R(38 - 30),
        'right_forearm': _R(-25 - 20),
        'right_wrist': -_R(10),
        'right_hand': -_R(15),
        'left_hip': _R(99 + 6),
        'left_upper_leg': _R(8 + 18),
        'left_lower_leg': _R(-12 - 18),
        'left_ankle': _R(5),
        'left_foot': _R(20),
        'right_upper_leg': _R(-6 + kick),
        'right_lower_leg': _R(9 - kick * 0.5),
        'right_ankle': -_R(kick * 0.2),
        'right_foot': _R(-20),
    }


# ─── CINEMATIC / POSES ─────────────────────────────────────

def gen_pose_power(t: float, params: Dict[str, Any] = None):
    """Power pose — arms raised up/out, legs braced. Heroic/arrival shot."""
    p = params or {}
    dur = p.get('duration', 2.0)
    prog = min(t / dur, 1.0)
    rise = _ease(prog)
    breath = math.sin(prog * math.pi * 2) * 0.5
    return {
        **_REST,
        'spine': _R(-84),  # chest out
        'chest': _R(3),
        'neck': _R(-8),
        'head': _R(-8),
        'left_shoulder': _R(-132 - 20),
        'left_upper_arm': _R(-38 - 85),     # arms out at shoulder height
        'left_forearm': _R(25 + 60),
        'left_wrist': _R(20),
        'left_hand': _R(25),
        'right_shoulder': _R(132 + 20),
        'right_upper_arm': _R(38 + 85),
        'right_forearm': _R(-25 - 60),
        'right_wrist': -_R(20),
        'right_hand': -_R(25),
        'left_hip': _R(99 + 6),
        'right_hip': _R(81 - 6),
        'left_upper_leg': _R(8 + 14),
        'left_lower_leg': _R(-12 - 16),
        'right_upper_leg': _R(-6 + 14),
        'right_lower_leg': _R(9 - 16),
        'left_ankle': _R(5),
        'right_ankle': -_R(5),
    }


def gen_fist_pump(t: float, params: Dict[str, Any] = None):
    """Victory fist pump — arm thrusts up repeatedly."""
    p = params or {}
    dur = p.get('duration', 1.2)
    s = t % dur
    pump = max(0.0, math.sin(s * (2 * math.pi / 0.4)))  # pump every 0.4s
    pump = _ease(pump)
    return {
        **_REST,
        'spine': _R(-90) - _R(2),
        'neck': _R(4),
        'head': _R(4),
        'left_upper_arm': _R(-38),  # arm hangs
        'left_forearm': _R(25),
        'left_wrist': _R(0),
        'left_hand': _R(0),
        'right_upper_arm': _R(38 - 100 * pump),
        'right_forearm': _R(-25 + 20),  # arm thrusts overhead
        'right_wrist': -_R(15),
        'right_hand': -_R(20),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_upper_leg': _R(8 + 8),
        'left_lower_leg': _R(-12 - 10),
        'right_upper_leg': _R(-6 + 8),
        'right_lower_leg': _R(9 - 10),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }


def gen_bow(t: float, params: Dict[str, Any] = None):
    """Bowing — bend at hips with arm across body."""
    p = params or {}
    dur = p.get('duration', 1.0)
    prog = min(t / dur, 1.0)
    if prog < 0.4:
        ph = _ease(prog / 0.4)
        bow = 60 * ph  # hips bend forward
        arm_fwd = 50 * ph
        arm_up = 0
    elif prog < 0.6:  # hold bow
        bow = 60
        arm_fwd = 50
        arm_up = -30
    else:  # rise
        ph = _ease((prog - 0.6) / 0.4)
        bow = 60 * (1 - ph)
        arm_fwd = 50 * (1 - ph)
        arm_up = 0
    return {
        **_REST,
        'hips': _R(bow * 0.3),
        'spine': _R(-90) - _R(bow * 0.6),
        'chest': _R(-bow * 0.2),
        'neck': _R(-bow * 0.2),
        'head': _R(-bow * 0.2),
        'left_shoulder': _R(-132 + 10),
        'left_upper_arm': _R(-38 + arm_fwd - arm_up),
        'left_forearm': _R(25 + 30),
        'left_wrist': _R(15),
        'left_hand': _R(20),
        'right_shoulder': _R(132 + 10),
        'right_upper_arm': _R(38 - arm_fwd - arm_up),  # arms together crossing
        'right_forearm': _R(-25 + 30),
        'right_wrist': -_R(15),
        'right_hand': -_R(20),
        'left_hip': _R(99 + bow),
        'right_hip': _R(81 - bow),
        'left_upper_leg': _R(8 + 14),
        'left_lower_leg': _R(-12 - 16),
        'right_upper_leg': _R(-6 + 14),
        'right_lower_leg': _R(9 - 16),
        'left_ankle': _R(4),
        'right_ankle': -_R(4),
    }, 0  # non-height (returns pose, 0)


def gen_pointing_finger(t: float, params: Dict[str, Any] = None):
    """Pointing directly at something/someone (more emphatic vs point)."""
    p = params or {}
    dur = p.get('duration', 1.2)
    prog = min(t / dur, 1.0)
    if prog < 0.3:
        ph = _ease(prog / 0.3)
        raise_ = ph
        point = ph
    else:
        raise_ = 1.0
        point = 1.0
    return {
        **_REST,
        'spine': _R(-88),
        'neck': _R(4),
        'head': _R(4),
        'left_upper_arm': _R(-38 + 40 * raise_),  # guard arm points too
        'left_forearm': _R(25 + 50),
        'left_wrist': _R(20),
        'left_hand': _R(25),
        'right_shoulder': _R(132 - 20),
        'right_upper_arm': _R(38 - 90),
        'right_forearm': _R(-25 + 25),
        'right_wrist': -_R(15),
        'right_hand': -_R(20),
        'left_hip': _R(99 + 4),
        'right_hip': _R(81 - 4),
        'left_upper_leg': _R(8 + 12),
        'left_lower_leg': _R(-12 - 14),
        'right_upper_leg': _R(-6 + 12),
        'right_lower_leg': _R(9 - 14),
        'left_ankle': _R(4),
        'right_ankle': -_R(4),
    }


def gen_charge_energy(t: float, params: Dict[str, Any] = None):
    """Charging a power move — arms pull back, body tightens, glow later."""
    p = params or {}
    dur = p.get('duration', 1.2)
    prog = min(t / dur, 1.0)
    if prog < 0.3:
        ph = _ease(prog / 0.3)
        pull = ph
        crouch = ph
        arm_up = 10 * ph
    else:
        pull = 1.0
        crouch = 1.0
        arm_up = 30
    return {
        **_REST,
        'spine': _R(-90) + _R(15 * crouch),
        'chest': _R(0),
        'neck': _R(10 * crouch),
        'head': _R(10 * crouch),
        'left_upper_arm': _R(-38 - 60 - 30 * crouch),
        'left_forearm': _R(25 + 50),
        'left_wrist': _R(20),
        'left_hand': _R(25),
        'right_upper_arm': _R(38 + 60 + 30 * crouch),
        'right_forearm': _R(-25 - 50),
        'right_wrist': -_R(20),
        'right_hand': -_R(25),
        'left_hip': _R(99 + 10),
        'right_hip': _R(81 - 10),
        'left_upper_leg': _R(8 + 70 * crouch),
        'left_lower_leg': _R(-12 - 70 * crouch),
        'right_upper_leg': _R(-6 + 70 * crouch),
        'right_lower_leg': _R(9 - 70 * crouch),
        'left_ankle': _R(20 * crouch),
        'right_ankle': -_R(20 * crouch),
    }, crouch * 25  # height-driven: sinks as it charges


def gen_leap(t: float, params: Dict[str, Any] = None):
    """Leap/hurdle — larcancy jumps over obstacless obscures."""
    # Actually a fast jump across space
    p = params or {}
    dur = p.get('duration', 0.7)
    prog = min(t / dur, 1.0)
    if prog < 0.2:
        ph = _ease(prog / 0.2)
        crouch = ph
        raise_t = 0
    elif prog < 0.5:
        ph = _ease((prog - 0.2) / 0.3)
        raise_t = ph
        crouch = 1 - ph
    else:
        raise_t = 1.0
        crouch = 0
        if prog < 0.8:
            extend = _ease((prog - 0.5) / 0.3)
            raise_t = 1 - extend * 0.6
        else:
            extend = _ease((prog - 0.8) / 0.2)
            crouch = extend
    vshape = math.sin(min(prog / 0.5, 1.0) * math.pi)  # legs tuck then extend
    return {
        **_REST,
        'spine': _R(-90) + _R(-5 * raise_t + 10 * crouch),
        'neck': _R(-5),
        'head': _R(-5),
        'left_shoulder': _R(-132 + 30 * raise_t),
        'left_upper_arm': _R(-38 - 80 * raise_t + 20 * crouch),
        'left_forearm': _R(25 + 20),
        'left_wrist': _R(5),
        'left_hand': _R(10),
        'right_shoulder': _R(132 - 30 * raise_t),
        'right_upper_arm': _R(38 + 80 * raise_t - 20 * crouch),
        'right_forearm': _R(-25 - 20),
        'right_wrist': -_R(5),
        'right_hand': -_R(10),
        # Legs tuck during arc, extend on landing
        'left_upper_leg': _R(8 + 30 * raise_t - 60 * crouch),
        'left_lower_leg': _R(-12 - 70 * raise_t + 60 * crouch),
        'left_ankle': _R(30 * raise_t),
        'left_foot': _R(25),
        'right_upper_leg': _R(-6 + 30 * raise_t - 60 * crouch),
        'right_lower_leg': _R(9 - 70 * raise_t + 60 * crouch),
        'right_ankle': -_R(30 * raise_t),
        'right_foot': _R(-25),
    }


# ─── WEAPON HANDLING ───────────────────────────────────────

def gen_draw_weapon(t: float, params: Dict[str, Any] = None):
    """Draw weapon — hand reaches to side/back, pulls out, holds in guard."""
    p = params or {}
    dur = p.get('duration', 0.8)
    prog = min(t / dur, 1.0)
    if prog < 0.4:  # reach back
        ph = _ease(prog / 0.4)
        reach = ph
        draw = 0.0
    elif prog < 0.7:  # pull out
        ph = _ease((prog - 0.4) / 0.3)
        reach = 1 - ph
        draw = ph
    else:  # present
        draw = 1.0
        reach = 0.0
    return {
        **_REST,
        'spine': _R(-88),
        'neck': _R(-4 * draw),
        'head': _R(-4 * draw),
        'left_upper_arm': _R(-38 - 25),
        'left_forearm': _R(25 + 30),
        'left_wrist': _R(10),
        'left_hand': _R(15),
        'right_shoulder': _R(132 + 25 * reach),
        'right_upper_arm': _R(38 - 70 * reach + 50 * draw),
        'right_forearm': _R(-25 - 55 * reach + 45 * draw),
        'right_wrist': -_R(10 * reach + 15 * draw),
        'right_hand': -_R(15 * reach + 20 * draw),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_upper_leg': _R(8 + 8),
        'left_lower_leg': _R(-12 - 10),
        'right_upper_leg': _R(-6 + 8),
        'right_lower_leg': _R(9 - 10),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }


def gen_swing_sword(t: float, params: Dict[str, Any] = None):
    """Sword swing — horizontal slash across the body."""
    p = params or {}
    dur = p.get('duration', 0.6)
    prog = min(t / dur, 1.0)
    if prog < 0.2:  # chamber up-back
        ph = _ease(prog / 0.2)
        slash = 0.0
        wind = ph * 70
        lean = -8 * ph
    elif prog < 0.5:  # slash across
        ph = _ease((prog - 0.2) / 0.3)
        slash = ph
        wind = 70 - ph * 130
        lean = -8 + 14 * ph
    else:  # follow through
        ph = _ease((prog - 0.5) / 0.5)
        slash = 1.0
        wind = -60 + ph * 30
        lean = 6 * (1 - ph)
    return {
        **_REST,
        'hips': _R(slash * 12),
        'spine': _R(-90) + _R(lean),
        'chest': _R(slash * 14),
        'neck': _R(lean * 0.4),
        'head': _R(lean * 0.4),
        'left_upper_arm': _R(-38 - 30),
        'left_forearm': _R(25 + 35),
        'left_wrist': _R(12),
        'left_hand': _R(15),
        # sword arm
        'right_shoulder': _R(132 + wind * 0.15),
        'right_upper_arm': _R(38 - wind),
        'right_forearm': _R(-25 + 20),
        'right_wrist': -_R(10),
        'right_hand': -_R(15),
        'left_hip': _R(99 + slash * 4),
        'right_hip': _R(81 - slash * 4),
        'left_upper_leg': _R(8 + 12),
        'left_lower_leg': _R(-12 - 14),
        'right_upper_leg': _R(-6 + 12),
        'right_lower_leg': _R(9 - 14),
        'left_ankle': _R(4),
        'right_ankle': -_R(4),
    }


def gen_aim_gun(t: float, params: Dict[str, Any] = None):
    """Aim gun — both arms extended forward, sighting down, hold."""
    p = params or {}
    dur = p.get('duration', 1.5)
    prog = min(t / dur, 1.0)
    if prog < 0.3:
        ph = _ease(prog / 0.3)
        raise_ = ph
        aim = ph
        lean = -3 * ph
    else:
        raise_ = 1.0
        aim = 1.0
        lean = -3
    # sight adjustment wobble
    wobble = math.sin(t * 8) * _R(1.5) * aim
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'neck': _R(5 * aim),
        'head': _R(5 * aim),
        'left_shoulder': _R(-132 + 10),
        'left_upper_arm': _R(-38 - 90 * aim),   # both arms forward
        'left_forearm': _R(25 + 55 * aim),
        'left_wrist': _R(20 * aim),
        'left_hand': _R(25 * aim),
        'right_shoulder': _R(132 - 10),
        'right_upper_arm': _R(38 + 95 * aim),   # gun arm forward
        'right_forearm': _R(-25 - 65 * aim),
        'right_wrist': -_R(20 * aim) + wobble,
        'right_hand': -_R(25 * aim),
        'left_hip': _R(99 + 4),
        'right_hip': _R(81 - 4),
        'left_upper_leg': _R(8 + 12),
        'left_lower_leg': _R(-12 - 14),
        'right_upper_leg': _R(-6 + 12),
        'right_lower_leg': _R(9 - 14),
        'left_ankle': _R(4),
        'right_ankle': -_R(4),
    }


def gen_shoot(t: float, params: Dict[str, Any] = None):
    """Shoot — recoil punch-back with flash (no projectile yet)."""
    p = params or {}
    dur = p.get('duration', 0.3)
    prog = min(t / dur, 1.0)
    if prog < 0.15:
        ph = _ease(prog / 0.15)
        recoil = ph
        arm_up = ph
        lean = -4 * ph
    else:
        ph = _ease((prog - 0.15) / 0.85)
        recoil = 1 - ph
        arm_up = 1 - ph * 0.3
        lean = -4 + ph * 4
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'chest': _R(-recoil * 6),
        'neck': _R(3),
        'head': _R(3),
        'left_upper_arm': _R(-38 - 90 - recoil * 20),
        'left_forearm': _R(25 + 60 - recoil * 15),
        'left_wrist': _R(20),
        'left_hand': _R(25),
        'right_shoulder': _R(132 - 10),
        'right_upper_arm': _R(38 + 95 + recoil * 25),   # recoil jerk back
        'right_forearm': _R(-25 - 65 + recoil * 20),
        'right_wrist': -_R(20),
        'right_hand': -_R(25),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_upper_leg': _R(8 + 12),
        'left_lower_leg': _R(-12 - 14),
        'right_upper_leg': _R(-6 + 12),
        'right_lower_leg': _R(9 - 14),
        'left_ankle': _R(4),
        'right_ankle': -_R(4),
    }


def gen_throw_shield(t: float, params: Dict[str, Any] = None):
    """Throw shield — arm whips forward with spin, follow-through."""
    p = params or {}
    dur = p.get('duration', 0.7)
    prog = min(t / dur, 1.0)
    if prog < 0.25:  # wind up
        ph = _ease(prog / 0.25)
        back = ph * 100
        lean = -8 * ph
    elif prog < 0.55:  # release
        ph = _ease((prog - 0.25) / 0.3)
        back = 100 * (1 - ph) - 130 * ph
        lean = -8 + 12 * ph
    else:  # follow through
        ph = _ease((prog - 0.55) / 0.45)
        back = -30 + ph * 20
        lean = 4 * (1 - ph)
    return {
        **_REST,
        'hips': _R(8 * min(prog / 0.55, 1.0)),
        'spine': _R(-90) + _R(lean),
        'chest': _R(8 * min(prog / 0.55, 1.0)),
        'neck': _R(lean * 0.4),
        'head': _R(lean * 0.4),
        'left_upper_arm': _R(-38 - 40),
        'left_forearm': _R(25 + 30),
        'left_wrist': _R(10),
        'left_hand': _R(15),
        # throwing arm
        'right_shoulder': _R(132 - 8),
        'right_upper_arm': _R(38 - back),
        'right_forearm': _R(-25 - back * 0.5),
        'right_wrist': -_R(back * 0.2),
        'right_hand': -_R(back * 0.25),
        'left_hip': _R(99 + 4),
        'right_hip': _R(81 - 4),
        'left_upper_leg': _R(8 + 14),
        'left_lower_leg': _R(-12 - 16),
        'right_upper_leg': _R(-6 + 14),
        'right_lower_leg': _R(9 - 16),
        'left_ankle': _R(5),
        'right_ankle': -_R(5),
    }


def gen_reload(t: float, params: Dict[str, Any] = None):
    """Reload — weapon drops, hand reaches to side, brings back up."""
    p = params or {}
    dur = p.get('duration', 0.8)
    prog = min(t / dur, 1.0)
    if prog < 0.3:  # drop weapon down
        ph = _ease(prog / 0.3)
        drop = ph
        side = 0
        lean = 8 * ph
    elif prog < 0.6:  # hand to side
        ph = _ease((prog - 0.3) / 0.3)
        drop = 1
        side = ph
        lean = 8 - 4 * ph
    else:  # bring back up
        ph = _ease((prog - 0.6) / 0.4)
        drop = 1 - ph
        side = 1 - ph
        lean = 4 * (1 - ph)
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'neck': _R(-5 * drop),
        'head': _R(-5 * drop),
        'left_upper_arm': _R(-38 - 30),
        'left_forearm': _R(25 + 30),
        'left_wrist': _R(10),
        'left_hand': _R(15),
        'right_shoulder': _R(132 + 10 * side),
        'right_upper_arm': _R(38 + 60 * drop - 40 * side),
        'right_forearm': _R(-25 - 55 * drop + 40 * side),
        'right_wrist': -_R(15),
        'right_hand': -_R(20),
        'left_hip': _R(99 + 3),
        'right_hip': _R(81 - 3),
        'left_upper_leg': _R(8 + 8),
        'left_lower_leg': _R(-12 - 10),
        'right_upper_leg': _R(-6 + 8),
        'right_lower_leg': _R(9 - 10),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }


# ─── DRAMATIC / FALL / RECOVERY ────────────────────────────

def gen_collapse(t: float, params: Dict[str, Any] = None):
    """Collapse — body folds down to knees, arms go limp (defeat/fall)."""
    p = params or {}
    dur = p.get('duration', 1.2)
    scale = p.get('scale', 1.0)
    prog = min(t / dur, 1.0)
    e = _ease(prog)
    drop = 40 * scale * e        # hips descend to near floor
    lean = 60 * e                # body folds forward
    arm_limp = 80 * e            # arms hang
    knee = 80 * e                # knees fold
    return {
        **_REST,
        'hips': _R(30 * e),
        'spine': _R(-90) + _R(lean),
        'neck': _R(-lean * 0.5),
        'head': _R(-lean * 0.5),
        'left_upper_arm': _R(-38 + arm_limp * 0.5),
        'left_forearm': _R(25 + arm_limp * 0.6),
        'left_wrist': _R(arm_limp * 0.3),
        'left_hand': _R(arm_limp * 0.4),
        'right_upper_arm': _R(38 - arm_limp * 0.5),
        'right_forearm': _R(-25 - arm_limp * 0.6),
        'right_wrist': -_R(arm_limp * 0.3),
        'right_hand': -_R(arm_limp * 0.4),
        'left_hip': _R(99 + 6),
        'right_hip': _R(81 - 6),
        'left_upper_leg': _R(8 + knee),
        'left_lower_leg': _R(-12 - knee * 0.9),
        'right_upper_leg': _R(-6 + knee),
        'right_lower_leg': _R(9 - knee * 0.9),
        'left_ankle': _R(knee * 0.4),
        'right_ankle': -_R(knee * 0.4),
    }, drop


def gen_get_back_up(t: float, params: Dict[str, Any] = None):
    """Get back up — reverse of collapse, pushes up off the floor."""
    p = params or {}
    dur = p.get('duration', 1.2)
    scale = p.get('scale', 1.0)
    prog = min(t / dur, 1.0)
    pose, drop = gen_collapse(dur - t, {'duration': dur, 'scale': scale})
    return pose, drop - 40 * scale


# ─── FLIGHT / SUPERPOWER ───────────────────────────────────

def gen_fly(t: float, params: Dict[str, Any] = None):
    """Fly — arms swept back, body horizontal, legs trailing (superhero)."""
    p = params or {}
    dur = p.get('duration', 2.0)
    prog = min(t / dur, 1.0)
    # Ramp into flying pose
    if prog < 0.3:
        ph = _ease(prog / 0.3)
        horiz = ph
    else:
        horiz = 1.0
    breath = math.sin(t * 2) * 2
    return {
        **_REST,
        'hips': _R(-90 * horiz),   # rotate to horizontal
        'spine': _R(-90) + _R(-5),
        'chest': _R(0),
        'neck': _R(10 * horiz),
        'head': _R(10 * horiz),    # head up looking forward
        'left_shoulder': _R(-132 - 40 * horiz),
        'left_upper_arm': _R(-38 - 55 * horiz - breath),   # arms swept back
        'left_forearm': _R(25 + 10),
        'left_wrist': _R(5),
        'left_hand': _R(10),
        'right_shoulder': _R(132 + 40 * horiz),
        'right_upper_arm': _R(38 + 55 * horiz + breath),
        'right_forearm': _R(-25 - 10),
        'right_wrist': -_R(5),
        'right_hand': -_R(10),
        'left_upper_leg': _R(8 + 10),
        'left_lower_leg': _R(-12 - 5),
        'right_upper_leg': _R(-6 + 10),
        'right_lower_leg': _R(9 - 5),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }, horiz * -20  # rise into air (negative offset = up)


def gen_hover(t: float, params: Dict[str, Any] = None):
    """Hover — floating in place, arms slightly out for balance, gentle bob."""
    p = params or {}
    dur = p.get('duration', 2.0)
    prog = min(t / dur, 1.0)
    if prog < 0.3:
        ph = _ease(prog / 0.3)
        rise = ph
    else:
        rise = 1.0
    bob = math.sin(t * 3) * 3 * rise
    return {
        **_REST,
        'spine': _R(-90) - _R(2),
        'neck': _R(2),
        'head': _R(2),
        'left_shoulder': _R(-132 - 15 * rise),
        'left_upper_arm': _R(-38 - 45 * rise),
        'left_forearm': _R(25 + 30 * rise),
        'left_wrist': _R(10 * rise),
        'left_hand': _R(15 * rise),
        'right_shoulder': _R(132 + 15 * rise),
        'right_upper_arm': _R(38 + 45 * rise),
        'right_forearm': _R(-25 - 30 * rise),
        'right_wrist': -_R(10 * rise),
        'right_hand': -_R(15 * rise),
        'left_upper_leg': _R(8 + 6),
        'left_lower_leg': _R(-12 - 5),
        'right_upper_leg': _R(-6 + 6),
        'right_lower_leg': _R(9 - 5),
        'left_ankle': _R(2),
        'right_ankle': -_R(2),
    }, rise * -15 + bob * 0.0  # rises into air, then holds (bob subtle)


def gen_land(t: float, params: Dict[str, Any] = None):
    """Land — descent crouch with arms out for balance, then stand."""
    p = params or {}
    dur = p.get('duration', 0.6)
    scale = p.get('scale', 1.0)
    prog = min(t / dur, 1.0)
    e = _ease(prog)
    crouch = 1 - e  # deep crouch at start, standing at end
    return {
        **_REST,
        'spine': _R(-90) + _R(20 * crouch),
        'neck': _R(10 * crouch),
        'head': _R(10 * crouch),
        'left_shoulder': _R(-132 + 15 * crouch),
        'left_upper_arm': _R(-38 - 70 * crouch),
        'left_forearm': _R(25 + 45 * crouch),
        'left_wrist': _R(15 * crouch),
        'left_hand': _R(20 * crouch),
        'right_shoulder': _R(132 - 15 * crouch),
        'right_upper_arm': _R(38 + 70 * crouch),
        'right_forearm': _R(-25 - 45 * crouch),
        'right_wrist': -_R(15 * crouch),
        'right_hand': -_R(20 * crouch),
        'left_upper_leg': _R(8 + 60 * crouch),
        'left_lower_leg': _R(-12 - 65 * crouch),
        'right_upper_leg': _R(-6 + 60 * crouch),
        'right_lower_leg': _R(9 - 65 * crouch),
        'left_ankle': _R(18 * crouch),
        'right_ankle': -_R(18 * crouch),
    }, crouch * 22 * scale


def gen_energy_blast(t: float, params: Dict[str, Any] = None):
    """Energy blast — both palms forward, recoil, arm thrust (power move)."""
    p = params or {}
    dur = p.get('duration', 0.8)
    prog = min(t / dur, 1.0)
    if prog < 0.25:  # charge back
        ph = _ease(prog / 0.25)
        pull = ph
        lean = -8 * ph
    elif prog < 0.55:  # release
        ph = _ease((prog - 0.25) / 0.3)
        pull = 1 - ph
        lean = -8 + 12 * ph
    else:  # hold + settle
        ph = _ease((prog - 0.55) / 0.45)
        pull = 0
        lean = 4 * (1 - ph)
    thrust = 1 - pull
    return {
        **_REST,
        'spine': _R(-90) + _R(lean),
        'chest': _R(-thrust * 8),
        'hips': _R(thrust * 5),
        'neck': _R(5 * thrust),
        'head': _R(5 * thrust),
        'left_shoulder': _R(-132 + 12),
        'left_upper_arm': _R(-38 - 95 * thrust + 30 * pull),
        'left_forearm': _R(25 + 60 * thrust),
        'left_wrist': _R(25 * thrust),
        'left_hand': _R(30 * thrust),
        'right_shoulder': _R(132 - 12),
        'right_upper_arm': _R(38 + 95 * thrust - 30 * pull),
        'right_forearm': _R(-25 - 60 * thrust),
        'right_wrist': -_R(25 * thrust),
        'right_hand': -_R(30 * thrust),
        'left_upper_leg': _R(8 + 16),
        'left_lower_leg': _R(-12 - 18),
        'right_upper_leg': _R(-6 + 16),
        'right_lower_leg': _R(9 - 18),
        'left_ankle': _R(5),
        'right_ankle': -_R(5),
    }


# ─── EXTRA MOVEMENT & EXPRESSION ───────────────────────────

def gen_sprint(t: float, params: Dict[str, Any] = None):
    """Sprint — all-out run, big lean, full extension, heels kick up."""
    p = params or {}
    speed = p.get('speed', 2.5)
    stride = p.get('stride', 95)
    s = t * speed
    swing = math.sin(s * math.pi)
    swing_opp = math.sin(s * math.pi + math.pi)
    lift = abs(math.sin(s * math.pi))
    double = math.sin(s * math.pi * 2)
    twist = swing * _R(9)
    knee_flex = _R(28) + abs(swing) * _R(58)   # deeper heel kick
    elbow_bend = _R(88) - abs(swing) * _R(30)
    return {
        **_REST,
        'spine': _R(-74) + double * _R(4),      # hard forward lean
        'chest': twist,
        'neck': _R(-10),
        'head': _R(-10) + double * _R(3),
        'left_shoulder': _R(-132) - swing * _R(10),
        'right_shoulder': _R(132) - swing_opp * _R(10),
        'left_upper_arm': _R(-38) - swing * _R(55),
        'left_forearm': elbow_bend,
        'left_wrist': -swing * _R(10),
        'left_hand': -swing * _R(25),
        'right_upper_arm': _R(38) - swing_opp * _R(55),
        'right_forearm': -elbow_bend,
        'right_wrist': -swing_opp * _R(10),
        'right_hand': -swing_opp * _R(25),
        'left_hip': _R(99) + swing * _R(6),
        'left_upper_leg': _R(8) + swing * _R(30),
        'left_lower_leg': -knee_flex,
        'left_ankle': lift * _R(14) - _R(5),
        'left_foot': _R(20) + lift * _R(18),
        'right_hip': _R(81) + swing_opp * _R(6),
        'right_upper_leg': _R(-6) + swing_opp * _R(30),
        'right_lower_leg': knee_flex,
        'right_ankle': -(lift * _R(14) - _R(5)),
        'right_foot': _R(-20) + lift * _R(18),
        'hips': -twist,
    }


def gen_backflip(t: float, params: Dict[str, Any] = None):
    """Backflip — crouch, jump, rotate backward 360°, land."""
    p = params or {}
    dur = p.get('duration', 1.0)
    scale = p.get('scale', 1.0)
    prog = min(t / dur, 1.0)
    if prog < 0.2:  # crouch load
        ph = _ease(prog / 0.2)
        crouch = ph
        rot = 0
        raise_t = 0
        tuck = 0
    elif prog < 0.8:  # flip in air
        ph = _ease((prog - 0.2) / 0.6)
        crouch = 0
        rot = ph * 360
        raise_t = 1
        tuck = math.sin(ph * math.pi)   # tuck mid-flip for rotation
    else:  # land
        ph = _ease((prog - 0.8) / 0.2)
        crouch = ph
        rot = 360
        raise_t = 0
        tuck = 0
    return {
        **_REST,
        'hips': _R(rot),
        'spine': _R(-90) + _R(-10 * raise_t + 20 * crouch),
        'neck': _R(-5 * raise_t),
        'head': _R(-5 * raise_t),
        'left_shoulder': _R(-132 + 20 * raise_t),
        'left_upper_arm': _R(-38 - 70 * raise_t + 30 * crouch),
        'left_forearm': _R(25 + 40 * raise_t),
        'left_wrist': _R(15 * raise_t),
        'left_hand': _R(20 * raise_t),
        'right_shoulder': _R(132 - 20 * raise_t),
        'right_upper_arm': _R(38 + 70 * raise_t - 30 * crouch),
        'right_forearm': _R(-25 - 40 * raise_t),
        'right_wrist': -_R(15 * raise_t),
        'right_hand': -_R(20 * raise_t),
        'left_hip': _R(99 + 5),
        'left_upper_leg': _R(8 + 40 * raise_t * tuck + 50 * crouch),
        'left_lower_leg': _R(-12 - 50 * raise_t * tuck - 55 * crouch),
        'left_ankle': _R(20 * raise_t),
        'left_foot': _R(20),
        'right_hip': _R(81 - 5),
        'right_upper_leg': _R(-6 + 40 * raise_t * tuck + 50 * crouch),
        'right_lower_leg': _R(9 - 50 * raise_t * tuck - 55 * crouch),
        'right_ankle': -_R(20 * raise_t),
        'right_foot': _R(-20),
    }, 0  # physics handles the arc; keep hips grounded (0 offset)


def gen_dance(t: float, params: Dict[str, Any] = None):
    """Dance — rhythmic stepping, arm grooves, hip sway."""
    p = params or {}
    dur = p.get('duration', 3.0)
    s = t % dur
    beat = s * (2 * math.pi / 0.5)   # ~120 BPM
    b = math.sin(beat)
    b2 = math.sin(beat * 2)
    return {
        **_REST,
        'spine': _R(-88) + _R(b2 * 3),
        'chest': _R(b * 4),
        'hips': _R(b * 5),            # hip sway
        'neck': _R(b2 * 4),
        'head': _R(b2 * 4),
        'left_shoulder': _R(-132 - b * 8),
        'right_shoulder': _R(132 + b * 8),
        'left_upper_arm': _R(-38 - 40 - b * 15),   # arms up and grooving
        'left_forearm': _R(25 + 45 + b2 * 10),
        'left_wrist': _R(b2 * 12),
        'left_hand': _R(b2 * 15),
        'right_upper_arm': _R(38 + 40 + b * 15),
        'right_forearm': _R(-25 - 45 + b2 * 10),
        'right_wrist': -_R(b2 * 12),
        'right_hand': -_R(b2 * 15),
        'left_upper_leg': _R(8 + 25 + b * 10),
        'left_lower_leg': _R(-12 - 30 - b2 * 8),
        'left_ankle': _R(b2 * 8),
        'left_foot': _R(20),
        'right_upper_leg': _R(-6 + 25 - b * 10),
        'right_lower_leg': _R(9 - 30 + b2 * 8),
        'right_ankle': -_R(b2 * 8),
        'right_foot': _R(-20),
    }


def gen_celebrate(t: float, params: Dict[str, Any] = None):
    """Celebrate — jump, arms up, victory pump (loop)."""
    p = params or {}
    dur = p.get('duration', 2.0)
    s = t % dur
    pump = max(0.0, math.sin(s * (2 * math.pi / 0.35)))
    pump = _ease(pump)
    hop = abs(math.sin(s * (2 * math.pi / 0.7))) * 8
    return {
        **_REST,
        'spine': _R(-84) - _R(2 * pump),
        'chest': _R(3),
        'neck': _R(-8),
        'head': _R(-8),
        'left_shoulder': _R(-132 - 15),
        'left_upper_arm': _R(-38 - 90 - pump * 10),
        'left_forearm': _R(25 + 50),
        'left_wrist': _R(20),
        'left_hand': _R(25),
        'right_shoulder': _R(132 + 15),
        'right_upper_arm': _R(38 + 90 + pump * 10),
        'right_forearm': _R(-25 - 50),
        'right_wrist': -_R(20),
        'right_hand': -_R(25),
        'left_upper_leg': _R(8 + 10),
        'left_lower_leg': _R(-12 - 12),
        'right_upper_leg': _R(-6 + 10),
        'right_lower_leg': _R(9 - 12),
        'left_ankle': _R(3),
        'right_ankle': -_R(3),
    }, -hop  # hop into the air


def gen_tremble(t: float, params: Dict[str, Any] = None):
    """Tremble — shake in place (cold/fear), fast micro-motion."""
    p = params or {}
    dur = p.get('duration', 2.0)
    s = t % dur
    sh = math.sin(s * 40) * _R(3)   # fast shake
    return {
        **_REST,
        'spine': _R(-90) + sh,
        'chest': _R(math.sin(s * 40 + 1) * _R(2)),
        'neck': _R(6 + sh),
        'head': _R(6 + sh),
        'left_shoulder': _R(-132 + 12) + sh,
        'right_shoulder': _R(132 - 12) - sh,
        'left_upper_arm': _R(-38 + 10) + sh,
        'left_forearm': _R(25 + 8) + sh,
        'left_wrist': _R(5) + sh,
        'left_hand': _R(8) + sh,
        'right_upper_arm': _R(38 - 10) - sh,
        'right_forearm': _R(-25 - 8) - sh,
        'right_wrist': -_R(5) - sh,
        'right_hand': -_R(8) - sh,
        'left_hip': _R(99 + 4),
        'right_hip': _R(81 - 4),
        'left_upper_leg': _R(8 + 8),
        'left_lower_leg': _R(-12 - 10),
        'right_upper_leg': _R(-6 + 8),
        'right_lower_leg': _R(9 - 10),
        'left_ankle': _R(3 + sh * 0.5),
        'right_ankle': -_R(3 + sh * 0.5),
    }


def gen_crawl(t: float, params: Dict[str, Any] = None):
    """Crawl — on hands and knees, slow forward movement."""
    p = params or {}
    dur = p.get('duration', 1.5)
    scale = p.get('scale', 1.0)
    prog = min(t / dur, 1.0)
    e = _ease(prog)
    drop = 34 * scale * e     # hips down to hands-and-knees height
    # Alternating limb advance
    step = math.sin(t * 4) * 20
    return {
        **_REST,
        'hips': _R(0),
        'spine': _R(-90) + _R(25 * e),
        'neck': _R(15 * e),
        'head': _R(15 * e),
        'left_shoulder': _R(-132 + 30 * e),
        'left_upper_arm': _R(-38 - 95 * e + step),
        'left_forearm': _R(25 + 80 * e),
        'left_wrist': _R(20 * e),
        'left_hand': _R(25 * e),
        'right_shoulder': _R(132 - 30 * e),
        'right_upper_arm': _R(38 + 95 * e - step),
        'right_forearm': _R(-25 - 80 * e),
        'right_wrist': -_R(20 * e),
        'right_hand': -_R(25 * e),
        'left_hip': _R(99 + 8),
        'left_upper_leg': _R(8 + 55 * e),
        'left_lower_leg': _R(-12 - 60 * e),
        'left_ankle': _R(20 * e),
        'left_foot': _R(20),
        'right_hip': _R(81 - 8),
        'right_upper_leg': _R(-6 + 55 * e),
        'right_lower_leg': _R(9 - 60 * e),
        'right_ankle': -_R(20 * e),
        'right_foot': _R(-20),
    }, drop


def gen_look(t: float, params: Dict[str, Any] = None):
    """Look — head turns to scan (left/right/up), body still."""
    p = params or {}
    dur = p.get('duration', 1.5)
    prog = min(t / dur, 1.0)
    # Head pans left then right then back
    pan = math.sin(prog * math.pi * 2) * 30
    return {
        **_REST,
        'spine': _R(-90) + _R(pan * 0.1),
        'neck': _R(pan * 0.7),
        'head': _R(pan),
        'left_upper_arm': _R(-38) + math.sin(t * 1.5) * _R(1),
        'right_upper_arm': _R(38) + math.sin(t * 1.5) * _R(1),
        'left_forearm': _R(25),
        'right_forearm': _R(-25),
        'left_wrist': _R(0),
        'right_wrist': _R(0),
        'left_hand': _R(0),
        'right_hand': _R(0),
        'left_hip': _R(99),
        'right_hip': _R(81),
        'left_upper_leg': _R(8),
        'left_lower_leg': _R(-12),
        'right_upper_leg': _R(-6),
        'right_lower_leg': _R(9),
        'left_ankle': _R(0),
        'right_ankle': _R(0),
        'left_foot': _R(20),
        'right_foot': _R(-20),
    }


# ─── REGISTRY ──────────────────────────────────────────────

# Each entry: (generator_fn, has_position_offset, default_params)
# Loop semantics match the action's intent: locomotion/emotes loop, combat
# gestures and one-shot transitions don't. sneak/walk/run advance position.
GENERATORS = {
    # ── Locomotion (loop, position-accumulating) ──
    'idle':  (gen_idle,  False, {'speed': 1.0}),
    'walk':  (gen_walk,  True,  {'speed': 1.2, 'stride': 55, 'step_height': 12, 'bounce': 3}),
    'run':   (gen_run,   True,  {'speed': 2.0, 'stride': 80, 'step_height': 18, 'bounce': 8}),
    'sneak': (gen_sneak, True,  {'speed': 0.7, 'stride': 26, 'step_height': 4, 'bounce': 1.5,
                                 'duration': 1.5}),

    # ── Acrobatics / one-shot movement ──
    'jump':  (gen_jump,  False, {'height': 50, 'duration': 1.1}),
    'fall':  (gen_fall,  False, {'duration': 0.8}),
    'turn':  (gen_turn,  False, {'duration': 0.4}),
    'crouch':(gen_crouch,False, {'duration': 0.8}),

    # ── Height-driven (sit/stand/kneel/lie family) ──
    'sit':       (gen_sit,       False, {'duration': 1.2}),
    'stand_up':  (gen_stand_up,  False, {'duration': 1.2}),
    'kneel':     (gen_kneel,     False, {'duration': 1.0}),
    'lie_down':  (gen_lie_down,  False, {'duration': 1.4}),
    'get_up':    (gen_get_up,    False, {'duration': 1.4}),

    # ── Gestures (one-shot) ──
    'wave':  (gen_wave,  False, {'duration': 2.0}),
    'point': (gen_point, False, {'duration': 1.0}),
    'clap':  (gen_clap,  False, {'duration': 1.2}),
    'nod':   (gen_nod,   False, {'duration': 1.0}),
    'shake_head': (gen_shake_head, False, {'duration': 1.0}),

    # ── Object interaction (one-shot) ──
    'pick_up':  (gen_pick_up,  False, {'duration': 1.4}),
    'put_down': (gen_put_down, False, {'duration': 1.4}),
    'throw':    (gen_throw,    False, {'duration': 1.0}),
    'catch':    (gen_catch,    False, {'duration': 1.0}),
    'push':     (gen_push,     False, {'duration': 1.0}),
    'pull':     (gen_pull,     False, {'duration': 1.0}),

    # ── Combat (one-shot, except block which holds) ──
    'punch': (gen_punch, False, {'duration': 0.4}),
    'kick':  (gen_kick,  False, {'duration': 0.6}),
    'uppercut': (gen_uppercut, False, {'duration': 0.5}),
    'sweep': (gen_sweep, False, {'duration': 0.8}),
    'slam':  (gen_slam,  False, {'duration': 0.8}),
    'block': (gen_block, False, {'duration': 0.6}),
    'dodge': (gen_dodge, False, {'duration': 0.7}),
    'combo':  (gen_combo,  False, {'duration': 0.9}),
    'elbow_strike': (gen_elbow_strike, False, {'duration': 0.5}),
    'roundhouse_kick': (gen_roundhouse_kick, False, {'duration': 0.8}),

    # ── Cinematic poses (heroic / dramatic, loop for holds) ──
    'power_pose': (gen_pose_power, False, {'duration': 2.0}),
    'fist_pump':  (gen_fist_pump,  False, {'duration': 1.2}),
    'bow':        (gen_bow,        False, {'duration': 1.0}),
    'pointing':   (gen_pointing_finger, False, {'duration': 1.2}),
    'charge':     (gen_charge_energy,   False, {'duration': 1.2}),
    'leap':       (gen_leap,       False, {'duration': 0.7}),

    # ── Weapon handling (one-shot) ──
    'draw_weapon': (gen_draw_weapon, False, {'duration': 0.8}),
    'swing_sword': (gen_swing_sword, False, {'duration': 0.6}),
    'aim_gun':     (gen_aim_gun,     False, {'duration': 1.5}),
    'shoot':       (gen_shoot,       False, {'duration': 0.3}),
    'throw_shield':(gen_throw_shield, False, {'duration': 0.7}),
    'reload':      (gen_reload,      False, {'duration': 0.8}),

    # ── Dramatic / fall / recovery ──
    'collapse':    (gen_collapse,    False, {'duration': 1.2}),
    'get_back_up': (gen_get_back_up, False, {'duration': 1.2}),

    # ── Flight / superpower ──
    'fly':          (gen_fly,         False, {'duration': 2.0}),
    'hover':        (gen_hover,       False, {'duration': 2.0}),
    'land':         (gen_land,        False, {'duration': 0.6}),
    'energy_blast': (gen_energy_blast, False, {'duration': 0.8}),

    # ── Extra movement & expression ──
    'sprint':   (gen_sprint,   True,  {'speed': 2.5, 'stride': 95}),
    'backflip': (gen_backflip, False, {'duration': 1.0}),
    'dance':    (gen_dance,    False, {'duration': 3.0}),
    'celebrate':(gen_celebrate,False, {'duration': 2.0}),
    'tremble':  (gen_tremble,  False, {'duration': 2.0}),
    'crawl':    (gen_crawl,    False, {'duration': 1.5}),
    'look':     (gen_look,     False, {'duration': 1.5}),

    # ── Acrobatic movement ──
    'roll':  (gen_roll,  False, {'duration': 0.8}),
    'slide': (gen_slide, False, {'duration': 0.8}),

    # ── Emotions (loop) ──
    'happy':  (gen_happy,  False, {'duration': 2.0}),
    'sad':    (gen_sad,    False, {'duration': 2.0}),
    'angry':  (gen_angry,  False, {'duration': 2.0}),
    'scared': (gen_scared, False, {'duration': 2.0}),
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
        # Height-driven actions return (pose, y_offset); unwrap
        samples = [s[0] if isinstance(s, tuple) else s for s in samples]
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
