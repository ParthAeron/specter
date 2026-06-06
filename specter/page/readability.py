import os
import urllib.request
import structlog
from pathlib import Path
from specter.cdp import CDPSession

logger = structlog.get_logger()

READABILITY_URL = "https://unpkg.com/@mozilla/readability@0.5.0/Readability.js"
READABILITY_PATH = Path(__file__).parent.parent.parent / "scripts" / "readability" / "readability.min.js"

def _ensure_readability_script() -> str:
    """
    Ensures that Readability.js is available locally, downloading it from unpkg CDN if missing.
    """
    if READABILITY_PATH.exists():
        return READABILITY_PATH.read_text(encoding="utf-8")
        
    logger.info("Readability.js not found locally. Downloading from CDN...", url=READABILITY_URL)
    try:
        READABILITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(READABILITY_URL) as response:
            content = response.read().decode("utf-8")
            
        READABILITY_PATH.write_text(content, encoding="utf-8")
        return content
    except Exception as e:
        logger.error("Failed to download Readability.js from CDN, using simple text extractor fallback", error=str(e))
        # Fallback script that extracts plain text from body
        return "window.Readability = class { constructor(doc) { this.doc = doc; } parse() { return { title: this.doc.title, textContent: this.doc.body.innerText, excerpt: '' }; } };"

async def extract_readable_content(session: CDPSession) -> dict[str, str]:
    """
    Injects Readability.js on the page and extracts structured article text, title, and excerpt.
    """
    script_content = _ensure_readability_script()
    
    # Wrap in IIFE to avoid polluting window namespaces except Readability
    runner_script = f"""
    (function() {{
        if (typeof Readability === 'undefined') {{
            {script_content}
        }}
        try {{
            var documentClone = document.cloneNode(true);
            var article = new Readability(documentClone).parse();
            return article ? {{
                title: article.title || '',
                content: article.textContent || '',
                excerpt: article.excerpt || '',
                byline: article.byline || ''
            }} : null;
        }} catch(e) {{
            return {{ error: e.toString() }};
        }}
    }})();
    """
    
    try:
        # Runtime.evaluate returns remote object, we want a returned value
        response = await session.send("Runtime.evaluate", {
            "expression": runner_script,
            "returnByValue": True,
            "awaitPromise": True
        })
        
        result = response.get("result", {})
        if result.get("subtype") == "error" or "error" in result.get("value", {}):
            err_msg = result.get("value", {}).get("error", "Evaluation failed")
            logger.error("Readability execution failed in browser", error=err_msg)
            return {}
            
        value = result.get("value")
        if not value:
            return {}
            
        return {
            "title": value.get("title", ""),
            "content": value.get("content", "").strip(),
            "excerpt": value.get("excerpt", ""),
            "byline": value.get("byline", "")
        }
    except Exception as e:
        logger.error("Failed to execute readability parser", error=str(e))
        return {}
