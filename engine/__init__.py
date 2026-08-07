"""StickFrame Engine — Main entry point

Usage:
    from engine import StickFrameEngine
    
    engine = StickFrameEngine()
    engine.create_character("hero", x=200, y=400, head_color="#FFD700")
    engine.play_action(1, "walk")  # entity_id=1
    engine.render("output.mp4", duration=3.0, fps=30)
"""

from typing import Optional
from PIL import Image

from engine.core.components import (
    Position, Velocity, Appearance, Skeleton,
    AnimationPlayer, ActionClip, Renderable, Camera, PhysicsBody, Collider,
    TimelineEvent, ProceduralPlayer, DialogueState,
)
from engine.core.systems import Engine, AnimationSystem
from engine.animation.skeleton import build_bipedal_skeleton, compute_forward_kinematics
from engine.animation.actions import get_action, BUILTIN_ACTIONS
from engine.pipeline.export import ExportPipeline
from engine.animation.generator_system import HEIGHT_ACTIONS


class StickFrameEngine(Engine):
    """High-level interface for the StickFrame animation engine.
    
    Provides simplified methods for creating scenes with characters
    and rendering them to video, hiding ECS complexity.
    """
    
    def __init__(self, fps: int = 30, width: int = 1280, height: int = 720):
        super().__init__(fps=fps, width=width, height=height)
        self._export = ExportPipeline(fps=fps)
    
    def create_character(
        self,
        name: str,
        x: float = 400,
        y: float = 400,
        head_color: str = "#FFD700",
        body_color: str = "#333333",
        shirt_color: str = "#2E86DE",
        pants_color: str = "#1B2A4A",
        shoe_color: str = "#8B4513",
        skin_color: str = "#FFDAB9",
        scale: float = 1.0,
    ) -> int:
        """Create a stickman character in the scene.

        Args:
            name: Character identifier (used for timeline events)
            x: Initial X position
            y: Initial Y position
            head_color: HTML color for head
            body_color: HTML color for body/limbs (fallback)
            shirt_color: HTML color for shirt/torso
            pants_color: HTML color for pants/legs
            shoe_color: HTML color for shoes/feet
            skin_color: HTML color for neck, forearms, hands
            scale: Overall size multiplier

        Returns:
            Entity ID
        """
        skeleton = build_bipedal_skeleton(scale)
        appearance = Appearance(
            head_color=head_color, body_color=body_color,
            shirt_color=shirt_color or "#2E86DE",
            pants_color=pants_color or "#1B2A4A",
            shoe_color=shoe_color or "#8B4513",
            skin_color=skin_color or "#FFDAB9",
            scale=scale,
        )

        # Feet ground offset: distance from hips (entity origin) down to the
        # BOTTOM of the foot circles in the rest pose. Computed via FK so it
        # stays correct for any skeleton proportions/angles — the foot bones
        # extend below the ankle, and the foot circles add their radius, so
        # grounding at ankle level would sink the feet into the floor.
        # NOTE: joint dots are drawn at a FIXED radius (HAND_FOOT_RADIUS *
        # zoom, NOT scale*zoom — the renderer keeps dots pen-sized), so the
        # grounding add-on must be the drawn radius, not scale*radius.
        compute_forward_kinematics(skeleton)
        from engine.renderer.stickman_renderer import HAND_FOOT_RADIUS
        feet_reach = max(y for _, y in skeleton.world_positions)
        ground_offset = feet_reach + HAND_FOOT_RADIUS

        # Use ProceduralPlayer for built-in actions, AnimationPlayer for custom keyframe actions
        player = ProceduralPlayer(playing=True)
        anim_player = AnimationPlayer()

        phys = PhysicsBody(mass=1.0, is_static=False, ground_offset=ground_offset,
                           rest_ground_offset=ground_offset)

        return self.create_entity({
            'position': Position(x, y),
            'velocity': Velocity(0, 0),
            'skeleton': skeleton,
            'appearance': appearance,
            'procedural_player': player,
            'animation_player': anim_player,
            'renderable': Renderable(visible=True, z_order=0),
            'physics': phys,
            'dialogue': DialogueState(),
            'name': name,
        })
    
    def play_action(self, entity_id: int, action_name: str) -> None:
        """Start playing an action on a character.

        Checks AnimationPlayer (custom keyframe actions) first,
        falls back to ProceduralPlayer (built-in procedural actions).
        Stops the other player when switching.

        Args:
            entity_id: The entity ID
            action_name: Name of the action
        """
        comps = self.entities[entity_id]

        # Try custom keyframe action first
        anim = comps.get('animation_player')
        if anim and action_name in anim.clips:
            # Stop procedural player
            pp = comps.get('procedural_player')
            if pp:
                pp.playing = False
                pp.current_action = None
            # Start keyframe action
            if anim.current_action != action_name:
                anim.current_action = action_name
                anim.time = 0.0
                anim.playing = True
                anim.position_offset_x = 0.0
                anim.position_offset_y = 0.0
                anim._prev_pos_x = 0.0
                anim._prev_pos_y = 0.0
            return

        # Fall back to procedural built-in action
        player = comps.get('procedural_player')
        if player:
            # Stop animation player
            anim = comps.get('animation_player')
            if anim:
                anim.playing = False
                anim.current_action = None
            # Start procedural action — pass scale + real ground distance so
            # generators (walk/run IK) target the ACTUAL ground, not a
            # hardcoded scale=1 value. This keeps foot placement correct for
            # any skeleton proportions or render scale.
            # NOTE: the IK end effector is the foot TIP, so subtract the foot
            # circle radius — otherwise legs over-extend to reach the floor
            # line and knees lock straight. Radius is the DRAWN dot radius
            # (fixed, pen-sized — not scaled with the figure).
            from engine.renderer.stickman_renderer import HAND_FOOT_RADIUS
            params = {'scale': comps['appearance'].scale}
            phys = comps.get('physics')
            if phys:
                params['ground'] = phys.ground_offset - HAND_FOOT_RADIUS
            self.generators.start_action(player, action_name, params=params)
            # Leaving a height-driven action (sit/lie/kneel): restore the
            # standing ground offset so walk/run/idle ground at normal height
            # again. Height actions manage ground_offset themselves.
            if action_name not in HEIGHT_ACTIONS:
                phys = comps.get('physics')
                if phys and phys.rest_ground_offset:
                    phys.ground_offset = phys.rest_ground_offset
            # Physics impulses for jump/fall
            vel = comps.get('velocity')
            if action_name == 'jump' and vel:
                # Delayed: fires when the generator crosses impulse_time
                # (after the crouch), so anticipation reads before launch.
                player.impulse_vy = -420
                player.impulse_time = 0.2
            elif action_name == 'fall' and vel:
                vel.vy = 180
                vel.vx = -80
    
    def set_position(self, entity_id: int, x: float, y: float) -> None:
        """Set a character's position."""
        pos = self.entities[entity_id].get('position')
        if pos:
            pos.x = x
            pos.y = y
    
    def move_toward(self, entity_id: int, target_x: float, speed: float = 200) -> None:
        """Set velocity to move toward a target X position."""
        pos = self.entities[entity_id].get('position')
        vel = self.entities[entity_id].get('velocity')
        if pos and vel:
            if abs(target_x - pos.x) > 5:
                vel.vx = speed if target_x > pos.x else -speed
            else:
                vel.vx = 0
    
    def _auto_frame_characters(self) -> None:
        """Ground characters on the floor and ensure something follows them.

        Without this, a bare `create_character()` + `render()` produces the
        two failures every demo script hit: the figure floats (hips placed at
        the given y, but the entity origin is the HIPS — feet hang below it),
        and walk/run advance position_offset_x forever with no camera, so the
        character exits frame and the rest of the video is blank.

        Only fills in what the scene didn't specify: an explicit camera or a
        y set below the floor line is left alone.
        """
        floor_y = self.height - 20

        for ent_id, comps in self.entities.items():
            phys, pos = comps.get('physics'), comps.get('position')
            if phys and pos and pos.y <= 0:
                pos.y = floor_y - phys.ground_offset

        if any(c.get('camera') for c in self.entities.values()):
            return

        chars = [e for e, c in self.entities.items() if c.get('procedural_player')]
        if not chars:
            return
        # follow_y off: the floor is fixed, so tracking vertical bob would
        # make the ground slide up and down under the character's feet
        self.create_entity({'camera': Camera(target_entity=chars[0],
                                             smooth_speed=0.0, follow_y=False,
                                             current_y=self.height / 2),
                            'name': 'auto_cam'})

    def render(self, output_path: str = "output.mp4", duration: float = 3.0) -> dict:
        """Render the current scene to a video file.
        
        Args:
            output_path: Output file path
            duration: Duration in seconds (must be > 0)
            
        Returns:
            Render info dict
        """
        if duration <= 0:
            raise ValueError("duration must be > 0")
        
        dt = 1.0 / self.fps
        total_frames = int(duration * self.fps)

        # Auto-wire timeline events to entity actions
        self.timeline.on("*", self._timeline_handler)

        # Start idle on all characters that have a procedural player
        for ent_id, player in self.get_entities_with('procedural_player'):
            self.generators.start_action(player, 'idle')

        self._auto_frame_characters()

        self._export.start()
        
        for frame in range(total_frames):
            frame_img = self.step(dt)
            self._export.submit_frame(frame_img)
        
        path, info = self._export.finish(output_path)
        return info
    
    def load_and_render_script(self, script_path: str, output_path: str = "output.mp4") -> dict:
        """Load a .sf script, build the scene, and render.
        
        Args:
            script_path: Path to .sf script file
            output_path: Output video path
            
        Returns:
            Render info dict
        """
        # Parse the script
        from compiler import Lexer, Parser, CodeGenerator
        
        with open(script_path) as f:
            text = f.read()
        
        lexer = Lexer(text)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        script_ast = parser.parse()
        cg = CodeGenerator()
        scene_data = cg.generate(script_ast)
        
        # Build scene from parsed data
        entity_map = {}  # name -> entity_id
        
        for char in scene_data.get('characters', []):
            head_color = char['appearance'].get('head_color', '#FFD700')
            body_color = char['appearance'].get('body_color', '#333')
            shirt_color = char['appearance'].get('shirt_color', '#2E86DE')
            pants_color = char['appearance'].get('pants_color', '#1B2A4A')
            shoe_color = char['appearance'].get('shoe_color', '#8B4513')
            skin_color = char['appearance'].get('skin_color', '#FFDAB9')
            scale = char.get('scale', 1.0)
            pos = char.get('position', {'x': 400, 'y': 400})
            eid = self.create_character(
                name=char['name'],
                x=pos['x'],
                y=0.0,  # start at 0, let _auto_frame_characters ground it
                head_color=head_color,
                body_color=body_color,
                shirt_color=shirt_color,
                pants_color=pants_color,
                shoe_color=shoe_color,
                skin_color=skin_color,
                scale=scale,
            )
            entity_map[char['name']] = eid
        
        # Load timeline
        timeline_data = scene_data.get('timeline', {})

        # Create camera entities from scene data
        for cam_def in scene_data.get('cameras', []):
            target_eid = entity_map.get(cam_def.get('follow'))
            cam = Camera(target_entity=target_eid, zoom=cam_def.get('zoom', 1.0),
                         follow_y=False, current_y=self.height / 2)
            # ponytail: start the follow camera at the target's x so the
            # first frame is centered instead of panning in from the edge
            if target_eid is not None:
                cam.current_x = self.entities[target_eid]['position'].x
            self.create_entity({'camera': cam, 'name': cam_def['name']})

        # Convert action definitions from .sf into ActionClip objects
        # Each keyframe is expanded to include ALL bones (missing = idle pose)
        import math
        from engine.core.components import ActionClip, Keyframe as Kf
        from engine.animation.generators import gen_idle

        # Get idle pose as base for filling missing bones
        idle_pose_deg = {}
        idle_pose_rad = gen_idle(0.0, {})
        for bone_name, angle_rad in idle_pose_rad.items():
            idle_pose_deg[bone_name] = math.degrees(angle_rad)

        action_clips = {}
        for act_def in scene_data.get('actions', []):
            bone_kfs = {}
            # Expand each keyframe to include ALL bones
            for t, partial_pose in act_def['keyframes']:
                full_pose = dict(idle_pose_deg)   # start with idle
                full_pose.update(partial_pose)     # override with user's values
                for bone_name, angle_deg in full_pose.items():
                    if bone_name not in bone_kfs:
                        bone_kfs[bone_name] = []
                    bone_kfs[bone_name].append(Kf(
                        time=t,
                        angle=math.radians(angle_deg),
                    ))
            clip = ActionClip(
                name=act_def['name'],
                duration=act_def['duration'],
                loop=act_def.get('loop', False),
                bone_keyframes=bone_kfs,
            )
            action_clips[act_def['name']] = clip
            # Attach to every character
            for eid in entity_map.values():
                anim = self.entities[eid].get('animation_player')
                if anim:
                    anim.clips[act_def['name']] = clip

        # Adjust ground_y based on character height so legs stay visible
        for eid in entity_map.values():
            skel = self.entities[eid].get('skeleton')
            if skel:
                # Find foot bones — the lowest-reach bone pair
                from engine.animation.skeleton import compute_forward_kinematics
                # Compute FK at origin to measure foot offset from hips
                compute_forward_kinematics(skel, 0, 0)
                max_foot_y = 0
                for pos in skel.world_positions:
                    if pos[1] > max_foot_y:
                        max_foot_y = pos[1]
                # ground_y = where hips stop = bottom_margin - leg_length
                self.physics.ground_y = self.height - 20 - max_foot_y
                break  # use first character for now
        if timeline_data:
            self.timeline.load_timeline(timeline_data)
            # Wire up timeline events to actions
            self.timeline.on("*", self._timeline_handler)
            
            # Calculate duration from timeline
            max_time = 0
            for events in timeline_data.values():
                for ev in events:
                    if ev['time'] > max_time:
                        max_time = ev['time']
            duration = max_time + 1.0  # add buffer
        else:
            duration = 3.0
        
        # Render
        return self.render(output_path, duration=duration)
    
    def _timeline_handler(self, time, action, params):
        """Handle timeline events: parse 'entity.action' and dispatch.

        Supports character actions (fighter.jump) and camera actions
        (camera.zoom_to, camera.shake, camera.follow, camera.activate, camera.pan_to).
        """
        parts = action.split(".", 1)
        if len(parts) < 2:
            return
        entity_name, action_name = parts

        # Global scene controls: bg.set(color="#...") changes background
        if entity_name == 'bg' and action_name == 'set' and 'color' in params:
            self.bg_color = str(params['color'])
            return

        # Find entity by name
        for eid, comps in self.entities.items():
            if comps.get('name') == entity_name:
                # Camera actions
                if 'camera' in comps:
                    cam = comps['camera']
                    if action_name == 'zoom_to' and 'zoom' in params:
                        cam.target_zoom = float(params['zoom'])
                    elif action_name == 'shake':
                        cam.shake_intensity = float(params.get('intensity', 10))
                        cam.shake_duration = float(params.get('duration', 0.3))
                        cam.shake_timer = cam.shake_duration
                    elif action_name == 'follow' and 'target' in params:
                        target_name = params['target']
                        for tid, tcomps in self.entities.items():
                            if tcomps.get('name') == target_name:
                                cam.target_entity = tid
                                break
                    elif action_name == 'activate':
                        for cid, ccomps in self.entities.items():
                            if 'camera' in ccomps:
                                ccomps['camera'].active = False
                        cam.active = True
                    elif action_name == 'pan_to':
                        cam.target_entity = None
                        if 'x' in params:
                            cam.current_x = float(params['x'])
                        if 'y' in params:
                            cam.current_y = float(params['y'])
                    elif action_name == 'reset':
                        cam.target_zoom = None
                        cam.zoom = 1.0
                        cam.shake_timer = 0
                        cam.shake_intensity = 0
                    break

                # Character actions
                # Dialogue: show a speech bubble above the character for a duration
                if action_name == 'speak':
                    dlg = comps.get('dialogue')
                    if dlg:
                        dlg.active_text = params.get('text', '')
                        dlg.progress = float(params.get('duration', 2.5))  # countdown timer
                    break

                self.play_action(eid, action_name)

                if 'x' in params:
                    pos = comps.get('position')
                    if pos:
                        pos.x = float(params['x'])
                if 'y' in params:
                    pos = comps.get('position')
                    if pos:
                        pos.y = float(params['y'])
                if 'speed' in params:
                    vel = comps.get('velocity')
                    if vel:
                        vel.vx = float(params['speed'])
                break
