"""End-to-end procedural engine test — all actions, single engine.render() call"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import StickFrameEngine
from engine.animation.generators import generator_names

def main():
    print("=" * 55)
    print("StickFrame — Procedural Engine E2E Test")
    print("=" * 55)
    
    # Create engine
    fps = 24
    e = StickFrameEngine(fps=fps, width=800, height=400)
    
    # Create one character
    hero = e.create_character("hero", x=50, y=280, head_color="#FFD700")
    e.entities[hero]['physics'].gravity_scale = 0
    
    print(f"Character created: entity {hero}")
    print(f"Available generators: {generator_names()}")
    
    # Load timeline with ALL actions
    timeline = {
        "demo": [
            {"time": 0.0, "action": "hero.idle", "params": {}},
            {"time": 2.0, "action": "hero.walk", "params": {"speed": 1.2, "stride": 55}},
            {"time": 5.0, "action": "hero.run", "params": {"speed": 2.0, "stride": 80}},
            {"time": 7.0, "action": "hero.wave", "params": {}},
            {"time": 9.0, "action": "hero.jump", "params": {"height": 60}},
            {"time": 10.0, "action": "hero.punch", "params": {}},
            {"time": 10.5, "action": "hero.fall", "params": {}},
            {"time": 11.5, "action": "hero.idle", "params": {}},
        ]
    }
    e.timeline.load_timeline(timeline)
    
    # Render 12 seconds — engine handles everything
    print("\nRendering 12s demo...")
    output = os.path.join(os.path.dirname(__file__), "procedural_e2e.mp4")
    info = e.render(output, duration=12.0)
    
    print(f"\n{'=' * 55}")
    print(f"Video: {output}")
    print(f"  Frames: {info['frames']}")
    print(f"  Duration: {info['duration']:.1f}s")
    print(f"  Size: {os.path.getsize(output)} bytes")
    print(f"  Final pos: ({e.entities[hero]['position'].x:.0f}, {e.entities[hero]['position'].y:.0f})")
    print(f"{'=' * 55}")
    
    # Copy to home
    import shutil
    shutil.copy(output, "/home/kali/procedural_e2e.mp4")
    print("\nAlso saved: /home/kali/procedural_e2e.mp4")

if __name__ == '__main__':
    main()