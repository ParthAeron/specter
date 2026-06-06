import asyncio
import random
import structlog
from typing import Any, Tuple
from specter.cdp import CDPSession
from specter.page.refs import RefRegistry
from specter.stealth.humanize import generate_mouse_path

logger = structlog.get_logger()

# Track mouse position per session globally
_mouse_positions: dict[str, Tuple[float, float]] = {}

def get_mouse_position(session_id: str) -> Tuple[float, float]:
    if session_id not in _mouse_positions:
        # Start mouse at a random position offscreen or at a corner
        _mouse_positions[session_id] = (random.uniform(0, 100), random.uniform(0, 100))
    return _mouse_positions[session_id]

def set_mouse_position(session_id: str, pos: Tuple[float, float]) -> None:
    _mouse_positions[session_id] = pos

async def click_element(
    session: CDPSession,
    ref_registry: RefRegistry,
    ref: str,
    steps: int = 12,
    timeout: float = 10.0
) -> dict[str, Any]:
    """
    Simulates a human-like click on the element identified by the short reference (e.g. n4).
    Resolves the box model, generates a Bezier mouse path, dispatches mouse move and click events.
    """
    logger.info("Clicking element", ref=ref)
    
    try:
        # 1. Resolve short ref to active nodeId
        node_id = await ref_registry.resolve_to_node_id(session, ref)
        
        # 2. Retrieve element box model
        box_response = await session.send("DOM.getBoxModel", {
            "nodeId": node_id
        }, timeout=timeout)
        
        model = box_response.get("model", {})
        content_quad = model.get("content")
        if not content_quad or len(content_quad) < 8:
            raise ValueError(f"Could not retrieve content bounds for element '{ref}'")
            
        # 3. Calculate center point from the 4-point polygon coordinates
        # content_quad = [x1, y1, x2, y2, x3, y3, x4, y4]
        cx = (content_quad[0] + content_quad[2] + content_quad[4] + content_quad[6]) / 4
        cy = (content_quad[1] + content_quad[3] + content_quad[5] + content_quad[7]) / 4
        
        # 4. Generate human-like Bezier path
        start_pos = get_mouse_position(session.session_id)
        path = generate_mouse_path(start_pos, (cx, cy), steps=steps)
        
        # 5. Dispatch mouse moves along the Bezier curve
        logger.debug("Dispatching Bezier mouse moves", start=start_pos, end=(cx, cy), steps=len(path))
        for point in path:
            x, y = point
            await session.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x,
                "y": y
            })
            # Add a slight delay between points to simulate velocity
            await asyncio.sleep(random.uniform(0.005, 0.015))
            
        set_mouse_position(session.session_id, (cx, cy))
        
        # 6. Execute human click sequence (Press -> Delay -> Release)
        await session.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": cx,
            "y": cy,
            "button": "left",
            "clickCount": 1
        })
        
        # Human click delay (80ms to 150ms)
        await asyncio.sleep(random.uniform(0.08, 0.15))
        
        await session.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": cx,
            "y": cy,
            "button": "left",
            "clickCount": 1
        })
        
        logger.info("Successfully clicked element", ref=ref, coords=(cx, cy))
        return {
            "status": "ok",
            "ref": ref,
            "coords": (cx, cy)
        }
        
    except Exception as e:
        logger.error("Click action failed", ref=ref, error=str(e))
        return {
            "status": "error",
            "error_type": "click_failed",
            "error_detail": str(e)
        }
