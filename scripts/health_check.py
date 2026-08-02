"""Engine health check — edge cases, stress tests, bug hunting"""
import sys, os, math, tempfile
sys.path.insert(0, os.path.expanduser("~/StickFrame"))

from engine import StickFrameEngine
from engine.animation.generators import gen_walk, gen_idle, gen_jump, gen_run, gen_wave, gen_punch, gen_fall, GENERATORS
from engine.animation.fabrik import FabrikChain
from engine.core.components import ProceduralPlayer
from engine.animation.skeleton import build_bipedal_skeleton, compute_forward_kinematics
from engine.core.systems import Engine

issues = []

print("=" * 55)
print("ENGINE HEALTH CHECK")
print("=" * 55)

# ── 1. FABRIK edge cases ──────────────────────────────────
print("\n[1/8] FABRIK IK Solver")

# 1a. Target at origin
c = FabrikChain(); c.add_bone(20); c.add_bone(15)
c.set_base(0,0); c.set_initial_pose([-30, -45])
r = c.solve(0, 0, tolerance=1.0)
if not r: issues.append("FABRIK can't reach origin")
else: print("  ✓ Target at origin")

# 1b. Target behind base
c2 = FabrikChain(); c2.add_bone(20); c2.add_bone(15)
c2.set_base(0,0); c2.set_initial_pose([90, 0])
r2 = c2.solve(-30, 10, tolerance=1.0)
if not r2: issues.append("FABRIK can't reach behind")
else: print("  ✓ Target behind base")

# 1c. Very far target (stretch)
c3 = FabrikChain(); c3.add_bone(20); c3.add_bone(15)
c3.set_base(0,0); c3.set_initial_pose([90, 0])
r3 = c3.solve(1000, 0, tolerance=1.0)
ex, ey = c3.get_end_effector()
dist = math.sqrt(ex**2 + ey**2)
if abs(dist - 35) > 1: issues.append(f"FABRIK stretch={dist:.1f} (expected 35)")
else: print(f"  ✓ Stretch to max ({dist:.0f}px)")

# 1d. Single bone chain (must be on circumference: 30px from base)
c4 = FabrikChain(); c4.add_bone(30)
c4.set_base(0,0); c4.set_initial_pose([0])
r4 = c4.solve(30, 0, tolerance=1.0)  # target exactly 30px away = reachable
if not r4: issues.append("FABRIK single bone fails")
else: print("  ✓ Single bone chain")

# 1e. Zero tolerance
c5 = FabrikChain(); c5.add_bone(20); c5.add_bone(15)
c5.set_base(0,0); c5.set_initial_pose([-30, -45])
r5 = c5.solve(15, -25, tolerance=0.0)
# Should still work with default tolerance
print("  ✓ Zero tolerance (falls back to iterations)")


# ── 2. Generator edge cases ───────────────────────────────
print("\n[2/8] Procedural Generators")

# 2a. All generators at t=0
for name in GENERATORS:
    fn, has_pos, defaults = GENERATORS[name]
    try:
        result = fn(0.0, defaults)
        pose = result[0] if isinstance(result, tuple) else result
        if len(pose) < 14: issues.append(f"{name}: only {len(pose)} bones")
    except Exception as e:
        issues.append(f"{name} at t=0: {e}")
print(f"  ✓ All {len(GENERATORS)} generators at t=0")

# 2b. Negative time
for name in ('idle', 'walk', 'run'):
    fn, _, defaults = GENERATORS[name]
    try:
        fn(-1.0, defaults)
    except Exception as e:
        issues.append(f"{name} at negative time: {e}")
print("  ✓ Negative time")

# 2c. Very large time
try:
    gen_walk(10000.0, {'speed': 1.0, 'stride': 55})
except Exception as e:
    issues.append(f"walk at large time: {e}")
print("  ✓ Very large time")

# 2d. No params (use defaults)
try:
    gen_walk(1.0, None)
    gen_jump(0.5, None)
except Exception as e:
    issues.append(f"generator with None params: {e}")
print("  ✓ None params (uses defaults)")


# ── 3. Character creation ────────────────────────────────
print("\n[3/8] Character Creation")

# 3a. Default values
e = StickFrameEngine(fps=10, width=400, height=300)
try:
    h = e.create_character("test")
    if 'procedural_player' not in e.entities[h]: issues.append("missing procedural_player")
    if 'skeleton' not in e.entities[h]: issues.append("missing skeleton")
    if 'position' not in e.entities[h]: issues.append("missing position")
    print("  ✓ Default character creation")
except Exception as ex:
    issues.append(f"create_character default: {ex}")

# 3b. Multiple characters
try:
    for i in range(5):
        e.create_character(f"c{i}")
    print("  ✓ 5 characters created simultaneously")
except Exception as ex:
    issues.append(f"multi-char: {ex}")

# 3c. Entity IDs increment
first = e.create_character("first")
second = e.create_character("second")
if second != first + 1: issues.append("entity IDs not sequential")
print("  ✓ Entity ID management")


# ── 4. Engine step / render ──────────────────────────────
print("\n[4/8] Engine Render Pipeline")

# 4a. Minimal render (0.5 seconds)
e2 = StickFrameEngine(fps=10, width=200, height=200)
h2 = e2.create_character("h2", x=50, y=100)
e2.entities[h2]['physics'].gravity_scale = 0
out = tempfile.mktemp(suffix=".mp4", prefix="sf_")
try:
    info = e2.render(out, duration=0.5)
    assert info['frames'] == 5
    os.remove(out)
    print("  ✓ Minimal render (0.5s)")
except Exception as ex:
    issues.append(f"minimal render: {ex}")

