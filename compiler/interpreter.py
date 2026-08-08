"""StickFrame script interpreter — turns a creative `script:` block into
timeline events.

.sf scripts can now be written like a tiny Python: variables, arithmetic,
repeat / for-in loops, if/else, user-defined functions, and action scheduling
with computed times and parameter expressions:

    scene s width=800 height=600 fps=30
    character hero:
        rig bipedal
        scale=2
        position (400, 374)
    camera main:
        follow hero
    script:
        var t = 0.5
        repeat 3:
            hero.wave at t
            t = t + 0.8
        hero.punch(power=95) at t
        if t > 2:
            hero.kick at t + 0.5
        def flourish(n):
            repeat n:
                hero.point at t
                t += 0.4
        flourish(2)

The interpreter executes the statements deterministically and emits
timeline events (time, "entity.action", params) that drive the exact same
accurate render path as a hand-written `timeline:` block.

Deterministic by design — no randomness, no floating-point surprises beyond
what the user writes. The same script always produces the same events.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from compiler import (
    SAssign, SSchedule, SRepeat, SFor, SIf, SDef, SReturn, SExpr,
    ENumber, EString, EVar, EBin, EUnary, ECall,
)


class ScriptError(Exception):
    pass


# ── Scope helpers ──────────────────────────────────────────────────

def _push_scope(ctx):
    ctx["scope"].append({})


def _pop_scope(ctx):
    ctx["scope"].pop()


def _get(ctx, name) -> Any:
    for frame in reversed(ctx["scope"]):
        if name in frame:
            return frame[name]
    raise ScriptError(f"undefined variable '{name}'")


def _set(ctx, name, value):
    ctx["scope"][-1][name] = value


# ── Expression evaluation ─────────────────────────────────────────

def _truthy(v) -> bool:
    return bool(v)


def _eval(expr, ctx) -> Any:
    if isinstance(expr, ENumber):
        return float(expr.value)
    if isinstance(expr, EString):
        return str(expr.value)
    if isinstance(expr, EVar):
        return _get(ctx, expr.name)
    if isinstance(expr, EBin):
        l = _eval(expr.left, ctx)
        r = _eval(expr.right, ctx)
        op = expr.op
        if op == "+":
            return l + r
        if op == "-":
            return l - r
        if op == "*":
            return l * r
        if op == "/":
            return l / r if r else 0.0
        if op == "%":
            return l % r if r else 0.0
        if op == "and":
            return _truthy(l) and _truthy(r)
        if op == "or":
            return _truthy(l) or _truthy(r)
        if op in ("<", ">", "==", "!=", "<=", ">="):
            return _compare(op, l, r)
        raise ScriptError(f"unknown operator '{op}'")
    if isinstance(expr, EUnary):
        v = _eval(expr.operand, ctx)
        if expr.op == "-":
            return -v
        if expr.op == "+":
            return v
        if expr.op == "not":
            return not _truthy(v)
    if isinstance(expr, ECall):
        return _call(expr, ctx)
    raise ScriptError(f"cannot evaluate {expr!r}")


def _compare(op: str, a, b) -> bool:
    if op == "<": return a < b
    if op == ">": return a > b
    if op == "==": return a == b
    if op == "!=": return a != b
    if op == "<=": return a <= b
    if op == ">=": return a >= b
    return False


# ── Builtins ─────────────────────────────────────────────────────

_BUILTINS = {
    "int": lambda x: int(x),
    "float": lambda x: float(x),
    "abs": lambda x: abs(x),
    "round": lambda x, nd=0: round(x, int(nd)),
    "min": min,
    "max": max,
    "range": lambda *a: list(range(*[int(i) for i in a])),
    "print": lambda *a: print("  [script]", *a),
}


def _call(expr: ECall, ctx) -> Any:
    name = expr.name
    args = [_eval(a, ctx) for a in expr.args]

    fn = ctx["funcs"].get(name)
    if fn is not None:
        _push_func_scope(ctx, fn, args)
        _run_block(fn.body, ctx)
        rc = ctx["_return"]
        ctx["_return"] = None
        ctx["scope"].pop()
        return rc if rc is not None else 0.0

    if name in _BUILTINS:
        try:
            return _BUILTINS[name](*args)
        except TypeError:
            return _BUILTINS[name](args[0])

    raise ScriptError(f"unknown function '{name}'")


def _push_func_scope(ctx, fn, args):
    _push_scope(ctx)
    for pname, pval in zip(fn.params, args):
        _set(ctx, pname, pval)


# ── Statement execution ──────────────────────────────────────────

def _run_block(stmts, ctx):
    for st in stmts:
        _run(st, ctx)
        if ctx["_return"] is not None or ctx["_break"]:
            break


def _run(st, ctx):
    if isinstance(st, SAssign):
        val = _eval(st.value, ctx)
        if st.op == "=":
            _set(ctx, st.name, val)
        else:  # +=, -=, *=, /=, %=
            cur = _get(ctx, st.name)
            _set(ctx, st.name, _apply(st.op[0], cur, val))
        return

    if isinstance(st, SSchedule):
        t = float(_eval(st.time, ctx))
        params = {k: _eval(v, ctx) for k, v in st.params.items()}
        ctx["events"].append({
            "time": t,
            "action": f"{st.entity}.{st.action}",
            "params": params,
        })
        return

    if isinstance(st, SRepeat):
        n = int(_eval(st.count, ctx))
        for _ in range(max(0, n)):
            _run_block(st.body, ctx)
            if ctx["_return"] is not None or ctx["_break"]:
                break
        return

    if isinstance(st, SFor):
        items = _eval(st.iter_expr, ctx)
        for item in items or []:
            ctx["scope"][-1][st.var] = item
            _run_block(st.body, ctx)
            if ctx["_return"] is not None or ctx["_break"]:
                break
        return

    if isinstance(st, SIf):
        if _truthy(_eval(st.cond, ctx)):
            _run_block(st.body, ctx)
        else:
            _run_block(st.else_body, ctx)
        return

    if isinstance(st, SDef):
        ctx["funcs"][st.name] = st
        return

    if isinstance(st, SReturn):
        ctx["_return"] = _eval(st.value, ctx) if st.value is not None else None
        return

    if isinstance(st, SExpr):
        _eval(st.expr, ctx)  # result discarded (calls/computed values)
        return

    raise ScriptError(f"unknown statement {st!r}")


def _apply(op: str, a, b) -> Any:
    if op == "+": return a + b
    if op == "-": return a - b
    if op == "*": return a * b
    if op == "/": return a / b if b else 0.0
    if op == "%": return a % b if b else 0.0
    raise ScriptError(f"unknown operator '{op}='")


# ── Entry point ──────────────────────────────────────────────────

def interpret(statements: List, scene_name: str = "script") -> List[Dict[str, Any]]:
    """Run a parsed script block and return timeline events (time-sorted).

    Args:
        statements: the list of statement nodes parsed from `script:`.
        scene_name: key under which events are grouped in the timeline dict.

    Returns:
        List of {"time", "action", "params"} dicts, sorted by time.
    """
    ctx = {
        "scope": [{}],       # variable frame stack
        "funcs": {},         # name -> SDef
        "events": [],        # collected timeline events
        "_return": None,
        "_break": False,
    }
    _run_block(statements, ctx)
    events = ctx["events"]
    events.sort(key=lambda e: e["time"])
    return events


def script_is_present(statements) -> bool:
    return bool(statements)