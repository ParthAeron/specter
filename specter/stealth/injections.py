import random
import structlog
from typing import Optional
from pathlib import Path
from specter.cdp import CDPSession

logger = structlog.get_logger()

# Path to the JavaScript patches file relative to this script
PATCHES_JS_PATH = Path(__file__).parent.parent.parent / "scripts" / "stealth" / "patches.js"

def get_stealth_script(seed: Optional[float] = None) -> str:
    if seed is None:
        seed = random.random()
        
    try:
        if PATCHES_JS_PATH.exists():
            js_template = PATCHES_JS_PATH.read_text(encoding="utf-8")
        else:
            # Fallback inline minimal loader if file not found
            logger.warn("patches.js file not found, using minimal fallback", path=str(PATCHES_JS_PATH))
            js_template = "(function() { delete Navigator.prototype.webdriver; })();"
            return js_template
    except Exception as e:
        logger.error("Failed to read patches.js file", error=str(e))
        js_template = "(function() { delete Navigator.prototype.webdriver; })();"
        return js_template
        
    # Replace placeholder with session-seeded float literal
    return js_template.replace("%SESSION_SEED%", f"{seed:.8f}")

async def inject_stealth(session: CDPSession, seed: Optional[float] = None) -> None:
    logger.info("Injecting stealth script", session_id=session.session_id)
    
    script_content = get_stealth_script(seed)
    
    try:
        # 1. Enable Page domain
        await session.send("Page.enable", {})
        
        # 2. Add injection script
        await session.send("Page.addScriptToEvaluateOnNewDocument", {
            "source": script_content
        })
    except Exception as e:
        logger.error("Failed to inject stealth patches", error=str(e), session_id=session.session_id)
        raise
