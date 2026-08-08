"""Core systems — ECS Processors for the StickFrame engine"""

import math
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

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
from engine.animation.generator_system import GeneratorSystem, HEIGHT_ACTIONS


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
                # Capture the end-of-cycle position value before looping
                if clip.position_keyframes.get('x'):
                    end_x = interpolate_keyframes(
                        [(k.time, k.angle) for k in clip.position_keyframes['x']],
                        clip.duration)
                    anim._cycle_pos_x += end_x - anim._prev_pos_x
                if clip.position_keyframes.get('y'):
                    end_y = interpolate_keyframes(
                        [(k.time, k.angle) for k in clip.position_keyframes['y']],
                        clip.duration)
                    anim._cycle_pos_y += end_y - anim._prev_pos_y
                # Reset prev tracking for the new cycle
                anim._prev_pos_x = 0.0
                anim._prev_pos_y = 0.0
                anim.time %= clip.duration
            
            # Apply clip bone keyframes to skeleton
            apply_action_to_skeleton(skel, clip, anim.time)
            
            # Apply position keyframes — compute delta from previous frame
            if clip.position_keyframes:
                kfs_x = clip.position_keyframes.get('x')
                kfs_y = clip.position_keyframes.get('y')
                
                t = anim.time
                # For looping clips, sample within duration
                if clip.loop and clip.duration > 0:
                    t = anim.time % clip.duration
                else:
                    t = min(anim.time, clip.duration)
                
                current_x = interpolate_keyframes([(k.time, k.angle) for k in kfs_x], t) if kfs_x else 0
                current_y = interpolate_keyframes([(k.time, k.angle) for k in kfs_y], t) if kfs_y else 0
                
                # Compute delta from last frame's position keyframe value
                dx = current_x - anim._prev_pos_x
                dy = current_y - anim._prev_pos_y
                
                anim.position_offset_x += dx
                anim.position_offset_y += dy
                
                # Add any completed cycle accumulation
                if anim._cycle_pos_x != 0 or anim._cycle_pos_y != 0:
                    anim.position_offset_x += anim._cycle_pos_x
                    anim.position_offset_y += anim._cycle_pos_y
                    anim._cycle_pos_x = 0
                    anim._cycle_pos_y = 0
                
                anim._prev_pos_x = current_x
                anim._prev_pos_y = current_y
    
    def play(self, entity_id: int, anim_players: dict, clip_name: str) -> None:
        """Start playing an animation clip on an entity."""
        anim = anim_players.get(entity_id)
        if anim and clip_name in anim.clips:
            anim.current_action = clip_name
            anim.time = 0.0
            anim.playing = True
            # Reset position keyframe tracking
            anim.position_offset_x = 0.0
            anim.position_offset_y = 0.0
            anim._prev_pos_x = 0.0
            anim._prev_pos_y = 0.0
            anim._cycle_pos_x = 0.0
            anim._cycle_pos_y = 0.0


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

            # Ground plane for THIS entity: the feet are ground_offset below
            # the origin (hips), so gravity stops and collision snaps at
            # ground_y - ground_offset — feet land on the floor, not the hips.
            ground = self.ground_y - phys.ground_offset

            # Apply gravity only if above ground
            if pos.y < ground:
                vel.vy += self.gravity * phys.gravity_scale * dt

            # Integrate position
            pos.x += vel.vx * dt
            pos.y += vel.vy * dt

            # Ground collision
            if pos.y >= ground:
                pos.y = ground
                vel.vy = -vel.vy * phys.restitution
                if abs(vel.vy) < 10:
                    vel.vy = 0.0

            # Friction
            vel.vx *= (1.0 - phys.friction * dt)


