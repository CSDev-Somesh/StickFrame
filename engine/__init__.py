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
    TimelineEvent,
)
from engine.core.systems import Engine, AnimationSystem
from engine.animation.skeleton import build_bipedal_skeleton, compute_forward_kinematics
from engine.animation.actions import get_action, BUILTIN_ACTIONS
from engine.pipeline.export import ExportPipeline


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
        scale: float = 1.0,
    ) -> int:
        """Create a stickman character in the scene.
        
        Args:
            name: Character identifier (used for timeline events)
            x: Initial X position
            y: Initial Y position
            head_color: HTML color for head
            body_color: HTML color for body/limbs
            scale: Overall size multiplier
            
        Returns:
            Entity ID
        """
        skeleton = build_bipedal_skeleton(scale)
        appearance = Appearance(head_color=head_color, body_color=body_color, scale=scale)
        
        # Build animation player with all built-in actions
        anim = AnimationPlayer()
        for action_name in BUILTIN_ACTIONS:
            anim.clips[action_name] = get_action(action_name)
        anim.current_action = "idle"
        anim.playing = True
        
        return self.create_entity({
            'position': Position(x, y),
            'velocity': Velocity(0, 0),
            'skeleton': skeleton,
            'appearance': appearance,
            'animation_player': anim,
            'renderable': Renderable(visible=True, z_order=0),
            'physics': PhysicsBody(mass=1.0, is_static=False),
            'name': name,
        })
    
    def play_action(self, entity_id: int, action_name: str) -> None:
        """Start playing an action on a character.
        
        Args:
            entity_id: The entity ID
            action_name: Name of built-in action (idle, walk, jump, wave, fall, punch)
        """
        anim = self.entities[entity_id].get('animation_player')
        if anim and action_name in anim.clips:
            anim.current_action = action_name
            anim.time = 0.0
            anim.playing = True
    
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
    
    def render(self, output_path: str = "output.mp4", duration: float = 3.0) -> dict:
        """Render the current scene to a video file.
        
        Args:
            output_path: Output file path
            duration: Duration in seconds
            
        Returns:
            Render info dict
        """
        dt = 1.0 / self.fps
        total_frames = int(duration * self.fps)
        
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
        from compiler.lexer import Lexer
        from compiler.parser import Parser
        from compiler.codegen import CodeGenerator
        
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
            pos = char.get('position', {'x': 400, 'y': 400})
            eid = self.create_character(
                name=char['name'],
                x=pos['x'],
                y=pos['y'],
                head_color=head_color,
                body_color=body_color,
            )
            entity_map[char['name']] = eid
        
        # Load timeline
        timeline_data = scene_data.get('timeline', {})
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
        """Handle timeline events: parse 'entity.action' and dispatch."""
        parts = action.split(".", 1)
        if len(parts) < 2:
            return
        entity_name, action_name = parts
        
        # Find entity by name
        for eid, comps in self.entities.items():
            if comps.get('name') == entity_name:
                self.play_action(eid, action_name)
                
                # Handle position parameters
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
