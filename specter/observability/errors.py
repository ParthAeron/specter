import base64
import structlog
from pathlib import Path
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def capture_error_screenshot(session: CDPSession, file_path: str | Path) -> None:
    """
    Captures a JPEG screenshot of the current viewport and writes it to a file.
    """
    logger.info("Capturing screenshot on failure", path=str(file_path))
    
    try:
        response = await session.send("Page.captureScreenshot", {
            "format": "jpeg",
            "quality": 60
        })
        
        b64_data = response.get("data")
        if not b64_data:
            raise ValueError("No screenshot data returned from Chrome.")
            
        img_bytes = base64.b64decode(b64_data)
        
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(img_bytes)
        
        logger.info("Screenshot successfully captured", size_bytes=len(img_bytes))
    except Exception as e:
        logger.error("Failed to capture screenshot", error=str(e))
