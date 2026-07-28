"""Procedural Walk Demo — 10 seconds, sine-wave gait, no keyframes"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import StickFrameEngine
from engine.animation.skeleton import compute_forward_kinematics
from engine.animation.procedural_walk import WalkGenerator, apply_procedural_pose
from engine.renderer.stickman_renderer import draw_stickman
from PIL import Image, ImageDraw

def main():
    print("="*50)
    print("StickFrame — Procedural Walk Demo (10s)")
    print("="*50)
    
    # Create engine
    fps = 24
    width, height = 800, 400
    e = StickFrameEngine(fps=fps, width=width, height=height)
    hero = e.create_character("hero", x=50, y=250, head_color="#FFD700")
    e.entities[hero]['physics'].gravity_scale = 0
    
    skel = e.entities[hero]['skeleton']
    gen = WalkGenerator(skel)
    renderer = e.renderer
    
    # Render frames manually so we can inject procedural poses
    import tempfile
    export_dir = tempfile.TemporaryDirectory(prefix="sf_proc_")
    frame_count = 0
    
    total_time = 10.0
    dt = 1.0 / fps
    frames_total = int(total_time * fps)
    
    from engine.pipeline.export import ExportPipeline
    export = ExportPipeline(fps=fps)
    export.start()
    
    for f in range(frames_total):
        t = f * dt
        
        # Sample procedural walk
        pose, fwd_offset, bob = gen.sample(t, speed=1.2, stride=60, step_height=12, bounce=3)
        apply_procedural_pose(skel, pose)
        
        # Update entity position
        pos = e.entities[hero]['position']
        pos.x = 50 + fwd_offset
        pos.y = 250 + bob
        
        # FK
        compute_forward_kinematics(skel, pos.x, pos.y)
        
        # Render frame
        frame = Image.new('RGB', (width, height), "#FFFFFF")
        draw = ImageDraw.Draw(frame)
        draw_stickman(draw, skel, e.entities[hero]['appearance'], pos)
        export.submit_frame(frame)
        
        if f % 24 == 0:
            print(f"  Frame {f}/{frames_total} — pos=({pos.x:.0f},{pos.y:.0f})")
    
    output = os.path.join(os.path.dirname(__file__), "procedural_walk_10s.mp4")
    path, info = export.finish(output)
    
    print(f"\n{'='*50}")
    print(f"Video: {output}")
    print(f"  Frames: {info['frames']}")
    print(f"  Duration: {info['duration']:.1f}s")
    print(f"  Size: {os.path.getsize(output)} bytes")
    print(f"  Final pos: {e.entities[hero]['position'].x:.0f}px")
    print(f"{'='*50}")

if __name__ == '__main__':
    main()