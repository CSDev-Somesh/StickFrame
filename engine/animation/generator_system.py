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
            
            # Get generator
            try:
                gen_fn, has_pos, defaults = get_generator(player.current_action)
            except KeyError:
                continue
            
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
                    player.playing = False
                    sample_t = duration
            
            # Sample generator
            result = gen_fn(sample_t, merged)
            
            # Handle generators that return (pose_dict, y_offset)
            y_offset = 0
            if isinstance(result, tuple):
                pose, y_offset = result
            else:
                pose = result
            
            # Apply bone angles to skeleton
            for i, bone in enumerate(skeleton.bones):
                if bone.name in pose:
                    skeleton.bones[i].default_angle = pose[bone.name]
            
            # Position handling for generators that move the character
            if has_pos:
                if player.current_action in ('walk', 'run'):
                    stride = merged.get('stride', 55)
                    speed = merged.get('speed', 1.2)
                    new_off = player.time * speed * stride * 0.8
                    player.position_offset_x = new_off - player._prev_offset_x
                    player._prev_offset_x = new_off
                    
                    bounce = merged.get('bounce', 3)
                    new_bob = math.sin(player.time * speed * math.pi * 2) * bounce
                    player.position_offset_y = new_bob - player._prev_offset_y
                    player._prev_offset_y = new_bob
                
                elif player.current_action == 'jump':
                    dy = y_offset - player._prev_offset_y
                    player.position_offset_y = dy
                    player._prev_offset_y = y_offset
                
                elif player.current_action == 'fall':
                    dy = y_offset - player._prev_offset_y
                    player.position_offset_y = dy
                    player._prev_offset_y = y_offset
    
    def start_action(self, player: ProceduralPlayer, action_name: str, 
                     params: Dict[str, Any] = None) -> None:
        """Start a procedural action on a player."""
        if action_name not in GENERATORS:
            return
        player.current_action = action_name
        player.time = 0.0
        player.playing = True
        player.params = params or {}
        player.position_offset_x = 0.0
        player.position_offset_y = 0.0
        player._prev_offset_x = 0.0
        player._prev_offset_y = 0.0
        
        # Non-looping actions
        _, _, defaults = get_generator(action_name)
        player.loop = action_name in ('idle', 'walk', 'run')