class CameraSystem:
    """Computes viewport transforms from camera components.

    Features:
      - Smooth follow with configurable lerp speed
      - Camera shake (deterministic smooth curve)
      - Animated zoom transitions (via target_zoom)
      - Zoom min/max bounds
      - Active camera selection for multi-camera scenes
    """

    def compute_viewport(self, camera_entities: list, entity_positions: dict,
                         screen_width: int, screen_height: int, dt: float = 0) -> tuple:
        """Compute viewport transform with smooth follow, shake, zoom animation.

        Args:
            camera_entities: List of (entity_id, camera) tuples
            entity_positions: Dict of entity_id -> Position
            screen_width, screen_height: Output dimensions
            dt: Delta time for smooth interpolation (0 = instant)

        Returns:
            (offset_x, offset_y, zoom) — apply world_pos * zoom + offset for rendering
        """
        # Find the first active camera
        active_cam = None
        for ent_id, cam in camera_entities:
            if cam.active:
                active_cam = (ent_id, cam)
                break

        if active_cam is None:
            return (0, 0, 1.0)

        ent_id, cam = active_cam

        # 1. Compute target position (what the camera should look at)
        target_x, target_y = screen_width / 2, screen_height / 2  # default center
        if cam.target_entity is not None and cam.target_entity in entity_positions:
            target_pos = entity_positions[cam.target_entity]
            target_x, target_y = target_pos.x, target_pos.y
        elif ent_id in entity_positions:
            own_pos = entity_positions[ent_id]
            target_x, target_y = own_pos.x, own_pos.y

        # Per-axis follow toggles: a disabled axis pins the camera to its
        # current position (set current_y = screen_height/2 for a grounded
        # side-scroller view where the character stays on a fixed floor line).
        if not cam.follow_x:
            target_x = cam.current_x
        if not cam.follow_y:
            target_y = cam.current_y

        # Pan targets override follow — camera lerps to the pan point with the
        # same smooth curve as entity follow. Only axes with an explicit pan
        # target move; the other axis keeps its follow/hold behavior.
        if cam.pan_target_x is not None:
            target_x = cam.pan_target_x
        if cam.pan_target_y is not None:
            target_y = cam.pan_target_y

        # 2. Smooth follow — lerp current position toward target
        if dt > 0 and cam.smooth_speed > 0:
            lerp = 1.0 - math.exp(-cam.smooth_speed * dt)
            cam.current_x += (target_x - cam.current_x) * lerp
            cam.current_y += (target_y - cam.current_y) * lerp
        else:
            cam.current_x = target_x
            cam.current_y = target_y

        # 3. Animated zoom — lerp toward target_zoom
        tz = cam.target_zoom if cam.target_zoom is not None else cam.zoom
        if dt > 0 and cam.smooth_speed > 0:
            lerp_z = 1.0 - math.exp(-cam.smooth_speed * dt)
            cam.zoom += (tz - cam.zoom) * lerp_z
        else:
            cam.zoom = tz

        # 4. Clamp zoom to bounds
        cam.zoom = max(cam.min_zoom, min(cam.max_zoom, cam.zoom))

        # 5. Camera shake — deterministic smooth sine/cosine
        shake_ox, shake_oy = 0.0, 0.0
        if cam.shake_timer > 0:
            shake_ox = math.sin(cam.shake_timer * 31.7) * cam.shake_intensity
            shake_oy = math.cos(cam.shake_timer * 27.3) * cam.shake_intensity
            cam.shake_timer -= dt
            if cam.shake_timer <= 0:
                cam.shake_timer = 0.0
                cam.shake_intensity = 0.0

        # 6. Compute viewport offset
        offset_x = screen_width / 2 - cam.current_x * cam.zoom + shake_ox
        offset_y = screen_height / 2 - cam.current_y * cam.zoom + shake_oy
        return (offset_x, offset_y, cam.zoom)


