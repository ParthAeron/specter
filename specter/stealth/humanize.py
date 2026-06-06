import random
import math
from typing import List, Tuple

def log_normal_delay(mean_ms: float, sigma_ms: float) -> float:
    """
    Generates a delay in seconds drawn from a log-normal distribution.
    This simulates realistic human reaction times.
    """
    mu = math.log(mean_ms ** 2 / math.sqrt(sigma_ms ** 2 + mean_ms ** 2))
    s = math.sqrt(math.log(1 + (sigma_ms / mean_ms) ** 2))
    return random.lognormvariate(mu, s) / 1000.0

def bezier_point(p0: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    """
    Calculates a single coordinate point on a cubic Bezier curve for a given t [0, 1].
    """
    x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0]
    y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1]
    return x, y

def generate_mouse_path(start: Tuple[float, float], end: Tuple[float, float], steps: int = 15) -> List[Tuple[float, float]]:
    """
    Generates a list of (x, y) coordinates representing a human-like mouse movement path.
    Uses a cubic Bezier curve with randomized control points, ease-in-out pacing, and slight jitter.
    """
    x1, y1 = start
    x2, y2 = end
    
    if start == end:
        return [end]
        
    # Generate two randomized control points in the bounding area between start and end
    dx = x2 - x1
    dy = y2 - y1
    
    cx1 = x1 + dx * random.uniform(0.1, 0.5) + random.uniform(-20, 20)
    cy1 = y1 + dy * random.uniform(0.1, 0.5) + random.uniform(-20, 20)
    cx2 = x1 + dx * random.uniform(0.5, 0.9) + random.uniform(-20, 20)
    cy2 = y1 + dy * random.uniform(0.5, 0.9) + random.uniform(-20, 20)
    
    p0 = (x1, y1)
    p1 = (cx1, cy1)
    p2 = (cx2, cy2)
    p3 = (x2, y2)
    
    path = []
    for i in range(steps + 1):
        # Apply ease-in-out function to the t progress parameter
        linear_t = i / steps
        # Easing function: t^2 * (3 - 2t)
        t = linear_t * linear_t * (3 - 2 * linear_t)
        
        px, py = bezier_point(p0, p1, p2, p3, t)
        
        # Add a tiny micro-tremor jitter (except at the exact start and end)
        if 0 < i < steps:
            px += random.uniform(-1.0, 1.0)
            py += random.uniform(-1.0, 1.0)
            
        path.append((px, py))
        
    return path
