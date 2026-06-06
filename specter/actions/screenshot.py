import base64
import structlog
from typing import Any, Optional
from pathlib import Path
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def take_screenshot(
    session: CDPSession,
    file_path: Optional[str] = None,
    timeout: float = 10.0
) -> dict[str, Any]:
    """
    Captures a screenshot of the current page viewport.
    Returns the base64-encoded image data. If a file_path is specified,
    also writes the image to disk.
    """
    logger.info("Taking page screenshot", file_path=file_path)
    
    try:
        response = await session.send("Page.captureScreenshot", {
            "format": "png"
        }, timeout=timeout)
        
        b64_data = response.get("data")
        if not b64_data:
            raise ValueError("No screenshot data returned from Chrome.")
            
        if file_path:
            img_bytes = base64.b64decode(b64_data)
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(img_bytes)
            logger.info("Screenshot saved to file", path=str(path), size_bytes=len(img_bytes))
            
        return {
            "status": "ok",
            "data": b64_data
        }
    except Exception as e:
        logger.error("Screenshot action failed", error=str(e))
        return {
            "status": "error",
            "error_type": "screenshot_failed",
            "error_detail": str(e)
        }
