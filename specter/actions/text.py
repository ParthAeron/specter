import structlog
from typing import Any, Dict, Optional
from specter.cdp import CDPSession
from specter.page.readability import extract_readable_content

logger = structlog.get_logger()

async def get_page_text(
    session: CDPSession,
    mode: str = "readability",  # "readability" or "raw"
    timeout: float = 10.0
) -> dict[str, Any]:
    """
    Retrieves the actual text content of the page.
    - 'readability': Extracts clean article title and readability prose.
    - 'raw': Returns document.body.innerText.
    """
    logger.info("Extracting page text content", mode=mode)
    
    try:
        if mode == "readability":
            article = await extract_readable_content(session)
            if not article:
                return {
                    "status": "error",
                    "error_type": "extraction_failed",
                    "error_detail": "Readability extraction returned empty result."
                }
            return {
                "status": "ok",
                "mode": mode,
                "text": article.get("content", ""),
                "title": article.get("title", ""),
                "excerpt": article.get("excerpt", ""),
                "byline": article.get("byline", "")
            }
        else:
            # Evaluate document.body.innerText
            response = await session.send("Runtime.evaluate", {
                "expression": "document.body.innerText || ''",
                "returnByValue": True,
                "awaitPromise": True
            }, timeout=timeout)
            
            result = response.get("result", {})
            if result.get("subtype") == "error":
                err_msg = result.get("value", {}).get("error", "Raw text evaluation failed")
                return {
                    "status": "error",
                    "error_type": "extraction_failed",
                    "error_detail": err_msg
                }
            
            text_val = result.get("value", "")
            return {
                "status": "ok",
                "mode": mode,
                "text": text_val
            }
            
    except Exception as e:
        logger.error("Text extraction action failed", error=str(e))
        return {
            "status": "error",
            "error_type": "extraction_failed",
            "error_detail": str(e)
        }
