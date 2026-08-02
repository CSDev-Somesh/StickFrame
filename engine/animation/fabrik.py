"""FABRIK — Forward And Backward Reaching Inverse Kinematics

Pure 2D implementation. Solves bone chains (like arm or leg) to reach
a target point in space. No external dependencies beyond math.

Algorithm:
  1. FORWARD PASS: end effector → base
     Pull each joint toward target, constrained by bone length
  2. BACKWARD PASS: base → end effector  
     Push each joint back toward original position
  3. Iterate until end effector is close enough to target
"""

import math
from typing import List, Tuple, Optional


class FabrikChain:
    """A chain of rigid links solved with FABRIK IK.
    
    Usage:
        chain = FabrikChain()
        chain.add_bone(30.0)  # upper arm
        chain.add_bone(25.0)  # forearm
        chain.add_bone(10.0)  # hand
        
        chain.solve(target_x=20, target_y=-40)
        angles = chain.get_angles()  # [joint1_angle, joint2_angle, ...]
    """
    
    def __init__(self):
        self.bones: List[float] = []       # bone lengths
        self.joints: List[Tuple[float, float]] = []  # joint positions (computed)
        self.base_pos: Tuple[float, float] = (0.0, 0.0)
        self._initial_directions: List[float] = []  # rest angles
        self.total_length: float = 0.0
    
    def add_bone(self, length: float) -> int:
        """Add a bone to the chain. Returns bone index."""
        self.bones.append(length)
        self.total_length += length
        return len(self.bones) - 1
    
    def set_base(self, x: float, y: float) -> None:
        """Set the fixed base position of the chain."""
        self.base_pos = (x, y)
    
    def set_initial_pose(self, angles_deg: List[float]) -> None:
        """Set the rest pose angles (degrees) for each joint.
        
        The chain starts in this pose. FABRIK will move from here.
        """
        self._initial_directions = [math.radians(a) for a in angles_deg]
        self._compute_rest_pose()
    
    def _compute_rest_pose(self) -> None:
        """Compute joint positions from initial angles (forward kinematics)."""
        self.joints = [self.base_pos]
        cx, cy = self.base_pos
        for i, length in enumerate(self.bones):
            angle = self._initial_directions[i] if i < len(self._initial_directions) else 0.0
            cx += math.cos(angle) * length
            cy += math.sin(angle) * length
            self.joints.append((cx, cy))
    
    def solve(self, target_x: float, target_y: float, 
              tolerance: float = 0.5, max_iterations: int = 20) -> bool:
        """Run FABRIK to reach target.
        
        Args:
            target_x, target_y: Target position for end effector
            tolerance: Stop when end effector is within this distance
            max_iterations: Maximum FABRIK iterations
            
        Returns:
            True if target was reached within tolerance
        """
        if not self.bones:
            return False
        
        n = len(self.bones)  # number of bones
        n_joints = n + 1     # n bones = n+1 joints (including base)
        
        # Handle edge case: target at or very near base
        dx = target_x - self.base_pos[0]
        dy = target_y - self.base_pos[1]
        dist_to_target = math.sqrt(dx*dx + dy*dy)
        
        if dist_to_target < 0.01:
            # Target at base — fold all joints to base position
            self.joints = [self.base_pos] * n_joints
            return True
        
        # If target is unreachable, stretch toward it
        if dist_to_target > self.total_length:
            ratio = self.total_length / dist_to_target
            target_x = self.base_pos[0] + dx * ratio
            target_y = self.base_pos[1] + dy * ratio
        
        # Initialize joints if empty
        if not self.joints or len(self.joints) != n_joints:
            self.joints = [(self.base_pos[0], self.base_pos[1]) for _ in range(n_joints)]
            for i in range(1, n_joints):
                self.joints[i] = (self.base_pos[0] + 1, self.base_pos[1])  # tiny offset to avoid zero-vec
        
        target = (target_x, target_y)
        base = self.base_pos
        
        for iteration in range(max_iterations):
            # ── FORWARD PASS: end effector → base ──
            # Set end effector to target
            self.joints[-1] = target
            
            # Work backward from second-to-last joint to base
            for i in range(n - 1, -1, -1):
                # direction from joint[i] to joint[i+1]
                jx, jy = self.joints[i]
                nx, ny = self.joints[i + 1]
                dx = nx - jx
                dy = ny - jy
                dist = math.sqrt(dx*dx + dy*dy)
                if dist < 0.0001:
                    dist = 0.0001
                # Pull joint[i] toward joint[i+1], constrained by bone length
                ratio = self.bones[i] / dist
                self.joints[i] = (
                    nx - dx * ratio,
                    ny - dy * ratio
                )
            
            # ── BACKWARD PASS: base → end effector ──
            # Set base to fixed position
            self.joints[0] = base
            
            # Work forward from second joint to end effector
            for i in range(n):
                jx, jy = self.joints[i]
                nx, ny = self.joints[i + 1]
                dx = nx - jx
                dy = ny - jy
                dist = math.sqrt(dx*dx + dy*dy)
                if dist < 0.0001:
                    dist = 0.0001
                # Push joint[i+1] away from joint[i], constrained by bone length
                ratio = self.bones[i] / dist
                self.joints[i + 1] = (
                    jx + dx * ratio,
                    jy + dy * ratio
                )
            
            # Check convergence
            ex, ey = self.joints[-1]
            dx = ex - target_x
            dy = ey - target_y
            if math.sqrt(dx*dx + dy*dy) <= tolerance:
                return True
        
        return False
    
    def get_angles(self) -> List[float]:
        """Get joint angles in radians from the solved chain.
        
        Returns angles for each bone (relative to parent).
        First angle is absolute (relative to +x axis).
        """
        angles = []
        for i in range(len(self.bones)):
            jx, jy = self.joints[i]
            nx, ny = self.joints[i + 1]
            dx = nx - jx
            dy = ny - jy
            angles.append(math.atan2(dy, dx))
        return angles
    
    def get_angles_deg(self) -> List[float]:
        """Get joint angles in degrees."""
        return [math.degrees(a) for a in self.get_angles()]
    
    def get_end_effector(self) -> Tuple[float, float]:
        """Get the current end effector position."""
        if not self.joints:
            return self.base_pos
        return self.joints[-1]
    
    def reset(self) -> None:
        """Reset chain to rest pose."""
        self.joints = []
        if self._initial_directions:
            self._compute_rest_pose()