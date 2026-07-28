"""StickFrame Engine — Core ECS Components

All component data structures for the Entity-Component-System.
Components are plain data containers (dataclasses) with no logic.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


# ─── Spatial Components ───────────────────────────────────────

@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0

@dataclass
class Velocity:
    vx: float = 0.0
    vy: float = 0.0

@dataclass
class Transform:
    """Local transform relative to parent. Rotation in radians."""
    parent: Optional[int] = None  # entity ID
    local_x: float = 0.0
    local_y: float = 0.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0


# ─── Skeletal & Appearance Components ─────────────────────────

@dataclass
class BoneDef:
    """Definition of a single bone in the skeleton"""
    name: str
    length: float          # pixels
    parent_index: int = -1  # index into skeleton's bone list, -1 = root
    default_angle: float = 0.0  # radians, relative to parent

@dataclass
class Skeleton:
    """Bone hierarchy definition. Bones are indexed by position in list."""
    bones: List[BoneDef] = field(default_factory=list)
    # Per-frame computed world angles (radians)
    world_angles: List[float] = field(default_factory=list)
    # Per-frame computed world tip positions (pixels)
    world_positions: List[tuple] = field(default_factory=list)

@dataclass
class Appearance:
    head_color: str = "#FFD700"
    body_color: str = "#333333"
    head_radius: float = 12.0
    limb_thickness: float = 3.0
    scale: float = 1.0


# ─── Animation Components ─────────────────────────────────────

@dataclass
class Keyframe:
    """A single keyframe for a bone property"""
    time: float          # seconds
    angle: float         # radians

@dataclass
class ActionClip:
    """A named animation clip — sequence of keyframes per bone"""
    name: str
    duration: float                        # total duration in seconds
    bone_keyframes: Dict[str, List[Keyframe]] = field(default_factory=dict)  # bone_name -> keyframes
    loop: bool = False
    # Position offset keyframes for moving the entire character through space
    position_keyframes: Dict[str, List[Keyframe]] = field(default_factory=dict)  # 'x' or 'y' -> keyframes

@dataclass
class AnimationPlayer:
    """Runtime state for playing animation clips (keyframe-based)"""
    current_action: Optional[str] = None   # name of current clip
    clips: Dict[str, ActionClip] = field(default_factory=dict)
    time: float = 0.0
    speed: float = 1.0
    playing: bool = False
    loop: bool = True
    blend_from: Optional[str] = None       # crossfade source
    blend_time: float = 0.0
    blend_duration: float = 0.15
    # Accumulated position offset from action position_keyframes
    position_offset_x: float = 0.0
    position_offset_y: float = 0.0
    # Track previous frame's position keyframe value to compute delta
    _prev_pos_x: float = 0.0
    _prev_pos_y: float = 0.0
    # Per-cycle offset for looping clips
    _cycle_pos_x: float = 0.0
    _cycle_pos_y: float = 0.0
    _last_cycle_start: float = 0.0


@dataclass
class ProceduralPlayer:
    """Runtime state for playing procedural animation generators.
    
    Unlike AnimationPlayer (keyframe-based), this uses math generators
    that produce bone angles on the fly from parameters.
    """
    current_action: Optional[str] = None
    time: float = 0.0
    speed: float = 1.0
    playing: bool = False
    loop: bool = True
    params: Dict[str, Any] = field(default_factory=dict)  # generator parameters
    # Position tracking for generators that move the character
    position_offset_x: float = 0.0
    position_offset_y: float = 0.0
    _prev_offset_x: float = 0.0
    _prev_offset_y: float = 0.0


# ─── Physics Components ──────────────────────────────────────

@dataclass
class PhysicsBody:
    mass: float = 1.0
    gravity_scale: float = 1.0
    is_static: bool = False
    restitution: float = 0.3  # bounciness
    friction: float = 0.5

@dataclass
class Collider:
    """Simple AABB or circle collider"""
    shape: str = "circle"  # "circle" or "aabb"
    radius: float = 10.0   # for circle
    width: float = 20.0    # for aabb
    height: float = 40.0   # for aabb


# ─── Rendering Components ────────────────────────────────────

@dataclass
class Renderable:
    """Marks entity as visible"""
    visible: bool = True
    z_order: int = 0
    draw_commands: List[Dict] = field(default_factory=list)

@dataclass
class Camera:
    """Camera/viewport definition"""
    target_entity: Optional[int] = None  # entity to follow
    zoom: float = 1.0
    rotation: float = 0.0
    shake_intensity: float = 0.0
    shake_duration: float = 0.0
    shake_timer: float = 0.0


# ─── Dialogue Component ──────────────────────────────────────

@dataclass
class DialogueState:
    active_text: str = ""
    bubble_style: str = "rounded"
    progress: float = 0.0


# ─── Scene Graph Component ───────────────────────────────────

@dataclass
class SceneNode:
    """A node in the scene graph hierarchy"""
    parent: Optional[int] = None
    children: List[int] = field(default_factory=list)
    name: str = ""


# ─── Timeline Component ──────────────────────────────────────

@dataclass
class TimelineEvent:
    time: float
    action: str          # "entity.action" format
    params: Dict[str, Any] = field(default_factory=dict)
    fired: bool = False

@dataclass
class TimelineTrack:
    name: str
    events: List[TimelineEvent] = field(default_factory=list)
    current_index: int = 0


# ─── AI / Director Components ────────────────────────────────

@dataclass
class AIComponent:
    behavior_tree: str = ""
    state: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    'Position', 'Velocity', 'Transform',
    'BoneDef', 'Skeleton', 'Appearance',
    'Keyframe', 'ActionClip', 'AnimationPlayer',
    'PhysicsBody', 'Collider',
    'Renderable', 'Camera',
    'DialogueState',
    'SceneNode',
    'TimelineEvent', 'TimelineTrack',
    'AIComponent',
]
