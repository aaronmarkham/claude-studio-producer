"""Geographic primitives shared across timeline parsing, joining, and rendering.

Kept in one place so distance and interpolation behave identically everywhere —
a join that measures distance differently than the filter that produced the track
will disagree with itself in ways that are very hard to see.
"""

from __future__ import annotations

import math
from typing import Tuple

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing in degrees (0-360) from point 1 toward point 2.

    Used by the visual grammar to drift a Ken Burns pan toward the next beat.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def interpolate_linear(
    lat1: float, lon1: float, lat2: float, lon2: float, t: float
) -> Tuple[float, float]:
    """Straight-line interpolation. Fine at city scale, wrong across continents."""
    return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)


def interpolate_great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, t: float
) -> Tuple[float, float]:
    """Slerp along the great circle. Use for flights, where linear visibly lies."""
    p1, l1 = math.radians(lat1), math.radians(lon1)
    p2, l2 = math.radians(lat2), math.radians(lon2)
    d = 2 * math.asin(
        math.sqrt(
            math.sin((p2 - p1) / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
        )
    )
    if d < 1e-12:                      # coincident points — slerp is undefined
        return (lat1, lon1)
    a = math.sin((1 - t) * d) / math.sin(d)
    b = math.sin(t * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return (
        math.degrees(math.atan2(z, math.sqrt(x * x + y * y))),
        math.degrees(math.atan2(y, x)),
    )


def speed_kmh(
    lat1: float, lon1: float, lat2: float, lon2: float, seconds: float
) -> float:
    """Implied ground speed between two fixes. Used to reject teleports."""
    if seconds <= 0:
        return 0.0
    return (haversine_m(lat1, lon1, lat2, lon2) / seconds) * 3.6
