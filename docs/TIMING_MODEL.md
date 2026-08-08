# StickFrame Timing Model

**Version:** 1.0  
**Last Updated:** 2026-08-08

---

## Overview

StickFrame uses a **discrete event timeline** where events fire at exact times, regardless of action duration. This allows precise choreography but requires understanding how actions interact with timing.

---

## Timeline Execution Model

### Event Firing
Timeline events fire at **exact times** specified in the script:

```sf
timeline:
    scene test:
        0.0s  hero.wave     # Fires at exactly 0.0 seconds
        0.5s  hero.punch    # Fires at exactly 0.5 seconds
```

### Action Interruption
When a new action is scheduled while another is playing, the current action **stops immediately**:

```sf
0.0s  hero.wave     # wave duration = 1.0s
0.5s  hero.punch    # Interrupts wave after 0.5s
```

**What happens:**
- 0.0s: `wave` starts playing
- 0.5s: `wave` stops (interrupted), `punch` starts
- 0.9s: `punch` ends (duration 0.4s), auto-returns to `idle`

---

## Action Types

### Looping Actions
These actions **loop forever** until interrupted by a timeline event:

**Locomotion:**
- `idle`, `walk`, `run`, `sneak`, `sprint`

**Emotions:**
- `happy`, `sad`, `angry`, `scared`

**Continuous:**
- `dance`, `celebrate`, `tremble`, `power_pose`, `hover`, `fly`, `crawl`

### One-Shot Actions
These actions **play once** and automatically return to `idle`:

**Combat:**
- `punch`, `kick`, `uppercut`, `roundhouse_kick`, `elbow_strike`
- `block`, `dodge`, `sweep`, `slam`, `combo`

**Gestures:**
- `wave`, `point`, `clap`, `bow`, `nod`, `shake_head`, `fist_pump`

**Object Interaction:**
- `pick_up`, `put_down`, `throw`, `catch`, `push`, `pull`

**Height Changes:**
- `sit`, `stand_up`, `kneel`, `lie_down`, `get_up`, `crouch`

**Special:**
- `jump`, `fall`, `roll`, `slide`, `backflip`, `leap`, `collapse`, `get_back_up`

**Weapons:**
- `draw_weapon`, `swing_sword`, `aim_gun`, `shoot`, `reload`, `throw_shield`, `energy_blast`

---

## Action Durations

All actions have **fixed base durations** (can be modified with `speed` parameter):

| Action | Duration | Type |
|--------|----------|------|
| **Locomotion** |
| idle | 1.0s | Loop |
| walk | 0.8s | Loop |
| run | 0.6s | Loop |
| sneak | 1.0s | Loop |
| sprint | 0.5s | Loop |
| **Fast Attacks** |
| punch | 0.4s | One-shot |
| jab | 0.3s | One-shot |
| kick | 0.6s | One-shot |
| **Power Moves** |
| uppercut | 0.8s | One-shot |
| roundhouse_kick | 1.0s | One-shot |
| slam | 1.0s | One-shot |
| **Defensive** |
| block | 0.6s | One-shot |
| dodge | 0.5s | One-shot |
| **Gestures** |
| wave | 1.0s | One-shot |
| point | 0.8s | One-shot |
| clap | 1.0s | One-shot |
| bow | 1.5s | One-shot |
| **Special** |
| jump | 1.0s | One-shot |
| fall | 1.2s | One-shot |
| roll | 0.8s | One-shot |
| backflip | 1.2s | One-shot |
| **Height** |
| sit | 1.0s | One-shot |
| kneel | 0.8s | One-shot |
| lie_down | 1.5s | One-shot |
| crouch | 0.6s | One-shot |
| **Emotions** |
| happy | 1.0s | Loop |
| sad | 1.5s | Loop |
| angry | 1.0s | Loop |
| scared | 1.2s | Loop |
| celebrate | 1.5s | Loop |

---

## Best Practices

### 1. Spacing One-Shot Actions

Leave enough time for actions to complete before scheduling the next:

```sf
# ✅ GOOD - Actions don't overlap
0.0s  hero.punch      # 0.4s duration
1.0s  hero.kick       # 0.6s duration
2.0s  hero.uppercut   # 0.8s duration

# ❌ BAD - Actions interrupt each other prematurely
0.0s  hero.punch
0.2s  hero.kick       # Interrupts punch after 0.2s (feels jarring)
0.5s  hero.uppercut   # Interrupts kick after 0.3s
```

**Rule of thumb:** Add **1.5× the action duration** as spacing for natural flow.

### 2. Looping Actions as Filler

Use looping actions between one-shots:

