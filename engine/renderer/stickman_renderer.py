"""Stickman renderer — draws stick figures with visible joint nodes like Pivot Animator"""

from typing import List, Tuple, Optional
from PIL import Image, ImageDraw

from engine.core.components import Skeleton, Appearance, Position
from engine.animation.skeleton import get_all_bone_segments


# Pivot-style color palette
JOINT_FILL = "#FFFFFF"      # white center
JOINT_OUTLINE = "#222222"   # dark outline
BONE_COLOR = "#222222"
HEAD_FILL = "#FFD700"
HEAD_OUTLINE = "#222222"


def get_joint_positions(skeleton: Skeleton, ox: float, oy: float) -> List[Tuple[float, float, str]]:
    """Get all joint positions with labels for Pivot-style rendering.
    
    Returns list of (x, y, label) for each joint.
    Joint = where bones connect (parent tip = child base).
    """
    joints = []
    n = len(skeleton.bones)
    
    # Root joint (hips) at entity position
    joints.append((ox, oy, "hips"))
    
    for i, bone in enumerate(skeleton.bones):
        tx = ox + skeleton.world_positions[i][0]
        ty = oy + skeleton.world_positions[i][1]
        joints.append((tx, ty, bone.name))
    
    return joints


def draw_stickman(
    draw: ImageDraw.ImageDraw,
    skeleton: Skeleton,
    appearance: Appearance,
    position: Position,
    head_color: Optional[str] = None,
    body_color: Optional[str] = None,
    show_joints: bool = True,
) -> None:
    """Render a stickman with visible pivot nodes (Pivot Animator style).
    
    Args:
        draw: Pillow ImageDraw instance
        skeleton: Computed skeleton with world positions
        appearance: Character appearance
        position: Entity position
        head_color: Override head color
        body_color: Override body/line color
        show_joints: Draw filled circles at each joint
    """
    ox, oy = position.x, position.y
    bc = body_color or appearance.body_color or BONE_COLOR
    hc = head_color or appearance.head_color or HEAD_FILL
    lt = max(2, int(appearance.limb_thickness))
    s = appearance.scale
    
    # 1. Draw bone segments (limbs as lines)
    segments = get_all_bone_segments(skeleton)
    for base, tip in segments:
        x1 = ox + base[0]
        y1 = oy + base[1]
        x2 = ox + tip[0]
        y2 = oy + tip[1]
        draw.line([x1, y1, x2, y2], fill=bc, width=lt)
    
    # 2. Draw joint dots (Pivot Animator style)
    if show_joints:
        joints = get_joint_positions(skeleton, ox, oy)
        for jx, jy, label in joints:
            # Different sizes for different joint types
            if label == "head":
                hr = appearance.head_radius * s
                draw.ellipse([jx - hr, jy - hr, jx + hr, jy + hr],
                             fill=hc, outline=HEAD_OUTLINE, width=2)
                continue
            elif label == "hips":
                r = 5 * s
            elif label in ("neck", "spine"):
                r = 3 * s
            elif "hand" in label or "foot" in label:
                r = 3 * s
            else:
                r = 4 * s  # elbows, knees, shoulders
            
            draw.ellipse([jx - r, jy - r, jx + r, jy + r],
                         fill=JOINT_FILL, outline=JOINT_OUTLINE, width=1)
    
    # 3. Draw head if not already done by joint rendering
    if not show_joints:
        # Find head bone position from skeleton
        for i, bone in enumerate(skeleton.bones):
            if bone.name == "head":
                hx = ox + skeleton.world_positions[i][0]
                hy = oy + skeleton.world_positions[i][1]
                hr = appearance.head_radius * s
                draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr],
                             fill=hc, outline=HEAD_OUTLINE, width=2)
                break


def render_scene(
    entities: List[Tuple],
    width: int = 1280,
    height: int = 720,
    bg_color: str = "#FFFFFF",
) -> Image.Image:
    """Render all entities in the scene.
    
    Args:
        entities: List of (position, skeleton, appearance) tuples
        width: Output width
        height: Output height
        bg_color: Background color (white for Pivot-style)
        
    Returns:
        PIL Image
    """
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    for item in entities:
        if len(item) >= 3:
            pos, skel, app = item[0], item[1], item[2]
            draw_stickman(draw, skel, app, pos)
    
    return img
