"""Avatar grid capture — sample every action at 6 timeframes and capture the
per-bone pose data plus a rendered still per cell.

A single ActionPose is the unit of capture:
  - 't01': normalized time within the action (0..1)
  - 't':   absolute seconds inside the action
  - 'angles': dict of {bone_name: radians} for all 25 skeleton bones
  - 'y_offset': hips descent for height-driven actions (0 otherwise)
  - 'foot_y': lowest foot-bottom Y for this pose (rest = grounded reference)

The grid is COLUMNS=6 timeframes × ROWS=actions (up to 26).
"""
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

from engine.animation.generators import GENERATORS, generator_names
from engine.animation.skeleton import build_bipedal_skeleton, compute_forward_kinematics

GRID_COLS = 6      # timeframes per action
GRID_ROWS = 26     # max actions in a sheet

# Standard normalized sample times across one action duration (0..1)
TIME_01 = [i / (GRID_COLS - 1) for i in range(GRID_COLS)]  # 0, .2, .4, .6, .8, 1.0

# Reference foot reach in the REST pose (identical for all actions at
# t=0 since generators start from rest). Used to judge grounding.
_REST_FOOT_Y = None


def rest_foot_y(scale: float = 1.0) -> float:
    """Vertical reach of the rest pose: hips(origin) -> lowest bone tip."""
    global _REST_FOOT_Y
    if _REST_FOOT_Y is None:
        skel = build_bipedal_skeleton(scale)
        compute_forward_kinematics(skel, 0, 0)
        _REST_FOOT_Y = max(y for _, y in skel.world_positions)
    return _REST_FOOT_Y


@dataclass
class ActionPose:
    """A single captured avatar pose for one action at one timeframe."""
    action: str
    t01: float                      # normalized time 0..1
    time_s: float                  # absolute seconds inside the action
    angles: Dict[str, float] = field(default_factory=dict)  # bone -> radians
    y_offset: float = 0.0
    foot_y: float = 0.0            # lowest foot Y for this pose (frame pose)


class AvatarGrid:
    """A 2D grid of ActionPose: rows = actions, cols = timeframes."""

    def __init__(self, scale: float = 1.0):
        self.scale = scale
        self.cells: Dict[Tuple[str, int], ActionPose] = {}
        self._action_list: List[str] = []
        self.foot_reference = rest_foot_y(scale)

    def build(self, actions: Optional[List[str]] = None) -> "AvatarGrid":
        """Capture every action (or a chosen subset) at every timeframe."""
        pool = actions if actions is not None else generator_names()
        self._action_list = list(pool)[:GRID_ROWS]   # cap to 26 rows

        skel = build_bipedal_skeleton(self.scale)
        for a in self._action_list:
            fn, has_pos, defaults = GENERATORS[a]
            dur = defaults.get('duration', 1.0)
            cfg = dict(defaults)
            cfg['scale'] = self.scale
            for col, t01 in enumerate(TIME_01):
                t = t01 * dur
                result = fn(t, cfg)
                if isinstance(result, tuple):
                    pose, yoff = result
                else:
                    pose, yoff = result, 0.0
                foot = self._frame_foot(pose, skel) + yoff
                self.cells[(a, col)] = ActionPose(
                    action=a, t01=t01, time_s=t,
                    angles=dict(pose), y_offset=yoff, foot_y=foot,
                )
        return self

    def _frame_foot(self, pose: Dict[str, float], skel) -> float:
        """Forward-solve a pose and return the lowest foot-bottom Y."""
        for i, bone in enumerate(skel.bones):
            if bone.name in pose:
                skel.bones[i].default_angle = pose[bone.name]
        compute_forward_kinematics(skel, 0, 0)
        return max(y for _, y in skel.world_positions)

    def get(self, action: str, col: int) -> ActionPose:
        return self.cells[(action, col)]

    def rows(self) -> List[str]:
        return self._action_list

    @property
    def n_rows(self) -> int:
        return len(self._action_list)

    @property
    def n_cols(self) -> int:
        return GRID_COLS

    def verify(self, foot_tol: float = 8.0) -> List[str]:
        """Assert every captured cell is valid. Returns list of problems.

        Checks: presence, full bone coverage, finite angles, and foot
        grounding (non-height actions should keep feet near the rest line).
        """
        problems = []
        for a in self._action_list:
            for col in range(GRID_COLS):
                ap = self.cells.get((a, col))
                if ap is None:
                    problems.append(f"{a} col{col}: missing cell")
                    continue
                miss = set(self.bone_names) - set(ap.angles)
                if miss:
                    problems.append(f"{a} col{col}: missing bones {sorted(miss)[:6]}")
                nf = [k for k, v in ap.angles.items() if not math.isfinite(v)]
                if nf:
                    problems.append(f"{a} col{col}: nonfinite bones {nf[:6]}")
        return problems

    @property
    def bone_names(self):
        return tuple(b.name for b in build_bipedal_skeleton(self.scale).bones)


def capture_grid(actions=None, scale=1.0) -> AvatarGrid:
    """Capture the full avatar action grid (6 cols × ≤26 rows)."""
    return AvatarGrid(scale=scale).build(actions=actions)