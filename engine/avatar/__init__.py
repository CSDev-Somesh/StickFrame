"""Avatar Action Grid — capture, verify, and apply avatar action data.

An "avatar grid" is a 6-column × 26-row sheet of character stills:
  - COLUMNS = 6 sampled timeframes through an action's animation
    (t = 0, 0.2, 0.4, 0.6, 0.8, 1.0 × duration)
  - ROWS    = actions (up to 26 from the generator library)

Each cell holds the FULL pose data (25 bone angles) plus a rendered
still. The grid can be:
  1. CAPTURED   -> collect pose data for every action at every timeframe
  2. VERIFIED   -> assert every cell has valid, finite, grounded data
  3. APPLIED    -> replay any captured action into a movie timeline

Design note: the grid is data-first. The PNG is a *view* of the captured
data, not the source of truth — a movie uses the captured angles directly.
"""

from .capture import AvatarGrid, capture_grid, ActionPose
from .sheet import render_grid_image, grid_to_png_bytes
from .apply import (
    grid_to_action_clips, action_to_clip,
    register_clips_to_player, LOOPING_ACTIONS,
)

__all__ = [
    'AvatarGrid', 'capture_grid', 'ActionPose',
    'render_grid_image', 'grid_to_png_bytes',
    'grid_to_action_clips', 'action_to_clip',
    'register_clips_to_player', 'LOOPING_ACTIONS',
]
