"""Avatar Grid Application — convert captured ActionPoses into playable ActionClips.

The avatar capture system (`engine/avatar/capture.py`) samples every
procedural action at 6 normalized timeframes (t = 0, .2, .4, .6, .8, 1.0 ×
duration) and stores the full 25-bone angle dict per cell as an
`ActionPose`. This module turns those captured poses into keyframe
`ActionClip` objects the engine's `AnimationPlayer` can replay — so
animations can be authored/edited from captured data instead of only
through the procedural generators.

Key facts about the conversion:
  - `ActionPose.angles` holds bone angles in RADIANS (the same units as
    `Keyframe.angle` and `Skeleton.default_angle`) — no conversion needed.
  - Looping actions get a wrap-around final keyframe (the first pose's
    angles are copied onto the last keyframe at the clip's end), so the
    engine's `time % duration` sampling yields a perfectly seamless loop
    with no pop where the cycle repeats.
  - One-shot actions play through all 6 sampled poses, then the engine
    holds the final pose (the interpolator clamps at the last keyframe).
  - Height-driven actions (sit/kneel/lie_down/...) reproduce the bone
    folding via keyframes. The captured `y_offset` is deliberately NOT
    written to `position_keyframes`: the keyframe path has no per-frame
    ground-following mechanism (the procedural path moves
    `physics.ground_offset` along each frame), so writing raw y offsets
    here would fight the physics ground clamp and snap the figure back.
"""

import warnings
from typing import Dict, List

from engine.avatar.capture import AvatarGrid, ActionPose
from engine.core.components import ActionClip, Keyframe
from engine.animation.generator_system import HEIGHT_ACTIONS

# Actions already warned about this process — dedupes the sit/kneel/lie
# position-keyframe limitation so a batch conversion of 60+ actions doesn't
# print a wall of warnings for the same message.
_WARNED_HEIGHT: set = set()


# Actions that should loop forever.
# Mirrors the loop set in engine/animation/generator_system.py — captured
# clips must loop where the procedural generators loop, and play once
# (then hold) everywhere else.
LOOPING_ACTIONS = frozenset({
    'idle', 'walk', 'run', 'sneak', 'sprint',
    'happy', 'sad', 'angry', 'scared',
    'dance', 'celebrate', 'tremble',
    'power_pose', 'hover', 'fly', 'crawl',
})


def grid_to_action_clips(grid: AvatarGrid) -> Dict[str, ActionClip]:
    """Convert all captured actions in a grid to ActionClip objects.

    Args:
        grid: AvatarGrid with captured pose data.

    Returns:
        Dict mapping action_name -> ActionClip.
    """
    clips = {}
    with warnings.catch_warnings():
        # Batch conversion knowingly covers height-driven actions (sit/
        # kneel/lie family). Suppress the per-action position-keyframe
        # limitation warning here — it's intended for users converting a
        # SINGLE height-driven action via action_to_clip().
        warnings.simplefilter("ignore", UserWarning)
        for action_name in grid.rows():
            clips[action_name] = action_to_clip(grid, action_name)
    return clips


def action_to_clip(grid: AvatarGrid, action_name: str,
                   bone_names: List[str] | None = None) -> ActionClip:
    """Convert one captured action to an ActionClip.

    Args:
        grid: AvatarGrid with captured data.
        action_name: Name of the action to convert.
        bone_names: Optional explicit bone order. If omitted, the union of
            all sampled poses' bone keys is used (capture guarantees all
            25 bones per cell, so this is defensive only).

    Returns:
        ActionClip with bone keyframes for all 6 timeframes.

    Raises:
        KeyError: If the action is not present in the grid.
    """
    poses = [grid.get(action_name, col) for col in range(grid.n_cols)]
    if not poses:
        raise KeyError(f"Action '{action_name}' not found in avatar grid")

    is_looping = action_name in LOOPING_ACTIONS
    duration = poses[-1].time_s
    if duration <= 0:
        # Capture stores t01 samples of the generator's default duration;
        # be safe against zero-length actions.
        duration = 1.0

    if action_name in HEIGHT_ACTIONS and action_name not in _WARNED_HEIGHT:
        _WARNED_HEIGHT.add(action_name)
        warnings.warn(
            f"'{action_name}' is a height-driven action (sit/kneel/lie family): "
            "the captured hips y_offset is NOT written to position keyframes, "
            "so the figure's bone fold plays at standing height (feet may "
            "float or clip through the floor). The procedural generator "
            "path handles vertical descent with per-frame ground following — "
            "use it instead of the captured clip if height matters.",
            stacklevel=2,
        )

    # Every bone across every sampled pose (capture guarantees all 25).
    if bone_names is None:
        all_bones = set()
        for pose in poses:
            all_bones.update(pose.angles.keys())
        bone_names = sorted(all_bones)

    bone_keyframes: Dict[str, List[Keyframe]] = {}
    for bone_name in bone_names:
        keyframes: List[Keyframe] = []
        for pose in poses:
            # Defensive: if a pose somehow misses this bone, carry the
            # previous angle forward rather than dropping the keyframe
            # (a hole would make the engine interpolate across a gap).
            angle = pose.angles.get(
                bone_name,
                keyframes[-1].angle if keyframes else 0.0
            )
            keyframes.append(Keyframe(time=pose.time_s, angle=angle))

        if is_looping and len(keyframes) >= 2:
            # Seamless loop: the final sampled pose may not exactly match
            # the first (e.g. walk sampled at t=1.0 has a different phase
            # than t=0). Copy the FIRST pose's angle onto the LAST
            # keyframe so `time % duration` wraps with no pop.
            keyframes[-1] = Keyframe(time=duration, angle=keyframes[0].angle)

        bone_keyframes[bone_name] = keyframes

    return ActionClip(
        name=action_name,
        duration=duration,
        loop=is_looping,
        bone_keyframes=bone_keyframes,
    )


def register_clips_to_player(player, clips: Dict[str, ActionClip]) -> None:
    """Attach converted clips to an entity's AnimationPlayer.

    Convenience helper for the common integration path:

        player = engine.entities[eid]['animation_player']
        register_clips_to_player(player, clips)

    Existing clips on the player are preserved (only keys in `clips` are
    set/overwritten).
    """
    for name, clip in clips.items():
        player.clips[name] = clip