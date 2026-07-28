# AI Director — Architecture Document

**StickFrame Animation Operating System**
**Classification:** Engineering Internal — Architecture Exploration
**Status:** Draft v0.1

---

## 1. Purpose

The AI Director is an autonomous cinematography system that converts a structured story plan into a fully realized animated sequence. It makes decisions about camera placement, shot composition, action choreography, scene pacing, and dramatic emphasis. The Director is entirely optional — the engine works without it.

## 2. Architecture

```
Source Script (.sf) or LLM output
         │
┌────────▼────────┐
│   Story Parser   │  Extract: characters, scenes, actions, dialogue
│                  │  Validate: structural completeness
└────────┬────────┘
         │
┌────────▼────────┐
│  Scene Planner   │  Break story into scenes, assign durations
│                  │  Determine scene emotional arc (tension curve)
└────────┬────────┘
         │
┌────────▼────────┐
│ Character Planner│  Assign initial positions, blocking paths
│                  │  Plan character entrances and exits
└────────┬────────┘
         │
┌────────▼────────┐
│  Camera Planner  │  Choose shot types (wide, medium, close-up)
│                  │  Plan camera movement and cuts
│                  │  Assign shots to scenes
└────────┬────────┘
         │
┌────────▼────────┐
│  Choreographer   │  Fill gaps with contextual actions
│                  │  Add reactions, flourishes, idle variations
│                  │  Ensure characters aren't static during dialogue
└────────┬────────┘
         │
┌────────▼────────┐
│ Dialogue Planner │  Assign speech bubble timings
│                  │  Plan gesture/emphasis beats
└────────┬────────┘
         │
┌────────▼────────┐
│    Validator     │  Timeline coherence check
│                  │  No speaking-after-death
│                  │  No simultaneous contradictory actions
│                  │  All referenced entities exist
└────────┬────────┘
         │
         ▼
   Engine-ready Timeline + Scene Graph
```

## 3. Subsystem Details

### 3.1 Story Parser
- Accepts: Natural language or structured .sf script
- Outputs: Entity list, scene list, dialogue lines, action sequence
- Implements: LLM-based parsing with schema-constrained output (JSON mode)
- Validation: All entities referenced in actions must be declared

### 3.2 Scene Planner
- Accepts: Story structure with scene boundaries
- Outputs: Scene duration estimates, emotional beat markers
- Key decision: Scene length is derived from dialogue word count + action density + dramatic weight

### 3.3 Camera Planner
- Shot grammar (wide, medium, close-up, over-shoulder, two-shot)
- Cut timing: minimum 2 seconds between cuts, maximum 8 seconds without cut
- Emotional emphasis: close-up on dramatic lines, wide on action reveals
- Camera movement: motivated by character movement, not arbitrary

### 3.4 Choreographer
- Fills "dead air" with contextual actions (character shifts weight, looks around, reacts to other characters)
- Adds secondary actions (breathing, blinking, fidgeting)
- Ensures visual variety — no two consecutive shots with identical composition

### 3.5 Validator
- The validator is the safety net. It catches impossible configurations before they reach the engine.
- Rules are declarative and extensible via the plugin system.

## 4. Director Overlay System

The Director never modifies the original timeline. Instead, it produces a **director's cut overlay**:

```json
{
  "director_overlay": {
    "base_timeline": "user_script.sf",
    "version": 1,
    "modifications": [
      {
        "type": "insert_camera_keyframe",
        "time": 4.0,
        "params": { "shot": "close-up", "target": "hero" }
      },
      {
        "type": "add_background_action",
        "time": 2.5,
        "character": "villain",
        "action": "idle_shift_weight"
      }
    ]
  }
}
```

The original timeline is preserved. The overlay can be accepted, rejected, or edited before rendering.

## 5. Research Questions

- Can shot selection be modeled as a constraint satisfaction problem?
- What is the minimal shot grammar that can tell any story?
- How to evaluate director quality objectively?
- Can pacing be algorithmically derived from dialogue sentiment analysis?
- When should the director break its own rules for dramatic effect?

## 6. Out of Scope (v0)

- Voice direction (tone, emphasis, emotion)
- Lip-sync precision
- Action choreography for complex fight scenes
- Multi-camera real-time switching (for live production)
