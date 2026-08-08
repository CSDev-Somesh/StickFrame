# .sf Creative Scripting Language

The `.sf` compiler now accepts a `script:` block — a tiny programming
language so a user composes actions from the library like writing code, not
just a fixed linear timeline. Deterministic: the same script always
produces the same video.

## Example

```sf
scene stage width=800 height=600 fps=30

camera main:
    follow hero
    zoom 1.0

character hero:
    rig bipedal
    scale=2.5
    position (400, 374)

script:
    var t = 0.5
    repeat 3:                    # wave three times, 0.8s apart
        hero.wave at t
        t = t + 0.8

    hero.punch(power=95) at t    # computed param + computed time

    if t > 2:                    # conditional separate flow
        hero.kick at t + 0.5
    else:
        hero.point at t

    var f = 0.0
    def combo(n):                # user-defined function
        repeat n:
            hero.punch at f
            f += 0.6
    combo(2)                     # call it

    for i in range(2):           # range loop
        hero.happy at 5.0 + i
```

## Language elements

| Syntax | Meaning |
|--------|---------|
| `var x = expr` | declare a variable |
| `x = expr` / `x += expr` | assign / augment |
| `entity.action at expr` | schedule an action at a computed time |
| `entity.action(param=expr, ...) at expr` | schedule with computed params |
| `repeat expr:` … | do a block N times |
| `for i in expr:` … | iterate |
| `if expr:` … `else:` … | conditional branching |
| `def name(a, b):` … `return expr` | user function |
| `range(n)` `int()` `float()` `round()` `abs()` `min()` `max()` | built-ins |
| `print(expr)` | debug output |

Every action available from the library (procedural or mocap) can be
scheduled; expressions may appear anywhere a number/string is expected
(times, params, loop bounds, conditions).

## Notes

- The `script:` block and the declarative `timeline:` block can coexist; the
  script track is merged into the render timeline.
- Deterministic by design — no LLM, no randomness; the engine still renders
  exactly what the script computes.
- The interpreter lives in `compiler/interpreter.py`; the parser additions
  are in `compiler/__init__.py`.