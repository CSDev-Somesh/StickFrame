"""Dance demo — walk 3 steps, jump, fall back. Pure engine API, no new code."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import StickFrameEngine

e = StickFrameEngine(fps=24, width=800, height=400)
hero = e.create_character("hero", x=80, y=280, head_color="#FFD700")
e.entities[hero]['physics'].gravity_scale = 0

# Timeline: walk → jump → fall back → idle (dance sequence)
e.timeline.load_timeline({
    "dance": [
        {"time": 0.0,  "action": "hero.idle", "params": {}},
        {"time": 0.5,  "action": "hero.walk", "params": {"speed": 1.0, "stride": 50}},
        {"time": 3.5,  "action": "hero.jump", "params": {"height": 55}},
        {"time": 4.5,  "action": "hero.fall", "params": {}},
        {"time": 5.5,  "action": "hero.idle", "params": {}},
    ]
})

output = "/home/kali/dance_demo.mp4"
info = e.render(output, duration=7.0)
print(f"Done: {info['frames']} frames, {info['duration']}s, {os.path.getsize(output)} bytes")
print(f"Final pos: ({e.entities[hero]['position'].x:.0f}, {e.entities[hero]['position'].y:.0f})")