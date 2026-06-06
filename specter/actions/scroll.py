import asyncio
import random
import structlog
from typing import Any
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def scroll_page(
    session: CDPSession,
    direction: str = "down",
    amount: int = 600,
    timeout: float = 5.0
) -> dict[str, Any]:
    """
    Scrolls the page by sending multiple mouseWheel events with a deceleration curve.
    Directions: 'down', 'up', 'left', 'right'.
    """
    logger.info("Scrolling page", direction=direction, amount=amount)
    
    try:
        # Determine signs and axes
        multiplier = 1 if direction in ("down", "right") else -1
        is_vertical = direction in ("down", "up")
        
        # Break total amount into a deceleration curve steps
        # E.g. for 600px: [180, 150, 120, 80, 50, 20]
        steps = 6
        step_percentages = [0.30, 0.25, 0.20, 0.13, 0.08, 0.04]
        
        # Determine current center of screen to place mouse cursor for scroll events
        eval_resp = await session.send("Runtime.evaluate", {
            "expression": "({ w: window.innerWidth / 2, h: window.innerHeight / 2 })",
            "returnByValue": True
        })
        screen_center = eval_resp.get("result", {}).get("value", {"w": 500, "h": 500})
        mx = screen_center.get("w", 500)
        my = screen_center.get("h", 500)
        
        for p in step_percentages:
            step_val = int(amount * p) * multiplier
            
            delta_x = 0
            delta_y = 0
            if is_vertical:
                delta_y = step_val
            else:
                delta_x = step_val
                
            await session.send("Input.dispatchMouseEvent", {
                "type": "mouseWheel",
                "x": mx,
                "y": my,
                "deltaX": delta_x,
                "deltaY": delta_y
            })
            
            # Smooth scroll wheel intervals (30ms to 60ms)
            await asyncio.sleep(random.uniform(0.03, 0.06))
            
        logger.info("Finished scrolling", direction=direction, amount=amount)
        return {
            "status": "ok",
            "direction": direction,
            "amount": amount
        }
        
    except Exception as e:
        logger.error("Scroll action failed", error=str(e))
        return {
            "status": "error",
            "error_type": "scroll_failed",
            "error_detail": str(e)
        }
