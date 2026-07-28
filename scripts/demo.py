"""Demo: Hello StickFrame — basic engine test with 2 characters"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import StickFrameEngine
from engine.animation.actions import get_action

def main():
    print("=" * 50)
    print("StickFrame Engine — Demo")
    print("=" * 50)
    
    # Create engine
    e = StickFrameEngine(fps=24, width=640, height=480)
    print(f"Engine created: {e.fps}fps, {e.width}x{e.height}")
    
    # Create hero — raised up, gravity disabled for initial idle
    hero = e.create_character("hero", x=100, y=300, head_color="#FFD700", body_color="#333")
    print(f"Hero created: entity {hero}")
    # Disable gravity so they stand still
    e.entities[hero]['physics'].gravity_scale = 0.0
    
    # Create villain
    villain = e.create_character("villain", x=500, y=300, head_color="#8B0000", body_color="#4A0000")
    print(f"Villain created: entity {villain}")
    e.entities[villain]['physics'].gravity_scale = 0.0
    
    # Test: render a single frame to verify everything works
    print("\nRendering test frame...")
    e.play_action(hero, "idle")
    e.play_action(villain, "idle")
    
    dt = 1.0 / e.fps
    for i in range(10):
        frame = e.step(dt)
    
    frame.save("/tmp/sf_test_frame.png")
    print(f"Test frame saved: /tmp/sf_test_frame.png ({frame.size})")
    
    # Test action system
    print("\nTesting actions...")
    for name in ['idle', 'walk', 'jump', 'wave', 'punch', 'fall']:
        clip = get_action(name)
        print(f"  {name:8s}: {len(clip.bone_keyframes)} bones keyframed, {clip.duration}s, loop={clip.loop}")
    
    # Full render: 5-second demo
    print(f"\nRendering 5-second demo...")
    e.reset()
    
    # Recreate scene — with gravity off, better spacing
    hero = e.create_character("hero", x=100, y=300, head_color="#FFD700")
    e.entities[hero]['physics'].gravity_scale = 0.0
    villain = e.create_character("villain", x=500, y=300, head_color="#8B0000", body_color="#4A0000")
    e.entities[villain]['physics'].gravity_scale = 0.0
    
    # Timeline
    e.timeline.load_timeline({
        "scene1": [
            {"time": 0.0, "action": "hero.idle", "params": {}},
            {"time": 0.0, "action": "villain.idle", "params": {}},
            {"time": 1.0, "action": "hero.wave", "params": {}},
            {"time": 2.0, "action": "villain.wave", "params": {}},
            {"time": 3.0, "action": "hero.jump", "params": {}},
            {"time": 3.5, "action": "villain.punch", "params": {}},
            {"time": 4.0, "action": "villain.idle", "params": {}},
            {"time": 4.5, "action": "hero.idle", "params": {}},
        ]
    })
    e.timeline.on("*", lambda t, a, p: print(f"  [timeline] {t:.1f}s: {a}"))
    
    output = "sf_demo.mp4"
    info = e.render(output, duration=5.0)
    
    print(f"\n{'=' * 50}")
    print(f"Video rendered: {output}")
    print(f"  Frames: {info['frames']}")
    print(f"  Duration: {info['duration']:.1f}s")
    print(f"  Size: {info['size_mb']:.1f} MB")
    print(f"{'=' * 50}")

if __name__ == '__main__':
    main()
