"""Stickman renderer — draws stick figures with visible joint nodes like Pivot Animator"""

from typing import List, Tuple, Optional
from PIL import Image, ImageDraw

from engine.core.components import Skeleton, Appearance, Position
from engine.animation.skeleton import get_all_bone_segments


# Pivot-style color palette
JOINT_FILL = "#FF3333"      # red fill — design aid: joints clearly visible
JOINT_OUTLINE = "#990000"   # darker red outline
BONE_COLOR = "#222222"
HEAD_FILL = "#FFD700"
HEAD_OUTLINE = "#222222"

# Clothes / skin color per body-part group — mapped to Appearance fields.
# This is the "outfit" — torso gets shirt, legs get pants, feet get shoes,
# neck + forearms + hands get skin tone. Head stays yellow (separate).
BONE_COLOR_MAP = {
    "head":     "head_color",      # yellow head circle
    "torso":    "shirt_color",      # blue shirt on torso/spine
    "arms":     "skin_color",        # peach skin on all arm bones
    "legs":     "pants_color",       # navy pants on legs
}
# Feet override: within "legs" group, foot bones get shoe color
FOOT_BONES = {"left_foot", "right_foot"}

# Joint radii — Pivot-style small dots (absolute px, don't scale with figure
# size — dots stay small clean dots at any scale, like a pen drawing)
HIP_RADIUS = 3.5
KNEE_ELBOW_RADIUS = 3.0     # elbows, knees, shoulders
HAND_FOOT_RADIUS = 2.5
NECK_SPINE_RADIUS = 2.0

# Body-part grouping for the part-by-part rig viewer.
# Every bone belongs to exactly one part; the preview lab can render only
# a subset (e.g. {"head", "legs"}) by setting Appearance.visible_parts.
BONE_PART = {
    # head
    "head": "head",
    # torso — spine chain + chest + neck (+ hips root)
    "spine": "torso", "chest": "torso", "neck": "torso", "hips": "torso",
    # arms — shoulders + arms + wrists + hands
    "left_shoulder": "arms", "left_upper_arm": "arms", "left_forearm": "arms",
    "left_wrist": "arms", "left_hand": "arms",
    "right_shoulder": "arms", "right_upper_arm": "arms", "right_forearm": "arms",
    "right_wrist": "arms", "right_hand": "arms",
    # legs — hips + legs + ankles + feet
    "left_hip": "legs", "left_upper_leg": "legs", "left_lower_leg": "legs",
    "left_ankle": "legs", "left_foot": "legs",
    "right_hip": "legs", "right_upper_leg": "legs", "right_lower_leg": "legs",
    "right_ankle": "legs", "right_foot": "legs",
}


# Joint dots that should NOT be drawn even though the bone exists.
# Design decisions (Somesh, rig review):
#  - legs keep only KNEE + ANKLE + FOOT dots — hip dots and the redundant
#    lower-leg dot are removed for a cleaner silhouette (bones still animate)
#  - "chest" tip dot is hidden: the CHEST JOINT is the spine-tip dot in the
#    middle of the torso (between hips and neck); the chest-bone tip sits
#    right at the neck base and would bunch with the neck dot
#  - arms keep SHOULDER + ELBOW + WRIST + HAND dots (user: "where are the
#    dots of shoulders and elbow keep them") — only the redundant
#    forearm-tip dot is hidden (it overlaps the wrist joint dot)
NO_DOT = {
    "left_hip", "right_hip",
    "left_lower_leg", "right_lower_leg",
    "chest",
    "left_forearm", "right_forearm",
}


def bone_visible(bone_name: str, visible_parts) -> bool:
    """True if this bone's body part is in the visible set (None = all)."""
    if visible_parts is None:
        return True
    part = BONE_PART.get(bone_name)
    return part is not None and part in visible_parts


