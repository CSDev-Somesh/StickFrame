"""Stickman renderer — draws stick figures using Pillow"""

from typing import List, Tuple, Optional
from PIL import Image, ImageDraw

from engine.core.components import Skeleton, Appearance, Position
from engine.animation.skeleton import get_all_bone_segments


def draw_stickman(
    draw: ImageDraw.ImageDraw,
    skeleton: Skeleton,
    appearance: Appearance,
    position: Position,
    head_color: Optional[str] = None,
    body_color: Optional[str] = None,
) -> None:
    """Render a stickman from its skeleton and appearance at the given position.
    
    Args:
        draw: Pillow ImageDraw instance
        skeleton: Computed skeleton with world positions
        appearance: Character appearance data
        position: World position offset
        head_color: Override for head color
        body_color: Override for body color
    """
    s = appearance.scale
    ox, oy = position.x, position.y
    hc = head_color or appearance.head_color
    bc = body_color or appearance.body_color
    lt = int(appearance.limb_thickness * s)
    
    # Draw bone segments (limbs)
    segments = get_all_bone_segments(skeleton)
    for base, tip in segments:
        x1 = ox + base[0]
        y1 = oy + base[1]
        x2 = ox + tip[0]
        y2 = oy + tip[1]
        draw.line([x1, y1, x2, y2], fill=bc, width=max(1, lt))
    
    # Draw head (circle on top of neck)
    # Find head bone position
    head_world = None
    neck_world = None
    for i, bone in enumerate(skeleton.bones):
        if bone.name == "head":
            head_world = skeleton.world_positions[i]
        if bone.name == "neck":
            neck_world = skeleton.world_positions[i]
    
    if head_world and neck_world:
        # Head is at neck tip, radius from appearance
        hx = ox + head_world[0]
        hy = oy + head_world[1]
        hr = appearance.head_radius * s
        # Also draw neck connection
        nx = ox + neck_world[0]
        ny = oy + neck_world[1]
        draw.line([nx, ny, hx, hy], fill=bc, width=max(1, lt))
        draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=hc, outline=bc, width=2)
    elif skeleton.bones:
        # Fallback: head is above first bone
        hx = ox
        hy = oy - 20 * s
        hr = appearance.head_radius * s
        draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=hc, outline=bc, width=2)


def render_scene(
    entities: List[Tuple],
    width: int = 1280,
    height: int = 720,
    bg_color: str = "#87CEEB",
) -> Image.Image:
    """Render all entities in the scene to a Pillow image.
    
    Args:
        entities: List of (position, skeleton, appearance) tuples
        width: Output width in pixels
        height: Output height in pixels
        bg_color: Background color
        
    Returns:
        Pillow Image
    """
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Sort by z-order (for now, just render in order)
    for item in entities:
        if len(item) >= 3:
            pos, skel, app = item[0], item[1], item[2]
            draw_stickman(draw, skel, app, pos)
    
    return img
