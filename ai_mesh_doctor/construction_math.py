"""Construction budgets usable outside Blender, without UI or geometry imports."""
import math


def through_cut_interval(lower, upper, tolerance=1e-7):
    """Extend beyond both STOCK bounds along the cutting axis; not a blind cut."""
    if not all(math.isfinite(x) for x in (lower, upper, tolerance)) or lower >= upper or tolerance <= 0:
        raise ValueError('Finite stock interval and positive tolerance required')
    margin = max(tolerance*8, (upper-lower)*.001,
                 max(abs(lower),abs(upper))*2**-23*8)
    return lower-margin, upper+margin


def segments_for_sagitta(radius, error, minimum=16, maximum=512):
    if (not all(math.isfinite(x) and x > 0 for x in (radius,error))
            or type(minimum) is not int or type(maximum) is not int or not 3 <= minimum <= maximum):
        raise ValueError('Invalid circular tessellation budget')
    # Stable for very small errors; acos(1-error/radius) loses precision.
    angle = 2*math.asin(math.sqrt(min(1., error/(2*radius))))
    required = max(minimum,math.ceil(math.pi/angle))
    if required > maximum:
        raise ValueError('Requested chord error exceeds segment budget; revise explicitly')
    return required
