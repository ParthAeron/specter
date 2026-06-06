import json
import structlog
from pathlib import Path
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def save_cookies(session: CDPSession, file_path: str | Path) -> None:
    """
    Retrieves all cookies from the active page session and writes them to a JSON file.
    """
    logger.info("Saving session cookies to disk", path=str(file_path))
    
    try:
        response = await session.send("Network.getCookies", {})
        cookies = response.get("cookies", [])
        
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        
        logger.info("Cookies successfully saved", count=len(cookies))
    except Exception as e:
        logger.error("Failed to save cookies", error=str(e))
        raise

async def restore_cookies(session: CDPSession, file_path: str | Path) -> None:
    """
    Reads cookies from a JSON file and applies them to the active session.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warn("Cookie file not found. Skipping restoration.", path=str(file_path))
        return
        
    logger.info("Restoring session cookies from disk", path=str(file_path))
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
        if not cookies:
            return
            
        await session.send("Network.setCookies", {
            "cookies": cookies
        })
        logger.info("Cookies successfully restored", count=len(cookies))
    except Exception as e:
        logger.error("Failed to restore cookies", error=str(e))
        raise
