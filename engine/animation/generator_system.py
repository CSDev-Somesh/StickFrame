
"""GeneratorSystem — drives procedural animation generators in the engine loop

For each entity with a ProceduralPlayer:
  1. Advance time
  2. Call the generator function
  3. Apply bone angles to Skeleton
  4. Compute position deltas for forward movement
"""

import math
from typing import Dict, Any

from engine.core.components import ProceduralPlayer, Skeleton, Position
from engine.animation.generators import get_generator, GENERATORS

# Height-driven actions (sit/lie/kneel family): their generators return
# (pose, y_offset) — y_offset is the total hips descent in px from the
# height the action started at. Engine.step applies it to position.y and
# moves the physics ground to follow, so the body lowers/raises without
# the ground clamp fighting it.
HEIGHT_ACTIONS = frozenset({
    'sit', 'stand_up', 'kneel', 'lie_down', 'get_up',
    'sweep', 'slide',
    'charge',            # crouch-down power-up
    'collapse', 'get_back_up',   # fall to floor / rise
    'fly', 'hover', 'land',      # flight altitude changes
    'celebrate', 'crawl',        # hop up / down on hands+ knees
})


class GeneratorSystem:
    """Processes procedural animation generators every frame.
    
    Wired into Engine.step() — runs after timeline, before FK.
    """
    
    def process(self, dt: float, entities: list) -> None:
        """Process all entities with ProceduralPlayer + Skeleton.
        
        Args:
            dt: Delta time in seconds
            entities: List of (entity_id, proc_player, skeleton)
        """
        for ent_id, player, skeleton in entities:
            if not player.playing or not player.current_action:
                continue
            
            # Advance time
            player.time += dt * player.speed
            
            # Get generator — should never miss now that start_action validates,
            # but if it does, fail loud so we don't silently freeze the figure.
            gen_fn, has_pos, defaults = get_generator(player.current_action)
            
            # Merge default params with overrides
            merged = {**defaults, **player.params}
            
            # Handle looping
            duration = merged.get('duration', 1.0)
            sample_t = player.time
            if player.loop and duration > 0:
                sample_t = player.time % duration
                if sample_t == 0 and player.time > 0:
                    # Loop completed - reset position tracking for non-looping position offsets
                    pass
            elif not player.loop:
                if player.time >= duration:
                    # Non-looping action finished - transition to idle
                    sample_t = duration
                    player.time = duration  # Hold at end frame
                    # Schedule transition to idle on next frame
                    if not hasattr(player, '_should_return_to_idle'):
                        player._should_return_to_idle = True
            
            # Sample generator
            result = gen_fn(sample_t, merged)
            
            # Handle generators that return (pose_dict, y_offset)
            y_offset = 0
            if isinstance(result, tuple):
                pose, y_offset = result
            else:
                pose = result

            # Store the height offset for height-driven actions (Engine.step
            # applies it to position.y in the 2.7 loop). Non-height actions
            # leave it None so the loop skips them.
            if player.current_action in HEIGHT_ACTIONS:
                player._height_offset = y_offset
            
            # Action blending — smooth crossfade when switching actions
            if player.blend_from_pose is not None:
                player.blend_timer += dt
                blend_t = min(player.blend_timer / player.blend_duration, 1.0)
                blend_weight = blend_t * (2 - blend_t)  # ease-out quad
                for bone_name in pose:
                    if bone_name in player.blend_from_pose:
                        pose[bone_name] = (player.blend_from_pose[bone_name] * (1 - blend_weight) + 
                                           pose[bone_name] * blend_weight)
                if blend_t >= 1.0:
                    player.blend_from_pose = None
                    player.blend_timer = 0.0
            
            player._prev_frame_pose = dict(pose)
            
            # Apply bone angles to skeleton
            for i, bone in enumerate(skeleton.bones):
                if bone.name in pose:
                    skeleton.bones[i].default_angle = pose[bone.name]
            
            # Position handling for generators that move the character
            if has_pos:
                if player.current_action in ('walk', 'run', 'sprint'):
                    scale = merged.get('scale', 1.0)
                    stride = merged.get('stride', 55) * scale
                    speed = merged.get('speed', 1.2)
                    new_off = player.time * speed * stride * 0.8
                    player.position_offset_x = new_off - player._prev_offset_x
                    player._prev_offset_x = new_off

                    bounce = merged.get('bounce', 3) * scale
                    new_bob = math.sin(player.time * speed * math.pi * 2) * bounce
                    player.position_offset_y = new_bob - player._prev_offset_y
                    player._prev_offset_y = new_bob

            # Return to idle after non-looping action completes
            if hasattr(player, '_should_return_to_idle') and player._should_return_to_idle:
                player._should_return_to_idle = False
                self.start_action(player, 'idle', params=merged)
    
    def start_action(self, player: ProceduralPlayer, action_name: str,
                     params: Dict[str, Any] = None) -> None:
        """Start a procedural action on a player with blending.

        Raises KeyError if action_name is not registered — a typo in the
        .sf timeline should fail loud, not silently freeze the character
        in the last pose (the resume note flagged this exact bug).
        """
        if action_name not in GENERATORS:
            raise KeyError(
                f"Unknown action: '{action_name}'. "
                f"Available: {sorted(GENERATORS.keys())}"
            )
        
        # Capture current pose for blending before switching
        if player._prev_frame_pose and player.current_action and player.current_action != action_name:
            player.blend_from_pose = dict(player._prev_frame_pose)
            player.blend_timer = 0.0
        
        player.current_action = action_name
        player.time = 0.0
        player.playing = True
        player.params = params or {}
        player.position_offset_x = 0.0
        player.position_offset_y = 0.0
        player._prev_offset_x = 0.0
        player._prev_offset_y = 0.0
        # Reset delayed-impulse state (jump anticipation)
        player.impulse_vy = 0.0
        player.impulse_time = 0.0
        player.impulse_fired = False
        # Reset height tracking — the new action captures its own start
        # height on its first processed frame
        player._height_base = None
        player._height_offset = None
        
        # Loop behavior: only continuous/cyclic actions should loop
        # All one-shot actions (punch, jump, kick, etc.) should play once
        _, _, defaults = get_generator(action_name)
        player.loop = action_name in ('idle', 'walk', 'run', 'sneak', 'sprint',
                                       'happy', 'sad', 'angry', 'scared',
                                       'dance', 'celebrate', 'tremble',
                                       'power_pose', 'hover', 'fly', 'crawl')