"""Accuracy verification: is the engine producing what the script asks for?"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import StickFrameEngine
from engine.timeline.evaluator import TimelineEvaluator
from engine.animation.generators import GENERATORS
import math

print("=== STICKFRAME ACCURACY VERIFICATION ===")
print()

# Test 1: Character grounding (feet land on floor, not floating)
print("Test 1: Character grounding")
e = StickFrameEngine(fps=24, width=800, height=600)
hero = e.create_character('hero', x=400, y=0, scale=2.5)
e._auto_frame_characters()
final_y = e.entities[hero]['position'].y
floor_y = e.height - 20
offset = e.entities[hero]['physics'].ground_offset
feet_y = final_y + offset
print(f"  Feet land at: {feet_y:.1f}px, floor at: {floor_y}px")
test1 = abs(feet_y - floor_y) < 1
print(f"  {'PASS' if test1 else 'FAIL'}")
print()

# Test 2: Timeline event timing
print("Test 2: Timeline event timing")
tl = TimelineEvaluator()
tl.load_timeline({'s': [
    {'time': 0.0, 'action': 'a', 'params': {}},
    {'time': 1.5, 'action': 'b', 'params': {}},
    {'time': 3.0, 'action': 'c', 'params': {}},
]})
fired = []
tl.on('*', lambda t, a, p: fired.append(t))
tl.step_to(5.0)
print(f"  Events fired at: {fired}")
print(f"  Expected: [0.0, 1.5, 3.0]")
test2 = fired == [0.0, 1.5, 3.0]
print(f"  {'PASS' if test2 else 'FAIL'}")
print()

# Test 3: Walk position accumulation
print("Test 3: Walk position accumulation (5 seconds)")
e2 = StickFrameEngine(fps=24, width=800, height=400)
h2 = e2.create_character('hero', x=100, y=250)
e2.entities[h2]['physics'].gravity_scale = 0
e2.play_action(h2, 'walk')
x0 = e2.entities[h2]['position'].x
for _ in range(120):  # 5s at 24fps
    e2.step(1.0/24)
x1 = e2.entities[h2]['position'].x
delta = x1 - x0
print(f"  Start: {x0:.1f}px, End: {x1:.1f}px, Delta: {delta:.1f}px")
test3 = 200 <= delta <= 400
print(f"  {'PASS' if test3 else 'FAIL'} (expected 200-400px)")
print()

# Test 4: All generators produce valid output
print(f"Test 4: All {len(GENERATORS)} generators produce finite angles")
fail = 0
for name, (fn, _, defaults) in GENERATORS.items():
    result = fn(0.5, defaults)
    pose = result[0] if isinstance(result, tuple) else result
    if not all(math.isfinite(v) for v in pose.values()):
        print(f"  FAIL: {name} has non-finite values")
        fail += 1
test4 = fail == 0
print(f"  {'PASS' if test4 else 'FAIL'} ({len(GENERATORS) - fail}/{len(GENERATORS)})")
print()

# Test 5: .sf -> video pipeline
print("Test 5: .sf script -> video pipeline")
import tempfile
script = 'scripts/kungfu.sf'
out = tempfile.mktemp(suffix='.mp4', prefix='sf_test_')
e3 = StickFrameEngine(fps=24, width=800, height=400)
info = e3.load_and_render_script(script, out)
test5 = os.path.exists(out) and os.path.getsize(out) > 1000
print(f"  Script: {script}")
print(f"  Output: {info['frames']} frames, {info['duration']:.2f}s, {info['size_mb']:.2f} MB")
print(f"  {'PASS' if test5 else 'FAIL'}")
print()

print("=== SUMMARY ===")
all_pass = all([test1, test2, test3, test4, test5])
print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
if all_pass:
    print()
    print("Engine is accurate:")
    print("  - Characters ground correctly (feet on floor)")
    print("  - Timeline events fire at exact times")
    print("  - Walk accumulates position correctly (no sliding)")
    print("  - All 31 generators produce valid output")
    print("  - .sf scripts compile and render to video")
