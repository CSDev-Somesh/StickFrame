# Mocap Pipeline — Real Motion for StickFrame

**Status:** Built & wired into the engine (2026-08-08)
**Purpose:** Bring real human motion into StickFrame so any action that exists
in a motion-capture library can play in our stickman — no hand-written
generator math per action, and far more natural than procedural curves.

---

## Why mocap

Our procedural generators (65+ actions) are hand-tuned math. They cover the
common vocabulary well, but a new story beat ("dropkicks," "angry stomp,"
"ballerina pirouette") means writing a new generator by hand.

Motion capture gives us **all the actions, for free**: CMU has a public
database with **2,600+ clips** (locomotion, sports, dance, martial arts) in
BVH/AMC formats. BVH files are just a skeleton + per-frame joint rotations —
exactly the data our keyframe `ActionClip` system can consume.

## Where the pieces live

| Module | Role |
|--------|------|
| `engine/mocap/bvh.py` | Parses BVH text → `BVHClip`; gives per-frame world positions for every joint (matrix FK, no external deps) |
| `engine/mocap/retarget.py` | Maps mocap joints → our 25-bone rig via an alias table, recovers parent-relative bone angles by inverting FK |
| `engine/mocap/importer.py` | Turns `.bvh` files (or a folder) into `ActionClip`s at a target fps / loop flag |
| `engine/__init__.py` | `load_mocap_library()` registers clips on the engine + attaches to characters so `.sf` timelines can name them |

## Data flow

```
.bvh file
   └─ parse_bvh() ───────────── BVHClip (frames, joints)
        └─ clip_to_poses(frame) ── one pose per frame:
             • flatten 3D → 2D (front or side view), y-down
             • subtract hips root (figure becomes local)
             • resolve each bone tip to a mocap joint (alias table)
             • solve_pose(): bone_angle = atan2(child − parent) − parent_world
        └─ bvh_to_action_clip() ── ActionClip{
              bone_keyframes: {bone: [Keyframe(t, angle), …]}
              duration, loop
           }
engine.load_mocap_library(folder) ── dict[name, ActionClip]
   └─ play_action(entity, name)  # resolves mocap before procedural gens
```

### Key detail: angle convention matches the rig exactly

StickFrame's FK is:
```
world_angle[i] = world_angle[parent] + bone.default_angle
tip[i] = parent_tip + (cos(world_angle)·len, sin(world_angle)·len)
```
`retarget.solve_pose()` computes each `bone_angle` as
`atan2(childJoint − parentJoint) − parent_world` — the exact inverse. So a
pose recovered from mocap reproduces identical skeleton positions via FK.

### Key property: angles are scale-invariant

Only directions matter (`atan2` of vectors), so we never need to rescale the
mocap units — a mocap subject's height doesn't matter. The `.sf` `scale=`
parameter still controls the rendered figure size.

### Degenerate-vector guard

If a bone's parent and child joints coincide (e.g. a minimal skeleton without
a `head_top` joint), `atan2(0,0)` is garbage, so we fall back to the rest
pose for that bone. Missing joints fall back to rest pose too ⇒ partial
skeletons still play.

## View projection

- `view="front"`: screen x = mocap X (right), y = −mocap Y (up→down).
  Best for gestures, punches, dances, poses.
- `view="side"`: screen x = −mocap Z (forward), y = −mocap Y. Best for
  locomotion (walk/run) where the legs scissor along the fixture's facing.

## Getting mocap data (CMU)

1. Browse/search the [CMU mocap database](http://mocap.cs.cmu.edu/), ~2,600
   clips under "free for all use."
2. Download clips as `.bvh` (many mirrors host CMU converted to BVH).
3. Drop the `.bvh` files into a folder — one file per action, named the
   action you want to expose (e.g. `spin_kick.bvh`).
4. In Python:
   ```python
   engine.load_mocap_library("mocap_lib", loops=["walk", "idle"])
   ```
5. In a `.sf` timeline, use the action by name:
   ```sf
   timeline:
       scene act1:
           0.0s   hero.spin_kick
   ```

Alternatives: [HDM05](https://resources.mpi-inf.mpg.de/HDM05/) (3+ hrs, classic),
[LaFAN1 (Ubisoft)](https://github.com/ubisoft/ubisoft-laforge-animation-dataset)
(check its license before public use).

## Real-data verification (CMU, 2026-08-08)

Verified against actual downloaded CMU BVH files (`una-dinosauria/cmu-mocap`):
- Subject 07 `07_01` (walk) and Subject 02 `02_01` (walk/run) both resolve
  **18/18 semantic slots** (Hips, Spine1, Neck, Head, Left/Right Shoulder,
  ForeArm, Hand, UpLeg, Leg, Foot, ToeBase) and render walk videos.
- Joint-naming handled case-insensitively; real CMU names like `LeftUpLeg`
  (hip), `LeftLeg` (knee), `LeftFoot` (ankle), `LeftToeBase` (toe),
  `LeftForeArm` (elbow), `LeftHand` (wrist) map via the `SEARCH` alias table.

## Projection guidance (important — real mocap is NOT axis-aligned)

A 2D stickman must be flattened from 3D, and the CHARACTER'S facing decides
which axis contains the stride:
- **`front`** (screen x = world X, y = −world Y) shows a walk's pedalling in
  the world-X lateral axis — recommended default; matches our side-on
  proc-walk style where legs scissor in screen X–Y.
- **`side`** projects onto the body's *anatomical forward* axis (derived from
  the hips-lateral cross product, travel-signed), for clips authored in the
  sagittal plane. Use it when `front` reads as lateral crab-walk.
- The naive `side` convention x = −z is **wrong** for real CMU because the
  subject's facing is not world-aligned (pelvis yaw).

## Retargeting quality notes (honest)

- We map by **name aliases** — different mocap skeletons name joints
  differently (`lshoulder` vs `LeftForeArm` vs `shoulder.l`). The alias table
  covers CMU/HDM/Blender/common exporters; extend `SEARCH` (lowercase) if a
  dataset uses other names. Resolution is case-insensitive.
- We project mocap into the 2D plane, so strongly out-of-plane motions
  (twists, spins) flatten. Great for planar reads, rough for figures that
  spin a lot.
- Feet ground: the recovered pose applies bones only; the physics ground
  clamp (`ground_offset`) still rides, so mocap foot-plants slide slightly.
  A future "foot IK" pass could snap the plant foot to the floor.
- The user-facing accuracy requirement is 100%: real clip -> exact video
  still needs per-clip QA (see `scripts/test_mocap_real.py`), especially
  feet and out-of-plane motions.

## Future work

- **Foot-plant stabilization** for locomotion (hold the planted foot at
  ground while the body passes over).
- **12–24 fps down-sampling + smoothing** to reduce jitter in noisy mocap.
- **`.sf`-exposed rotation/scale hygiene**: allow overriding clip root
  rotation for off-axis takes.
- **Automatic `loop` detection**: a clip whose first/last pose are close ⇒
  loop=true.

---
**Status kept in git**: `engine/mocap/`, `scripts/gen_synthetic_bvh.py`,
`scripts/mocap_smoke.py`, docs.