def get_joint_positions(skeleton: Skeleton, ox: float, oy: float) -> List[Tuple[float, float, str]]:
    """Get all joint positions with labels for Pivot-style rendering.

    Returns list of (x, y, label) for each joint.
    Joints are at bone tips and connection points.
    """
    joints = []

    # Root joint (hips) — use FK world position, not passed ox/oy (already in world space)
    if len(skeleton.bones) > 0:
        joints.append((skeleton.world_positions[0][0], skeleton.world_positions[0][1], "hips"))

    for i, bone in enumerate(skeleton.bones):
        if bone.length <= 0:
            continue  # skip zero-length bones (hips is already added)
        tx = skeleton.world_positions[i][0]
        ty = skeleton.world_positions[i][1]
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
    viewport_offset: tuple = (0, 0),
    zoom: float = 1.0,
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
        viewport_offset: (offset_x, offset_y) for camera transform
        zoom: Viewport zoom factor
    """
    ox, oy = position.x, position.y
    bc = body_color or appearance.body_color or BONE_COLOR
    hc = head_color or appearance.head_color or HEAD_FILL
    s = appearance.scale
    # Limb pen width scales WITH the figure so limbs stay human-proportioned
    # (≈0.35× head radius) at every scale — previously fixed 2px, which made
    # the stickman look like toothpicks when scaled up. Capped to keep it
    # bold but not bloated.
    pen = max(2, int(0.35 * appearance.head_radius * s * zoom))
    lt = pen
    vis_parts = getattr(appearance, "visible_parts", None)

    def bone_color(app: Appearance, bone_name: str) -> str:
        """Pick the right outfit color for a bone."""
        # Find the body part group this bone belongs to
        part = BONE_PART.get(bone_name, "torso")
        # Feet override: within "legs" group, foot bones get shoe color
        if bone_name in FOOT_BONES:
            color_attr = "shoe_color"
        else:
            color_attr = BONE_COLOR_MAP.get(part, "shirt_color")
        # Resolve from Appearance; fall back to body_color
        return getattr(app, color_attr, None) or app.body_color or BONE_COLOR

    vx, vy = viewport_offset

    def vp(x: float, y: float) -> Tuple[float, float]:
        """Apply viewport transform to world coordinates."""
        return (x * zoom + vx, y * zoom + vy)

    # 1. Draw bone segments (limbs as lines) — pen strokes scale with the
    #    figure (human-proportioned), tapered per bone via BoneDef.thickness
    #    so the silhouette has hierarchy: torso thickest, limbs thinner.
    for i, bone in enumerate(skeleton.bones):
        if bone.length <= 0:
            continue
        if not bone_visible(bone.name, vis_parts):
            continue
        base = skeleton.world_positions[bone.parent_index] if bone.parent_index >= 0 else (0.0, 0.0)
        tip = skeleton.world_positions[i]
        sx, sy = vp(base[0], base[1])
        tx, ty = vp(tip[0], tip[1])
        w = max(1, int(lt * zoom * getattr(bone, "thickness", 1.0)))
        # joint="curve" rounds the join between connected limb segments —
        # keeps intersections clean when limbs cross during fast action
        # (director review: thick lines can merge into one dark shape)
        draw.line([sx, sy, tx, ty], fill=bone_color(appearance, bone.name), width=w, joint="curve")

    # 2. Draw torso fill (shirt) — egg/tapered shape: wide at chest, narrow at waist
    #    Draw AFTER bone lines so it visually covers shoulder connections
    if bone_visible("torso", vis_parts):
        # Find key torso joints in world space
        # hips (root), spine base, chest (top of torso), neck base
        torso_points = []
        # hips center (average of left/right hip positions)
        left_hip_i = next((i for i, b in enumerate(skeleton.bones) if b.name == "left_hip"), None)
        right_hip_i = next((i for i, b in enumerate(skeleton.bones) if b.name == "right_hip"), None)
        if left_hip_i is not None and right_hip_i is not None:
            lh = skeleton.world_positions[left_hip_i]
            rh = skeleton.world_positions[right_hip_i]
            hips_cx = (lh[0] + rh[0]) / 2
            hips_cy = (lh[1] + rh[1]) / 2
        else:
            # fallback: first bone root
            hips_cx, hips_cy = skeleton.world_positions[0] if skeleton.bones else (0, 0)
        
        # spine base (spine bone)
        spine_i = next((i for i, b in enumerate(skeleton.bones) if b.name == "spine"), None)
        # chest (top of shirt)
        chest_i = next((i for i, b in enumerate(skeleton.bones) if b.name == "chest"), None)
        # neck base (where neck starts)
        neck_i = next((i for i, b in enumerate(skeleton.bones) if b.name == "neck"), None)
        
        # Build egg shape: wide at chest (shoulder-width), narrow at waist (NOT hips — pants start there)
        # Width multipliers at each level (relative to head_radius)
        hr = appearance.head_radius * s * zoom

        if chest_i is not None and neck_i is not None:
            cx, cy = vp(skeleton.world_positions[chest_i][0], skeleton.world_positions[chest_i][1])
            nx, ny = vp(skeleton.world_positions[neck_i][0], skeleton.world_positions[neck_i][1])
            hx, hy = vp(hips_cx, hips_cy)

            # Shoulder positions (for shirt chest width - shirt covers shoulders)
            left_shoulder_i = next((i for i, b in enumerate(skeleton.bones) if b.name == "left_shoulder"), None)
            right_shoulder_i = next((i for i, b in enumerate(skeleton.bones) if b.name == "right_shoulder"), None)
            if left_shoulder_i is not None and right_shoulder_i is not None:
                lsx, lsy = vp(skeleton.world_positions[left_shoulder_i][0], skeleton.world_positions[left_shoulder_i][1])
                rsx, rsy = vp(skeleton.world_positions[right_shoulder_i][0], skeleton.world_positions[right_shoulder_i][1])
                chest_w = (rsx - lsx) * 1.15  # 15% wider than shoulder span
            else:
                chest_w = 2.5 * hr  # fallback

            # Shirt width at waist (narrowest = 0.85 * head_radius)
            waist_y = cy + (hy - cy) * 0.55  # ~55% down from chest to hips
            waist_w = 0.85 * hr

            # Polygon: neck -> chest -> waist (stop at waist, pants take over)
            shirt_color = bone_color(appearance, "spine")  # shirt_color

            # Chest level points (left, right) - widest part covering shoulders
            chest_left = (cx - chest_w/2, cy)
            chest_right = (cx + chest_w/2, cy)

            # Waist level (narrowest - tucked into pants)
            waist_left = (cx - waist_w/2, waist_y)
            waist_right = (cx + waist_w/2, waist_y)

            # Neck base points (collar)
            neck_w = 0.55 * hr
            neck_left = (nx - neck_w/2, ny)
            neck_right = (nx + neck_w/2, ny)

            # Polygon: neck_left -> chest_left -> waist_left -> waist_right -> chest_right -> neck_right
            polygon = [neck_left, chest_left, waist_left, waist_right, chest_right, neck_right]
            draw.polygon(polygon, fill=shirt_color, outline=shirt_color)

    # 3. Draw joint dots (Pivot Animator style) — small absolute dots,
    #    scaled only by zoom, NOT by figure scale
    if show_joints:
        joints = get_joint_positions(skeleton, 0, 0)
        for jx, jy, label in joints:
            if not bone_visible(label, vis_parts):
                continue
            if label in NO_DOT:
                continue  # hidden joint dots (e.g. hip/lower-leg per rig design)
            # Different sizes for different joint types
            if label == "head":
                hr = appearance.head_radius * s * zoom
                sx, sy = vp(jx, jy)
                draw.ellipse([sx - hr, sy - hr, sx + hr, sy + hr],
                             fill=hc, outline=HEAD_OUTLINE, width=max(1, int(2 * zoom)))
                continue
            elif label == "hips":
                r = HIP_RADIUS * zoom
            elif label in ("neck", "spine"):
                r = NECK_SPINE_RADIUS * zoom
            elif "hand" in label or "foot" in label:
                r = HAND_FOOT_RADIUS * zoom
            else:
                r = KNEE_ELBOW_RADIUS * zoom  # elbows, knees, shoulders

            # White fill with dark outline — Pivot style (dots are FIXED
            # size, so the outline must stay thin — a pen-scaled outline
            # would swallow the fill on these small dots)
            sx, sy = vp(jx, jy)
            draw.ellipse([sx - r, sy - r, sx + r, sy + r],
                         fill=JOINT_FILL, outline=JOINT_OUTLINE,
                         width=max(1, int(1.5 * zoom)))

        # 2b. Shoulder-connection dot — the point where the two shoulder
        # LINES originate: the chest bone tip (both shoulder bones attach
        # there). This is the true "middle of the shoulders", not the
        # geometric midpoint of the shoulder joints (which sits lower
        # because the shoulder bones angle down-out). Tracks in every pose.
        if bone_visible("chest", vis_parts):
            chest_i = next(i for i, b in enumerate(skeleton.bones)
                           if b.name == "chest")
            cx, cy = skeleton.world_positions[chest_i]
            mx, my = vp(cx, cy)
            r = KNEE_ELBOW_RADIUS * zoom
            draw.ellipse([mx - r, my - r, mx + r, my + r],
                         fill=JOINT_FILL, outline=JOINT_OUTLINE,
                         width=max(1, int(1.5 * zoom)))

    # 3. Draw head if not already done by joint rendering
    if not show_joints:
        for i, bone in enumerate(skeleton.bones):
            if bone.name == "head" and bone_visible(bone.name, vis_parts):
                hx, hy = vp(skeleton.world_positions[i][0], skeleton.world_positions[i][1])
                hr = appearance.head_radius * s * zoom
                draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr],
                             fill=hc, outline=HEAD_OUTLINE, width=max(1, int(2 * zoom)))
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
