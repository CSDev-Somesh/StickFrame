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
    TimelineEvent, ProceduralPlayer, DialogueState, Facing,
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
        # Mocap action library: name -> ActionClip, loaded from .bvh files.
        # These resolve before procedural generators (play_action checks the
        # AnimationPlayer's clips first), so a .sf can use mocap action names
        # as if they were built-ins.
        self.mocap_clips: dict = {}
    
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

        eid = self.create_entity({
            'position': Position(x, y),
            'velocity': Velocity(0, 0),
            'skeleton': skeleton,
            'appearance': appearance,
            'procedural_player': player,
            'animation_player': anim_player,
            'renderable': Renderable(visible=True, z_order=0),
            'physics': phys,
            'dialogue': DialogueState(),
            'facing': Facing(direction='right'),
            'name': name,
        })
        # Attach any mocap library so this character can play mocap actions too
        if self.mocap_clips:
            anim_player.clips.update(self.mocap_clips)
        return eid
    
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
        
        # Read the script leniently: prefer UTF-8 (what our web backend writes),
        # but fall back to the Windows locale (cp1252) for hand-authored files
        # saved with default encoders — strict UTF-8 would reject em-dashes
        # and accents that are perfectly readable in comments.
        raw = open(script_path, "rb").read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        
        lexer = Lexer(text)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        script_ast = parser.parse()
        cg = CodeGenerator()
        scene_data = cg.generate(script_ast)

        # Execute a `script:` block (the creative programming layer) to
        # generate timeline events, merged under their own track. Runs BEFORE
        # validation so a bug in the user's script fails loudly here.
        if scene_data.get('script'):
            from compiler.interpreter import interpret
            script_events = interpret(scene_data['script'])
            if script_events:
                scene_data.setdefault('timeline', {})['script'] = script_events

        # Validate the parsed scene BEFORE building — a typo fires or entity
        # name otherwise renders a silently wrong (or blank) video. Fail loud
        # with a precise message instead.
        self._validate_scene(scene_data)

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

        # Attach any mocap action library to every character so .sf timelines
        # can reference mocap action names (resolved before procedural gens).
        if self.mocap_clips:
            for eid in entity_map.values():
                anim = self.entities[eid].get('animation_player')
                if anim:
                    anim.clips.update(self.mocap_clips)

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
    
    def load_mocap_library(self, folder: str, loops=None, view: str = "front",
                           every_n: int = 1) -> dict:
        """Load .bvh files from a folder into the engine's mocap action library.

        Mocap action names can then be used directly in .sf timelines (e.g.
        ``hero.spin_kick`` if a spin_kick.bvh was loaded). They resolve via
        the keyframe AnimationPlayer, taking priority over procedural
        generators.

        Args:
            folder: Directory containing .bvh files (one per action).
            loops: Optional list of clip names that should loop.
            view: 'front' or 'side' mocap projection.
            every_n: Subsample factor (1 = keep every frame).

        Returns:
            The loaded {name: ActionClip} library.
        """
        from engine.mocap.importer import load_mocap_library as _load
        self.mocap_clips.update(_load(folder, loop_names=loops, view=view, every_n=every_n))
        # Attach to any existing characters so they can play the new actions
        for eid, comps in self.entities.items():
            anim = comps.get('animation_player')
            if anim:
                for name, clip in self.mocap_clips.items():
                    anim.clips[name] = clip
        return dict(self.mocap_clips)

    def _validate_scene(self, scene_data: dict) -> None:
        """Check a parsed scene for accuracy-killing mistakes before rendering.

        Raises ValueError with a precise, actionable message on the first
        problem found. Detects:
          1. Timeline actions referencing an entity that doesn't exist
          2. Unknown action names (not in the generator library)
          3. Timeline events out of chronological order
          4. Camera actions on a non-camera entity (and vice versa)

        Without this, a typo silently produces a frozen character or a blank
        video — the exact accuracy failures a movie script can't tolerate.
        """
        from engine.animation.generators import GENERATORS

        # Actions that work on entities but aren't procedural generators
        # (camera controls + dialogue). Validated against GENERATORS only
        # when the target is a character.
        NON_GENERATOR_ACTIONS = {
            'zoom_to', 'follow', 'activate', 'pan_to', 'reset', 'shake',
            'speak', 'set', 'turn',
        }

        # 1. Known entity names + which are cameras.
        # 'bg' is a pseudo-entity for global scene controls (bg.set color=...)
        # handled directly in the timeline handler — always valid.
        entity_names = {c.get('name') for c in scene_data.get('characters', [])}
        camera_names = {c.get('name') for c in scene_data.get('cameras', [])}
        entity_names |= camera_names | {'bg'}

        timeline = scene_data.get('timeline', {})
        for scene_name, events in timeline.items():
            prev_time = -1.0
            for ev in events:
                t = float(ev.get('time', 0))
                action_str = str(ev.get('action', ''))
                action_name = action_str.split('.', 1)[-1] if '.' in action_str else action_str
                entity_name = action_str.split('.', 1)[0] if '.' in action_str else ''

                # 2. Chronological order
                if t < prev_time:
                    raise ValueError(
                        f"Timeline '{scene_name}': event at {t:.2f}s comes after "
                        f"{prev_time:.2f}s — events must be in time order."
                    )
                prev_time = t

                # 3. Entity must exist
                if entity_name and entity_name not in entity_names:
                    raise ValueError(
                        f"Timeline '{scene_name}' @ {t:.2f}s: unknown entity "
                        f"'{entity_name}'. Defined entities: {sorted(entity_names)}"
                    )

                # 4. Action must be known — camera actions on a camera entity
                #    are handled by the timeline handler, not the generators.
                if entity_name in camera_names:
                    if action_name not in ('zoom_to', 'follow', 'activate',
                                           'pan_to', 'reset', 'shake'):
                        raise ValueError(
                            f"Timeline '{scene_name}' @ {t:.2f}s: unknown camera "
                            f"action '{action_name}' on '{entity_name}'. "
                            "Camera actions: zoom_to, follow, activate, pan_to, reset, shake"
                        )
                elif action_name and action_name not in GENERATORS and \
                        action_name not in NON_GENERATOR_ACTIONS and \
                        action_name not in self.mocap_clips:
                    raise ValueError(
                        f"Timeline '{scene_name}' @ {t:.2f}s: unknown action "
                        f"'{action_name}' on '{entity_name}'. "
                        f"Available: {sorted(GENERATORS.keys())[:8]}, +mocap: "
                        f"{sorted(self.mocap_clips)[:8]} ({len(GENERATORS)} gens, "
                        f"{len(self.mocap_clips)} mocap)"
                    )

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
                        # Following an entity cancels any pan target
                        cam.pan_target_x = None
                        cam.pan_target_y = None
                    elif action_name == 'activate':
                        for cid, ccomps in self.entities.items():
                            if 'camera' in ccomps:
                                ccomps['camera'].active = False
                        cam.active = True
                    elif action_name == 'pan_to':
                        # Smooth pan: set pan targets and let CameraSystem lerp
                        # toward them (previous behavior snapped instantly).
                        cam.target_entity = None
                        cam.pan_target_x = float(params['x']) if 'x' in params else None
                        cam.pan_target_y = float(params['y']) if 'y' in params else None
                    elif action_name == 'reset':
                        cam.target_zoom = None
                        cam.zoom = 1.0
                        cam.shake_timer = 0
                        cam.shake_intensity = 0
                        cam.pan_target_x = None
                        cam.pan_target_y = None
                    break

                # Character actions
                # Dialogue: show a speech bubble above the character for a duration
                if action_name == 'speak':
                    dlg = comps.get('dialogue')
                    if dlg:
                        dlg.active_text = params.get('text', '')
                        dlg.progress = float(params.get('duration', 2.5))  # countdown timer
                    break

                # CRITICAL FIX: Stop any currently playing action before starting new one
                # This ensures timeline events cleanly switch between actions instead of
                # having multiple actions play simultaneously (walk + punch = broken)
                proc_player = comps.get('procedural_player')
                anim_player = comps.get('animation_player')
                if proc_player and proc_player.playing:
                    proc_player.playing = False
                if anim_player and anim_player.playing:
                    anim_player.playing = False

                # Special handling for 'turn' — flip facing direction, then
                # play the pivot animation. The renderer mirrors the skeleton
                # so the character visually turns around.
                if action_name == 'turn':
                    facing = comps.get('facing')
                    if facing:
                        facing.direction = 'left' if facing.direction == 'right' else 'right'
                    self.play_action(eid, action_name)
                    break

                self.play_action(eid, action_name)

                vel = comps.get('velocity')

                # Velocity-based movement for locomotion actions with an x= target.
                # The character WALKS/RUNS to the target (not teleport), at a speed
                # matching the action. Stops at the target via Engine.step()'s
                # stop-at-target check.
                if action_name in ('walk', 'run', 'sprint', 'sneak') and 'x' in params:
                    pos = comps.get('position')
                    if pos and vel:
                        target_x = float(params['x'])
                        distance = target_x - pos.x
                        speeds = {
                            'walk': 100,    # pixels per second
                            'run': 200,
                            'sprint': 300,
                            'sneak': 50
                        }
                        speed = speeds.get(action_name, 100)
                        vel.vx = speed if distance > 0 else -speed
                        # Store target + signed speed so Engine.step() can
                        # keep the velocity (friction decays vx every frame,
                        # which would stall the character well short of the
                        # target) and stop when reached.
                        comps['_movement_target'] = target_x
                        comps['_movement_speed'] = speed if distance > 0 else -speed
                        # Suppress the generator's own X stride offset so the
                        # character doesn't double-move (velocity + stride)
                        proc = comps.get('procedural_player')
                        if proc:
                            proc.velocity_move = True
                        # Auto-face the direction of travel
                        facing = comps.get('facing')
                        if facing:
                            facing.direction = 'right' if distance > 0 else 'left'
                    return

                # Non-movement actions still honor instant position changes
                if 'x' in params:
                    pos = comps.get('position')
                    if pos:
                        pos.x = float(params['x'])
                if 'y' in params:
                    pos = comps.get('position')
                    if pos:
                        pos.y = float(params['y'])
                if 'speed' in params:
                    if vel:
                        vel.vx = float(params['speed'])
                break
