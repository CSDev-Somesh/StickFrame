"""Procedural walk generator — sine-wave based gait with IK foot placement

No keyframes. The walk is generated from parameters:
  - speed: steps per second
  - stride: step length in pixels
  - step_height: how high feet lift
  - bounce: body vertical bob amplitude

Each frame, the generator:
  1. Computes leg swing angles from sine waves
  2. Determines foot target positions on the ground
  3. Solves IK to place feet at those positions
  4. Computes arm swing (opposite phase)
  5. Computes body bob and lean
"""

import math
from typing import List, Tuple, Optional, Dict

from engine.animation.fabrik import FabrikChain
from engine.core.components import Skeleton, BoneDef


class WalkGenerator:
    """Procedural walk cycle generator.
    
    Usage:
        gen = WalkGenerator(leg_chain, arm_chain)
        pose = gen.sample(time=2.5, speed=1.2, stride=60)
        # pose contains bone angles for every bone in the skeleton
    """
    
    def __init__(self, skeleton: Skeleton):
        self.skeleton = skeleton
        # Build IK chains for each limb
        self._build_chains()
    
    def _build_chains(self) -> None:
        """Build FABRIK chains for left and right legs."""
        bones = self.skeleton.bones
        
        # Left leg: hip → knee → ankle → foot
        self.left_leg = FabrikChain()
        left_leg_indices = self._get_chain_indices(
            "left_upper_leg", "left_lower_leg", "left_foot")
        for idx in left_leg_indices:
            self.left_leg.add_bone(bones[idx].length)
        
        # Right leg
        self.right_leg = FabrikChain()
        right_leg_indices = self._get_chain_indices(
            "right_upper_leg", "right_lower_leg", "right_foot")
        for idx in right_leg_indices:
            self.right_leg.add_bone(bones[idx].length)
        
        # Left arm: shoulder → elbow → hand
        self.left_arm = FabrikChain()
        left_arm_indices = self._get_chain_indices(
            "left_upper_arm", "left_forearm", "left_hand")
        for idx in left_arm_indices:
            self.left_arm.add_bone(bones[idx].length)
        
        # Right arm
        self.right_arm = FabrikChain()
        right_arm_indices = self._get_chain_indices(
            "right_upper_arm", "right_forearm", "right_hand")
        for idx in right_arm_indices:
            self.right_arm.add_bone(bones[idx].length)
    
    def _get_chain_indices(self, *bone_names: str) -> List[int]:
        """Get bone indices for a chain of bone names."""
        name_to_idx = {b.name: i for i, b in enumerate(self.skeleton.bones)}
        return [name_to_idx[n] for n in bone_names]
    
    def sample(self, time: float, speed: float = 1.0, stride: float = 60.0,
               step_height: float = 15.0, bounce: float = 4.0) -> Dict[str, float]:
        """Sample walk pose at a given time.
        
        Args:
            time: Current time in seconds (walk cycles at ~1.25 steps/sec per leg)
            speed: Speed multiplier (1.0 = normal)
            stride: Step length in pixels
            step_height: How high feet lift mid-step
            bounce: Body vertical bob amplitude
            
        Returns:
            Dict of bone_name -> angle (radians) for every bone
        """
        # Time scales: each leg completes one full step cycle per unit time
        t = time * speed
        
        # ── Leg swing (sine wave, legs are opposite phase) ──
        # Left leg phase: sin(t*π) → forward at t=0, back at t=1
        # Right leg phase: sin(t*π + π) → opposite
        left_swing = math.sin(t * math.pi)
        right_swing = math.sin(t * math.pi + math.pi)
        
        # Leg angle from vertical (convert swing [-1,1] to angle [30° forward, -30° back])
        max_leg_angle = math.radians(30)  # 30° max swing
        left_leg_angle = left_swing * max_leg_angle
        right_leg_angle = right_swing * max_leg_angle
        
        # ── Foot lift (sine wave, lifts when leg is at max swing) ──
        # Lift happens at midpoint of swing (when swing crosses 0 going forward)
        left_lift = abs(math.sin(t * math.pi)) * step_height
        right_lift = abs(math.sin(t * math.pi + math.pi)) * step_height
        
        # ── Body bob ──
        body_bob = math.sin(t * math.pi * 2) * bounce
        
        # ── Forward movement offset ──
        # Character moves forward at constant rate
        forward_offset = time * speed * stride * 0.8  # 0.8 steps/sec normalization
        
        # ── Build pose dict ──
        pose = {}
        
        # Spine: slight lean forward with bob
        pose['spine'] = math.radians(-88) + math.sin(t * math.pi * 2) * math.radians(2)
        pose['neck'] = 0.0
        pose['head'] = 0.0
        
        # Arms: swing opposite to legs
        # Arm base angle (hanging down): ~180° relative to spine
        arm_swing = max_leg_angle * 0.6  # arms swing less than legs
        pose['left_upper_arm'] = math.radians(185) - left_swing * arm_swing
        pose['left_forearm'] = math.radians(10) + left_swing * math.radians(10)
        pose['left_hand'] = 0.0
        pose['right_upper_arm'] = math.radians(175) - right_swing * arm_swing
        pose['right_forearm'] = math.radians(-10) + right_swing * math.radians(10)
        pose['right_hand'] = 0.0
        
        # Legs
        pose['left_upper_leg'] = math.radians(90) + left_leg_angle
        pose['left_lower_leg'] = -left_leg_angle * 0.5  # knee bends naturally
        pose['left_foot'] = 0.0
        pose['right_upper_leg'] = math.radians(90) + right_leg_angle
        pose['right_lower_leg'] = -right_leg_angle * 0.5
        pose['right_foot'] = 0.0
        
        # Hips (invisible pivot, keep at 0)
        pose['hips'] = 0.0
        
        return pose, forward_offset, body_bob
    
    def compute_foot_ik(self, time: float, speed: float = 1.0, 
                         stride: float = 60.0, step_height: float = 15.0,
                         hip_x: float = 0, hip_y: float = 0) -> Dict[str, float]:
        """Compute bone angles using IK for precise foot placement.
        
        This is more accurate than sine-wave only—feet actually land
        at specific ground positions.
        
        Returns:
            Dict of bone_name -> angle for leg bones
        """
        t = time * speed
        results = {}
        
        # For each leg: compute foot target position on ground
        for leg_chain, leg_name, side_mult in [
            (self.left_leg, "left", -1),
            (self.right_leg, "right", 1)
        ]:
            # Foot ground position: moves forward with body + stride oscillation
            base_foot_x = hip_x + time * speed * stride * 0.8 + side_mult * 8
            foot_target_x = base_foot_x + math.sin(t * math.pi + (0 if side_mult < 0 else math.pi)) * stride * 0.5
            
            # Foot Y: on ground, with lift during swing
            foot_lift = abs(math.sin(t * math.pi + (0 if side_mult < 0 else math.pi))) * step_height
            foot_target_y = hip_y + 40 + 16 - foot_lift  # ~40px down to ground
            
            # Solve IK
            leg_chain.set_base(hip_x, hip_y)
            leg_chain.solve(foot_target_x, foot_target_y, tolerance=1.0)
            angles = leg_chain.get_angles()
            
            # Map chain angles back to bone names
            upper_name = f"{leg_name}_upper_leg"
            lower_name = f"{leg_name}_lower_leg" 
            foot_name = f"{leg_name}_foot"
            
            if len(angles) >= 1:
                results[upper_name] = angles[0]
            if len(angles) >= 2:
                results[lower_name] = angles[1]
            if len(angles) >= 3:
                results[foot_name] = angles[2]
        
        return results


def apply_procedural_pose(skeleton: Skeleton, pose: Dict[str, float]) -> None:
    """Apply a procedural pose dict to a skeleton.
    
    Sets bone.default_angle for each bone that has a value in pose.
    """
    for i, bone in enumerate(skeleton.bones):
        if bone.name in pose:
            skeleton.bones[i].default_angle = pose[bone.name]