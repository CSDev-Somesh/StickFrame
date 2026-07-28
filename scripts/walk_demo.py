"""StickFrame Walk Demo — single stickman walks across screen with Pivot-style joint nodes"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import StickFrameEngine
from engine.renderer.stickman_renderer import get_joint_positions

def main():
    print("=" * 50)
    print("StickFrame — Walk Demo")
    print("=" * 50)
    
    # Parse the .sf script and render
    sf_path = os.path.join(os.path.dirname(__file__), "walk.sf")
    
    e = StickFrameEngine(fps=24, width=800, height=400)
    
    # Parse script
    from compiler import Lexer, Parser, CodeGenerator
    
    with open(sf_path) as f:
        text = f.read()
    
    lexer = Lexer(text)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    script_ast = parser.parse()
    cg = CodeGenerator()
    scene_data = cg.generate(script_ast)
    
    print(f"Parsed: {len(scene_data['characters'])} character(s), {len(scene_data['timeline'])} scene(s)")
    
    # Create character
    char = scene_data['characters'][0]
    hero = e.create_character(
        name=char['name'],
        x=char['position']['x'],
        y=char['position']['y'],
        head_color=char['appearance'].get('head_color', '#FFD700'),
        body_color=char['appearance'].get('body_color', '#222222'),
    )
    e.entities[hero]['physics'].gravity_scale = 0.0  # no falling
    
    # Show initial joint positions
    print("\nJoint layout (relative to entity position):")
    skel = e.entities[hero]['skeleton']
    from engine.animation.skeleton import compute_forward_kinematics
    compute_forward_kinematics(skel, 0, 0)
    joints = get_joint_positions(skel, 0, 0)
    for jx, jy, label in joints:
        print(f"  {label:20s}: ({jx:6.1f}, {jy:6.1f})")
    
    # Load timeline from parsed script
    timeline_data = scene_data.get('timeline', {})
    if timeline_data:
        e.timeline.load_timeline(timeline_data)
        e.timeline.on("*", lambda t, a, p: print(f"  [timeline] {t:.1f}s: {a}"))
        
        # Walk for 4 seconds (character moves ~60px per cycle, ~300px total)
        max_time = 4.0
    else:
        max_time = 3.0
    
    print(f"\nRendering {max_time}s walk...")
    output = os.path.join(os.path.dirname(__file__), "walk_demo.mp4")
    info = e.render(output, duration=max_time)
    
    print(f"\n{'=' * 50}")
    print(f"Video: {output}")
    print(f"  Frames: {info['frames']}")
    print(f"  Duration: {info['duration']:.1f}s")
    print(f"  Size: {info['size_mb']:.1f} MB")
    
    # Final position
    final_pos = e.entities[hero]['position']
    print(f"  Character moved from (50, 250) to ({final_pos.x:.0f}, {final_pos.y:.0f})")
    print(f"  Distance: {final_pos.x - 50:.0f}px")
    print(f"{'=' * 50}")

if __name__ == '__main__':
    main()