class RenderSystem:
    """Generates draw commands from visible entities, outputs a frame."""
    
    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height
    
    def render_frame(self, entities: list, bg_color: str = "#FFFFFF",
                     viewport_offset: tuple = (0, 0), zoom: float = 1.0,
                     facings: dict = None) -> Image.Image:
        """Render all visible entities into a single frame.

        Args:
            entities: List of (position, skeleton, appearance, renderable) tuples
            bg_color: Background color
            viewport_offset: (offset_x, offset_y) to apply to all world coords
            zoom: Viewport zoom factor
            facings: Optional dict mapping entity_id -> 'left'/'right'. When
                omitted, every character renders facing right (legacy).

        Returns:
            Rendered PIL Image
        """
        img = Image.new('RGB', (self.width, self.height), bg_color)
        draw = ImageDraw.Draw(img)

        for ent_id, pos, skel, app, rend in entities:
            if not rend.visible:
                continue
            facing = (facings or {}).get(ent_id, 'right')
            # Apply viewport transform: screen = world * zoom + offset
            draw_stickman(draw, skel, app, pos,
                          viewport_offset=viewport_offset, zoom=zoom,
                          facing=facing)

        return img

    def draw_dialogue_bubble(self, frame: Image.Image, text: str,
                             cx: float, top_y: float, zoom: float = 1.0) -> None:
        """Draw a speech bubble above a character's head.

        Args:
            frame: The frame image to draw on
            text: The dialogue text
            cx: Screen-space bubble center x (head position)
            top_y: Screen-space y for the top of the bubble
            zoom: Viewport zoom (scales font + padding modestly)
        """
        if not text:
            return
        draw = ImageDraw.Draw(frame)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                                      max(12, int(14 * zoom)))
        except Exception:
            font = ImageFont.load_default()

        # Wrap text to ~28 chars per line
        words, lines, cur = text.split(), [], ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if len(cand) > 28 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)

        pad = 6
        line_h = font.getbbox("Ag")[3] + 4
        w = max(font.getbbox(l)[2] for l in lines) + 2 * pad
        h = line_h * len(lines) + 2 * pad

        x0, y0 = cx - w / 2, top_y - h
        # Clamp to frame bounds
        x0 = max(2, min(x0, frame.width - w - 2))
        y0 = max(2, min(y0, frame.height - h - 2))

        draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=6,
                               fill="white", outline="black", width=2)
        # Bubble tail — small triangle pointing down at the head
        tx = min(max(cx, x0 + 10), x0 + w - 10)
        draw.polygon([(tx - 7, y0 + h), (tx + 7, y0 + h), (cx, y0 + h + 10)],
                     fill="white", outline="black")
        draw.line([(tx - 7, y0 + h), (tx + 7, y0 + h)], fill="black", width=2)

        for i, l in enumerate(lines):
            lw = font.getbbox(l)[2]
            draw.text((cx - lw / 2, y0 + pad + i * line_h), l,
                      font=font, fill="black")


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
        self.generators = GeneratorSystem()
        self.physics = PhysicsSystem(ground_y=height - 20)
        self.renderer = RenderSystem(width, height)
        self.timeline = TimelineEvaluator()
        self.camera = CameraSystem()
        
        # Entity storage (simple flat storage for MVP)
        self.entities: dict = {}  # entity_id -> entity_data
        self._next_id = 1
        # ponytail: single global bg color; timeline `bg.set(color=...)` changes it
        self.bg_color = "#FFFFFF"
    
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
        
        # 2. Update keyframe animations
        anim_entities = self.get_entities_with('animation_player', 'skeleton')
        self.animation.process(dt, anim_entities)
        
        # 2.5 Apply keyframe animation position offsets
        for ent_id, anim in self.get_entities_with('animation_player'):
            if anim.position_offset_x != 0 or anim.position_offset_y != 0:
                pos = self.entities[ent_id].get('position')
                if pos:
                    pos.x += anim.position_offset_x
                    pos.y += anim.position_offset_y
                    anim.position_offset_x = 0
                    anim.position_offset_y = 0
        
        # 2.6 Update procedural generators
        proc_entities = self.get_entities_with('procedural_player', 'skeleton')
        self.generators.process(dt, proc_entities)
        
        # 2.7 Apply procedural position offsets
        for ent_id, player in self.get_entities_with('procedural_player'):
            # When velocity_move is active (timeline x= with walk/run/sprint),
            # the generator's own X offset is suppressed so the character
            # doesn't double-move (velocity + stride). The Y bob is kept
            # for life.
            if player.velocity_move:
                player.position_offset_x = 0.0
                player._prev_offset_x = 0.0
            if player.position_offset_x != 0 or player.position_offset_y != 0:
                pos = self.entities[ent_id].get('position')
                if pos:
                    pos.x = pos.x + player.position_offset_x
                    pos.y = pos.y + player.position_offset_y
            # Height-driven actions (sit/lie/kneel): the generator returns a
            # total hips descent; apply it to position.y and move the physics
            # ground to follow so the ground clamp never fights the descent.
            if player.playing and player.current_action in HEIGHT_ACTIONS \
               and player._height_offset is not None:
                pos = self.entities[ent_id].get('position')
                if pos:
                    if player._height_base is None:
                        player._height_base = pos.y
                    pos.y = player._height_base + player._height_offset
                    phys = self.entities[ent_id].get('physics')
                    if phys:
                        phys.ground_offset = self.physics.ground_y - pos.y
                    vel = self.entities[ent_id].get('velocity')
                    if vel:
                        vel.vy = 0.0
            # Delayed physics impulse — fires once the action reaches
            # impulse_time (jump: launch AFTER the crouch pose reads)
            if player.impulse_vy and not player.impulse_fired and \
               player.time >= player.impulse_time:
                vel = self.entities[ent_id].get('velocity')
                if vel:
                    vel.vy = player.impulse_vy
                player.impulse_fired = True
        
        # 3. Physics — run BEFORE FK so skeletons reflect physics movements
        phys_entities = self.get_entities_with('position', 'velocity', 'physics')
        self.physics.process(dt, phys_entities)

        # 3.5 Stop-at-target — check if any character reached their
        # velocity-move target and stop them.
        for ent_id, comps in self.entities.items():
            target = comps.get('_movement_target')
            if target is not None:
                pos = comps.get('position')
                vel = comps.get('velocity')
                if pos and vel:
                    if abs(pos.x - target) < 5:
                        vel.vx = 0
                        pos.x = target  # snap to exact position
                        comps['_movement_target'] = None
                        comps['_movement_speed'] = None
                        # Keep velocity_move=True: the loop action (walk/run)
                        # keeps playing in place with its X stride suppressed,
                        # so the character stays exactly at the target. If we
                        # cleared it here, the generator would resume its own
                        # accumulated position offset (time × speed × stride)
                        # and the character would JUMP forward and keep moving.
                        # The next timeline event (e.g. idle) resets the player.
                    else:
                        # Counteract friction: keep the movement velocity at
                        # its set speed while traveling to the target
                        # (otherwise vx decays ~1.7%/frame at 30fps and the
                        # character stalls far short of the target).
                        mspd = comps.get('_movement_speed')
                        if mspd:
                            vel.vx = mspd

        # 4. Forward kinematics for all skeletons (uses updated positions)
        skel_entities = self.get_entities_with('position', 'skeleton')
        for ent_id, pos, skel in skel_entities:
            compute_forward_kinematics(skel, pos.x, pos.y)

        # 4.5 Camera / viewport transform
        cam_entities = self.get_entities_with('camera')
        # Build entity position lookup for camera target tracking
        ent_positions = {}
        for ent_id, pos in self.get_entities_with('position'):
            ent_positions[ent_id] = pos
        viewport_offset_x, viewport_offset_y, zoom = self.camera.compute_viewport(
            cam_entities, ent_positions, self.width, self.height, dt=dt)

        # 5. Render
        render_entities = self.get_entities_with('position', 'skeleton', 'appearance', 'renderable')
        # Facing map so the renderer mirrors characters that turned around
        facing_map = {eid: comps['facing'].direction
                      for eid, comps in self.entities.items()
                      if 'facing' in comps}
        frame = self.renderer.render_frame(render_entities,
                                         viewport_offset=(viewport_offset_x, viewport_offset_y),
                                         zoom=zoom,
                                         bg_color=self.bg_color,
                                         facings=facing_map)

        # 5.5 Dialogue bubbles — draw above characters with active speech
        dlg_entities = self.get_entities_with('position', 'skeleton', 'dialogue')
        for ent_id, pos, skel, dlg in dlg_entities:
            if dlg.active_text and dlg.progress > 0:
                # Head bone is index 4 in the bipedal rig
                head_i = next((i for i, b in enumerate(skel.bones) if b.name == "head"), None)
                if head_i is not None:
                    hx, hy = skel.world_positions[head_i]
                    self.renderer.draw_dialogue_bubble(
                        frame, dlg.active_text,
                        hx * zoom + viewport_offset_x,
                        hy * zoom + viewport_offset_y - 20 * zoom,
                        zoom)
                dlg.progress -= dt
        
        return frame
    
    def reset(self) -> None:
        """Reset engine state."""
        self.time = 0.0
        self.frame_count = 0
        self.entities = {}
        self._next_id = 1
        self.timeline.reset()