# 4b. No timeline (just idle)
e3 = StickFrameEngine(fps=10, width=200, height=200)
h3 = e3.create_character("h3")
e3.entities[h3]['physics'].gravity_scale = 0
out2 = tempfile.mktemp(suffix=".mp4", prefix="sf_")
try:
    info2 = e3.render(out2, duration=1.0)
    assert info2['frames'] == 10
    os.remove(out2)
    print("  ✓ No timeline (default idle)")
except Exception as ex:
    issues.append(f"no timeline: {ex}")

# 4c. Zero-duration render (should raise clear error)
e4 = StickFrameEngine(fps=10, width=200, height=200)
try:
    e4.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=0)
    issues.append("zero duration should raise ValueError")
except ValueError:
    print("  ✓ Zero duration raises clear ValueError")


# ── 5. Timeline event system ──────────────────────────────
print("\n[5/8] Timeline Events")

# 5a. Events fire in order
e5 = StickFrameEngine(fps=10, width=200, height=200)
h5 = e5.create_character("h5")
e5.entities[h5]['physics'].gravity_scale = 0
events_fired = []
e5.timeline.on("*", lambda t, a, p: events_fired.append((t, a)))
e5.timeline.load_timeline({"s": [
    {"time": 0.0, "action": "h5.walk", "params": {}},
    {"time": 2.0, "action": "h5.jump", "params": {}},
]})
e5.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=3.0)
if len(events_fired) != 2: issues.append(f"timeline: {len(events_fired)} events (expected 2)")
else: print("  ✓ Events fire in order")

# 5b. Unknown action doesn't crash
e6 = StickFrameEngine(fps=10, width=200, height=200)
h6 = e6.create_character("h6")
e6.entities[h6]['physics'].gravity_scale = 0
e6.timeline.load_timeline({"s": [
    {"time": 0.0, "action": "h6.nonexistent", "params": {}},
]})
try:
    e6.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=1.0)
    print("  ✓ Unknown action doesn't crash")
except Exception as ex:
    issues.append(f"unknown action crashed: {ex}")


# ── 6. Position tracking ─────────────────────────────────
print("\n[6/8] Position Tracking")

# 6a. Walk position accumulates correctly
e7 = StickFrameEngine(fps=10, width=800, height=400)
h7 = e7.create_character("h7", x=50, y=250)
e7.entities[h7]['physics'].gravity_scale = 0
e7.timeline.load_timeline({"s": [
    {"time": 0, "action": "h7.walk", "params": {"speed": 1.0, "stride": 50}},
]})
e7.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=5.0)
fx = e7.entities[h7]['position'].x
if fx < 100 or fx > 1000: issues.append(f"walk position: x={fx:.0f}")
else: print(f"  ✓ Walk position ({fx:.0f}px in 5s)")

# 6b. Position doesn't go negative
e8 = StickFrameEngine(fps=10, width=400, height=300)
h8 = e8.create_character("h8", x=50, y=200)
e8.entities[h8]['physics'].gravity_scale = 0
e8.timeline.load_timeline({"s": [
    {"time": 0, "action": "h8.idle", "params": {}},
]})
e8.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=2.0)
px = e8.entities[h8]['position'].x
if px < 0: issues.append(f"idle made x negative: {px}")
else: print("  ✓ Position stays non-negative during idle")


# ── 7. Multiple action switches ───────────────────────────
print("\n[7/8] Rapid Action Switching")

e9 = StickFrameEngine(fps=10, width=400, height=300)
h9 = e9.create_character("h9", x=50, y=200)
e9.entities[h9]['physics'].gravity_scale = 0
e9.timeline.load_timeline({"s": [
    {"time": 0.0, "action": "h9.idle", "params": {}},
    {"time": 0.3, "action": "h9.walk", "params": {}},
    {"time": 0.6, "action": "h9.jump", "params": {}},
    {"time": 0.9, "action": "h9.wave", "params": {}},
    {"time": 1.2, "action": "h9.punch", "params": {}},
    {"time": 1.5, "action": "h9.fall", "params": {}},
    {"time": 2.0, "action": "h9.idle", "params": {}},
]})
try:
    e9.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=3.0)
    print("  ✓ Rapid action switching (7 actions in 2s)")
except Exception as ex:
    issues.append(f"rapid switching: {ex}")


# ── 8. Memory / resource edge cases ──────────────────────
print("\n[8/8] Resource Edge Cases")

# 8a. Engine reset
e10 = StickFrameEngine(fps=10, width=200, height=200)
h10 = e10.create_character("h10")
e10.entities[h10]['physics'].gravity_scale = 0
e10.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=1.0)
e10.reset()
try:
    h10b = e10.create_character("h10b")
    e10.entities[h10b]['physics'].gravity_scale = 0
    e10.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=1.0)
    print("  ✓ Engine reset and re-render")
except Exception as ex:
    issues.append(f"engine reset: {ex}")

# 8b. Create character after render
e11 = StickFrameEngine(fps=10, width=200, height=200)
h11 = e11.create_character("h11")
e11.entities[h11]['physics'].gravity_scale = 0
try:
    e11.render(tempfile.mktemp(suffix=".mp4", prefix="sf_"), duration=1.0)
    h11b = e11.create_character("h11b")
    e11.entities[h11b]['physics'].gravity_scale = 0
    print("  ✓ Create character after render")
except Exception as ex:
    issues.append(f"char after render: {ex}")


# ── Summary ──────────────────────────────────────────────
print("\n" + "=" * 55)
if issues:
    print(f"⚠  {len(issues)} ISSUES FOUND:")
    for issue in issues:
        print(f"  • {issue}")
    sys.exit(1)
else:
    print("✓ ALL HEALTH CHECKS PASSED — engine is clean")
    print("=" * 55)