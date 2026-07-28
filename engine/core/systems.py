"""Core systems — ECS Processors for the StickFrame engine"""

import math
from typing import Optional
from PIL import Image, ImageDraw

from engine.core.components import (
    Position, Velocity, Transform,
    Skeleton, Appearance, AnimationPlayer, ActionClip, Keyframe,
    PhysicsBody, Collider, Renderable, Camera,
    TimelineTrack, TimelineEvent,
)
from engine.animation.skeleton import compute_forward_kinematics, apply_action_to_skeleton, build_bipedal_skeleton
from engine.animation.easing import interpolate_keyframes
from engine.renderer.stickman_renderer import draw_stickman
from engine.timeline.evaluator import TimelineEvaluator


class AnimationSystem:
    """Updates AnimationPlayer components and applies action clips to skeletons.
    
    For each entity with both AnimationPlayer and Skeleton:
    1. Advance the animation time
    2. Sample the current action clip at the current time
    3. Apply sampled bone angles to the skeleton
    """
    
    def process(self, dt: float, entities: list) -> None:
        """Process all entities with animation components.
        
        Args:
            dt: Delta time in seconds
            entities: List of (entity_id, anim_player, skeleton) tuples
        """
        for ent_id, anim, skel in entities:
            if not anim.playing:
                continue
            
            # Advance time
            anim.time += dt * anim.speed
            
            # Get current clip
            clip = anim.clips.get(anim.current_action) if anim.current_action else None
            if clip is None:
                continue
            
            # Handle looping
            if clip.loop and anim.time >= clip.duration:
                anim.time %= clip.duration
            
            # Apply clip to skeleton
            apply_action_to_skeleton(skel, clip, anim.time)
    
    def play(self, entity_id: int, anim_players: dict, clip_name: str) -> None:
        """Start playing an animation clip on an entity."""
        anim = anim_players.get(entity_id)
        if anim and clip_name in anim.clips:
            anim.current_action = clip_name
            anim.time = 0.0
            anim.playing = True


class PhysicsSystem:
    """Simple 2D physics — gravity, velocity integration, basic collision."""
    
    def __init__(self, gravity: float = 980.0, ground_y: float = 700.0):
        self.gravity = gravity
        self.ground_y = ground_y
    
    def process(self, dt: float, entities: list) -> None:
        """Integrate velocities and apply constraints."""
        for ent_id, pos, vel, phys in entities:
            if phys.is_static:
                continue
            
            # Apply gravity
            vel.vy += self.gravity * phys.gravity_scale * dt
            
            # Integrate position
            pos.x += vel.vx * dt
            pos.y += vel.vy * dt
            
            # Ground collision
            if pos.y >= self.ground_y:
                pos.y = self.ground_y
                vel.vy = -vel.vy * phys.restitution
                if abs(vel.vy) < 10:
                    vel.vy = 0.0
            
            # Friction
            vel.vx *= (1.0 - phys.friction * dt)


class RenderSystem:
    """Generates draw commands from visible entities, outputs a frame."""
    
    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height
    
    def render_frame(self, entities: list, bg_color: str = "#87CEEB") -> Image.Image:
        """Render all visible entities into a single frame.
        
        Args:
            entities: List of (position, skeleton, appearance, renderable) tuples
            bg_color: Background color
            
        Returns:
            Rendered PIL Image
        """
        img = Image.new('RGB', (self.width, self.height), bg_color)
        draw = ImageDraw.Draw(img)
        
        for ent_id, pos, skel, app, rend in entities:
            if not rend.visible:
                continue
            draw_stickman(draw, skel, app, pos)
        
        return img


class Engine:
    """Main engine orchestrator — ties all systems together.
    
    Coordinates the per-frame update loop:
    1. Timeline evaluator fires scheduled events
    2. Animation system updates bone angles
    3. Forward kinematics computes world transforms
    4. Render system generates frame
    5. Export pipeline saves/outputs the frame
    """
    
    def __init__(self, fps: int = 30, width: int = 1280, height: int = 720):
        self.fps = fps
        self.width = width
        self.height = height
        self.time = 0.0
        self.frame_count = 0
        self.running = False
        
        # Systems
        self.animation = AnimationSystem()
        self.physics = PhysicsSystem(ground_y=height - 20)
        self.renderer = RenderSystem(width, height)
        self.timeline = TimelineEvaluator()
        
        # Entity storage (simple flat storage for MVP)
        self.entities: dict = {}  # entity_id -> entity_data
        self._next_id = 1
    
    def create_entity(self, components: dict) -> int:
        """Create an entity with the given components.
        
        Args:
            components: Dict of component_type_name -> component instance
                       e.g. {'position': Position(100, 200), 'skeleton': Skeleton(...)}
        
        Returns:
            Entity ID
        """
        ent_id = self._next_id
        self._next_id += 1
        components['_id'] = ent_id
        self.entities[ent_id] = components
        return ent_id
    
    def add_entity(self, id: int, components: dict) -> None:
        """Add a pre-defined entity."""
        components['_id'] = id
        self.entities[id] = components
    
    def get_entities_with(self, *component_names: str) -> list:
        """Get all entities that have ALL specified components.
        
        Returns:
            List of (entity_id, component1, component2, ...) tuples
        """
        results = []
        for ent_id, comps in self.entities.items():
            match = True
            values = []
            for name in component_names:
                if name not in comps:
                    match = False
                    break
                values.append(comps[name])
            if match:
                results.append((ent_id, *values))
        return results
    
    def step(self, dt: float) -> Image.Image:
        """Advance the engine by one frame time step.
        
        Args:
            dt: Delta time in seconds (usually 1/fps)
            
        Returns:
            Rendered frame as PIL Image
        """
        self.time += dt
        self.frame_count += 1
        
        # 1. Fire timeline events
        self.timeline.step(dt)
        
        # 2. Update animations
        anim_entities = self.get_entities_with('animation_player', 'skeleton')
        self.animation.process(dt, anim_entities)
        
        # 3. Forward kinematics for all skeletons
        skel_entities = self.get_entities_with('position', 'skeleton')
        for ent_id, pos, skel in skel_entities:
            compute_forward_kinematics(skel, pos.x, pos.y)
        
        # 4. Physics
        phys_entities = self.get_entities_with('position', 'velocity', 'physics')
        self.physics.process(dt, phys_entities)
        
        # 5. Render
        render_entities = self.get_entities_with('position', 'skeleton', 'appearance', 'renderable')
        frame = self.renderer.render_frame(render_entities)
        
        return frame
    
    def reset(self) -> None:
        """Reset engine state."""
        self.time = 0.0
        self.frame_count = 0
        self.entities = {}
        self._next_id = 1
        self.timeline.reset()
