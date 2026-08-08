
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
    thickness: float = 1.0  # line-width multiplier (1.0 = base pen) —
    # enables tapered limbs: torso 1.0, thighs 0.9, upper arm 0.85,
    # forearm/lower leg 0.8, hands/feet 0.7 (visual hierarchy)

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
    head_color: str = "#FFD700"       # yellow head (unchanged)
    body_color: str = "#444444"       # fallback line color
    # Clothing / skin colors
    shirt_color: str = "#2E86DE"      # blue shirt on torso
    pants_color: str = "#1B2A4A"      # dark navy pants on legs
    shoe_color: str = "#8B4513"       # brown shoes on feet
    skin_color: str = "#FFDAB9"       # peach skin on neck, forearms, hands
    head_radius: float = 7.0
    limb_thickness: float = 2.0
    scale: float = 1.0
    # Part-visibility filter for the preview lab's part-by-part rig viewer.
    # None = render everything; a set like {"head","torso"} renders ONLY
    # those body parts (each bone maps to a part via BONE_PART in the
    # renderer). Defaults to None so the engine behaves exactly as before.
    visible_parts: Optional[set] = None


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
    params: Dict[str, Any] = field(default_factory=dict)
    # Position tracking
    position_offset_x: float = 0.0
    position_offset_y: float = 0.0
    _prev_offset_x: float = 0.0
    _prev_offset_y: float = 0.0
    # Action blending
    blend_from_pose: Optional[Dict[str, float]] = None
    blend_timer: float = 0.0
    blend_duration: float = 0.12
    _prev_frame_pose: Optional[Dict[str, float]] = None
    # Delayed physics impulse (jump anticipation): the velocity fires when
    # player.time crosses impulse_time, so the crouch pose reads BEFORE the
    # body launches. Without this, the body lifts while the pose is still
    # crouching and the anticipation is lost.
    impulse_vy: float = 0.0
    impulse_time: float = 0.0
    impulse_fired: bool = False
    # Height-driven actions (sit/lie/kneel family): the generator returns
    # (pose, y_offset) — total hips descent from the height the action
    # STARTED at. _height_base is captured on the first processed frame so
    # chained actions (sit → stand_up) continue from the current height.
    _height_base: Optional[float] = None
    _height_offset: Optional[float] = None
    # Velocity-driven movement (walk/run/sprint toward an x= target): when
    # True, the generator's own X position offset is suppressed so the
    # character doesn't double-move (velocity + generator stride). The Y
    # bob is kept for life. Set/cleared by the timeline movement handler.
    velocity_move: bool = False


# ─── Physics Components ──────────────────────────────────────

@dataclass
class PhysicsBody:
    mass: float = 1.0
    gravity_scale: float = 1.0
    is_static: bool = False
    restitution: float = 0.3  # bounciness
    friction: float = 0.5
    ground_offset: float = 0.0  # feet distance below entity origin (hips) — used by ground collision
    rest_ground_offset: float = 0.0  # standing ground_offset (rest pose) — restored when a height-driven action ends

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
    """Camera/viewport definition with smooth follow, shake, and zoom animation."""
    target_entity: Optional[int] = None  # entity to follow
    zoom: float = 1.0
    rotation: float = 0.0
    shake_intensity: float = 0.0
    shake_duration: float = 0.0
    shake_timer: float = 0.0
    # Smooth follow
    smooth_speed: float = 5.0      # higher = snappier follow (0 = instant)
    current_x: float = 0.0         # actual camera position for lerp
    current_y: float = 0.0
    # Per-axis follow toggles — e.g. side-scroller: follow_x=True, follow_y=False
    # (camera y pinned to current_y so the character stays grounded on a fixed floor)
    follow_x: bool = True
    follow_y: bool = True
    # Zoom bounds
    min_zoom: float = 0.3
    max_zoom: float = 3.0
    # Animated zoom
    target_zoom: Optional[float] = None  # None = use zoom directly
    # Smooth pan targets — when set, the camera lerps toward them instead of
    # following an entity. Cleared when a follow target is set or reset() runs.
    pan_target_x: Optional[float] = None
    pan_target_y: Optional[float] = None
    # Multi-camera
    active: bool = True


# ─── Dialogue Component ──────────────────────────────────────

@dataclass
class DialogueState:
    active_text: str = ""
    bubble_style: str = "rounded"
    progress: float = 0.0


@dataclass
class Facing:
    """Character facing direction — controls horizontal mirroring at render time."""
    direction: str = 'right'  # 'left' or 'right'


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
    'DialogueState', 'Facing',
    'SceneNode',
    'TimelineEvent', 'TimelineTrack',
    'AIComponent',
]
