"""Easing functions for animation interpolation"""

import math
from typing import Callable

# Type: easing function takes t in [0,1] and returns eased t in [0,1]
EasingFn = Callable[[float], float]


def linear(t: float) -> float:
    return t


def in_quad(t: float) -> float:
    return t * t


def out_quad(t: float) -> float:
    return t * (2.0 - t)


def in_out_quad(t: float) -> float:
    if t < 0.5:
        return 2.0 * t * t
    return -1.0 + (4.0 - 2.0 * t) * t


def in_cubic(t: float) -> float:
    return t * t * t


def out_cubic(t: float) -> float:
    t = t - 1.0
    return t * t * t + 1.0


def in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    t = 2.0 * t - 2.0
    return 0.5 * t * t * t + 1.0


def out_elastic(t: float) -> float:
    if t == 0 or t == 1:
        return t
    return math.pow(2, -10 * t) * math.sin((t - 0.075) * (2 * math.pi) / 0.3) + 1.0


def out_bounce(t: float) -> float:
    n1, n2 = 7.5625, 2.75
    if t < 1.0 / n2:
        return n1 * t * t
    elif t < 2.0 / n2:
        t -= 1.5 / n2
        return n1 * t * t + 0.75
    elif t < 2.5 / n2:
        t -= 2.25 / n2
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / n2
        return n1 * t * t + 0.984375


# Registry for looking up by name
EASING_REGISTRY: dict[str, EasingFn] = {
    'linear': linear,
    'in_quad': in_quad,
    'out_quad': out_quad,
    'in_out_quad': in_out_quad,
    'in_cubic': in_cubic,
    'out_cubic': out_cubic,
    'in_out_cubic': in_out_cubic,
    'out_elastic': out_elastic,
    'out_bounce': out_bounce,
}


def get_easing(name: str) -> EasingFn:
    """Look up an easing function by name. Falls back to linear."""
    return EASING_REGISTRY.get(name, linear)


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation"""
    return a + (b - a) * t


def interpolate_keyframes(keyframes: list, time: float) -> float:
    """Interpolate a value from a list of (time, value, easing_name) tuples.
    
    Args:
        keyframes: List of (time, value) or (time, value, easing_name)
        time: Current time in seconds
        
    Returns:
        Interpolated value
    """
    if not keyframes:
        return 0.0
    if time <= keyframes[0][0]:
        return keyframes[0][1]
    if time >= keyframes[-1][0]:
        return keyframes[-1][1]
    
    for i in range(len(keyframes) - 1):
        k0 = keyframes[i]
        k1 = keyframes[i + 1]
        if k0[0] <= time <= k1[0]:
            t = (time - k0[0]) / (k1[0] - k0[0])
            easing = k1[2] if len(k1) > 2 else 'linear'
            t = get_easing(easing)(t)
            return lerp(k0[1], k1[1], t)
    
    return keyframes[-1][1]