```sf
0.0s  hero.idle       # Loop until interrupted
2.0s  hero.punch      # One-shot
3.0s  hero.idle       # Back to idle (automatic, but explicit is clearer)
5.0s  hero.kick
6.0s  hero.walk       # Loop until next event
10.0s hero.idle
```

### 3. Action Sequences (Combos)

For fluid combat sequences, chain actions with minimal gaps:

```sf
# Fast combo - tight timing
0.0s  hero.punch      # 0.4s
0.5s  hero.punch      # 0.4s (0.1s gap)
1.0s  hero.kick       # 0.6s (0.1s gap)
1.7s  hero.uppercut   # 0.8s (0.1s gap)

# Slower, deliberate strikes
0.0s  hero.punch
1.0s  hero.kick
2.5s  hero.slam
```

### 4. Movement Duration

When using movement (`hero.walk(x=600)`), calculate how long it takes:

**Walk speed:** 100 px/s  
**Run speed:** 200 px/s  
**Sprint speed:** 300 px/s

```sf
# Character at x=200, walking to x=600
# Distance: 400px ÷ 100px/s = 4 seconds

0.0s  hero.walk(x=600)
4.5s  hero.idle           # Wait for walk to finish (4s + 0.5s buffer)
5.0s  hero.punch
```

### 5. Camera Sync

Sync camera movements with character actions:

```sf
# Zoom in as punch lands
0.0s  hero.punch
0.0s  main.zoom_to(zoom=1.5)   # Same timing

# Shake on impact (slightly delayed)
0.3s  main.shake(intensity=15, duration=0.2)

# Zoom back out
0.6s  main.zoom_to(zoom=1.0)
```

---

## Common Patterns

### Pattern 1: Idle → Action → Idle

```sf
0.0s  hero.idle
2.0s  hero.wave       # 1.0s one-shot
3.5s  hero.idle       # Explicit return (or automatic at 3.0s)
```

### Pattern 2: Walk → Stop → Action

```sf
0.0s  hero.walk(x=600)
4.0s  hero.idle       # Stop walking
5.0s  hero.punch
```

### Pattern 3: Combat Sequence

```sf
0.0s  hero.idle
1.0s  hero.punch
1.5s  hero.kick
2.2s  hero.uppercut
3.5s  hero.idle
```

### Pattern 4: Emotional State

```sf
0.0s  hero.happy      # Loops
5.0s  hero.wave       # Interrupts happy, one-shot
6.5s  hero.happy      # Back to happy loop
```

### Pattern 5: Height Change

```sf
0.0s  hero.idle
2.0s  hero.sit        # 1.0s to sit down
3.5s  hero.idle       # Character sitting (still in sit pose)
5.0s  hero.stand_up   # 1.0s to stand
6.5s  hero.walk
```

---

## Speed Modification

Actions can be sped up or slowed down:

```sf
# Normal speed
0.0s  hero.punch

# Fast punch (2× speed, 0.2s duration)
1.0s  hero.punch(speed=2.0)

# Slow-motion kick (0.5× speed, 1.2s duration)
2.0s  hero.kick(speed=0.5)
```

**Formula:** `actual_duration = base_duration / speed`

---

## Timeline Debugging

### Check Action Overlap

If actions look wrong, check for unintended overlaps:

```sf
# This creates a problem:
0.0s  hero.walk      # Starts walking (loops forever)
2.0s  hero.punch     # Stops walk, starts punch
# At 2.4s, punch ends → auto-returns to idle
# Character stops moving at 2.4s (may be unexpected)
```

**Fix:** Explicitly control when looping actions end:

```sf
0.0s  hero.walk(x=600)
4.0s  hero.idle      # Stop walking before punch
5.0s  hero.punch
```

### Verify One-Shot Returns

One-shots return to idle automatically. If you don't see idle, the action might be:
1. A looping action (check the table above)
2. Interrupted by the next timeline event too soon

---

## Advanced: Action Queuing (Future)

Currently, timeline events fire at exact times and interrupt running actions. A future **queuing mode** could wait for actions to finish:

```sf
# Hypothetical future syntax
timeline(mode=queue):
    0.0s  hero.punch      # Starts at 0.0s
    next  hero.kick       # Waits for punch to finish, starts at 0.4s
    next  hero.uppercut   # Waits for kick, starts at 1.0s
```

**Current workaround:** Calculate durations manually and space events.

---

## Summary

✅ Timeline events fire at **exact times**  
✅ Actions **interrupt** each other when overlapped  
✅ **One-shot actions** return to idle automatically  
✅ **Looping actions** continue until interrupted  
✅ Space events by **1.5× action duration** for natural flow  
✅ Use **speed parameter** to modify action timing  
✅ **Calculate movement time** based on distance and speed  

---

## Reference: Complete Action List

See `engine/animation/generators.py` for the complete list of 68 actions and their implementations.
