"""Avatar sheet renderer — turn a captured AvatarGrid into a grid image.

Layout: GRID_COLS columns (timeframes) × N rows (actions). Each cell is a
rendered stickman still centered on a subtle floor tick so grounding is
easy to judge. Rows are labeled with the action name; columns with the
normalized sample time.
"""
import io
from typing import Optional, List
from PIL import Image, ImageDraw

from engine.avatar.capture import AvatarGrid
from engine.animation.skeleton import build_bipedal_skeleton, compute_forward_kinematics
from engine.core.components import Appearance, Position
from engine.renderer.stickman_renderer import draw_stickman

CELL_W = 120
CELL_H = 140
LABEL_H = 22
PAD = 6
FLOOR_Y = CELL_H - 30


def _render_cell_avatar(grid: AvatarGrid, action: str, col: int,
                        show_floor: bool = True) -> Image.Image:
    """Render one action@timeframe as a small stickman still.

    draw_stickman ignores the position argument and draws bone world
    coords directly with a viewport transform. To center the figure in
    the cell and put its feet on FLOOR_Y, we set:
        vx = cell_center_x - hips_world_x * zoom
        vy = FLOOR_Y     - feet_world_y * zoom
    The figure's full height is then scaled to fit the cell.
    """
    pose = grid.get(action, col)
    skel = build_bipedal_skeleton(grid.scale)
    for i, bone in enumerate(skel.bones):
        if bone.name in pose.angles:
            skel.bones[i].default_angle = pose.angles[bone.name]
    compute_forward_kinematics(skel, 0, 0)

    # Vertical extent
    ys = [y for _, y in skel.world_positions]
    top = min(ys)
    bot = max(ys)
    figure_h = bot - top

    # Per-cell zoom so the figure fits the cell with PAD margin top + bottom
    avail_h = CELL_H - 2 * PAD
    zoom = min(1.0, avail_h / figure_h) if figure_h > 0 else 1.0

    # Viewport so feet sit on FLOOR_Y and the figure centers horizontally
    hips_world_x = skel.world_positions[0][0]
    feet_world_y = max(y for _, y in skel.world_positions)
    vx = CELL_W / 2 - hips_world_x * zoom
    vy = FLOOR_Y - feet_world_y * zoom

    img = Image.new('RGB', (CELL_W, CELL_H), "#FAFAFA")
    d = ImageDraw.Draw(img)
    if show_floor:
        d.line([(PAD, FLOOR_Y), (CELL_W - PAD, FLOOR_Y)], fill="#CCCCCC", width=1)

    app = Appearance(
        head_color="#FFD700", body_color="#333333",
        shirt_color="#2E86DE", pants_color="#1B2A4A",
        shoe_color="#8B4513", skin_color="#FFDAB9",
        scale=grid.scale * 0.9,
    )
    # draw_stickman reads position.x/y as a no-op for FK drawing, but the
    # dialog lookup uses it for bubble positioning — pass screen-space center.
    pos = Position(CELL_W / 2, FLOOR_Y - (FLOOR_Y - feet_world_y * zoom))
    draw_stickman(d, skel, app, pos,
                  show_joints=True,
                  viewport_offset=(vx, vy), zoom=zoom)
    return img


def render_grid_image(grid: AvatarGrid, rows: Optional[List[str]] = None,
                      show_floor: bool = True) -> Image.Image:
    """Render the full 6×N avatar sheet as one image."""
    rows = rows if rows is not None else grid.rows()
    cols = grid.n_cols
    width = cols * CELL_W + PAD
    height = LABEL_H + len(rows) * CELL_H + PAD
    sheet = Image.new('RGB', (width, height), "#FFFFFF")
    d = ImageDraw.Draw(sheet)

    # Column headers (normalized time)
    for c in range(cols):
        t01 = grid.cells[(rows[0], c)].t01 if rows else c / (cols - 1)
        label = f"t={t01*100:.0f}%"
        d.text((c * CELL_W + CELL_W / 2 - len(label) * 3, 4), label, fill="#555555")

    for r, action in enumerate(rows):
        # Row label (action name)
        d.text((PAD, LABEL_H + r * CELL_H - 14), action, fill="#333333")
        for c in range(cols):
            cell_img = _render_cell_avatar(grid, action, c, show_floor)
            sheet.paste(cell_img, (c * CELL_W, LABEL_H + r * CELL_H))
            # Cell divider
            d.rectangle([c * CELL_W, LABEL_H + r * CELL_H,
                         c * CELL_W + CELL_W, LABEL_H + (r + 1) * CELL_H],
                        outline="#DDDDDD")
    return sheet


def grid_to_png_bytes(grid: AvatarGrid) -> bytes:
    """Render the grid to PNG bytes (for the web/backend to serve)."""
    img = render_grid_image(grid)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def grid_apply_to_movie(grid: AvatarGrid, action: str,
                        movie_timeline: dict, character: str,
                        start_time: float, scale: float = 1.0) -> dict:
    """Apply a captured action into a movie timeline.

    The captured action is played back by injecting a `character.action`
    timeline event at start_time — the engine runs the same generator that
    produced the captured cells, so the movie replays the exact performance
    shown in the avatar grid.

    Returns the modified timeline dict (mutates in place, also returned).
    """
    scene_key = list(movie_timeline.keys())[0]
    movie_timeline[scene_key].append({
        'time': start_time,
        'action': f"{character}.{action}",
        'params': {'scale': scale},
    })
    return movie_timeline