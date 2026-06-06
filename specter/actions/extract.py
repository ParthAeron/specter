import json
import structlog
from typing import Any, Dict
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def extract_data(
    session: CDPSession,
    schema: Dict[str, Any],
    timeout: float = 10.0
) -> dict[str, Any]:
    """
    Evaluates a CSS selector schema on the page to extract structured JSON data.
    Schema format example:
      {
        "title": "h1",
        "price": ".price-tag",
        "features": [".feature-item"] // Array indicates multiple elements
      }
    """
    logger.info("Extracting structured data from page", schema_keys=list(schema.keys()))
    
    # We construct a JavaScript function to walk the DOM based on the schema
    js_expression = f"""
    (function() {{
        const schema = {json.dumps(schema)};
        
        function evaluateNode(spec) {{
            if (typeof spec === 'string') {{
                const el = document.querySelector(spec);
                return el ? el.innerText.strip() || el.textContent.strip() : null;
            }} else if (Array.isArray(spec)) {{
                if (spec.length === 0) return [];
                const selector = spec[0];
                
                // If it is a nested schema array like [{{"name": ".name"}}]
                if (typeof selector === 'object') {{
                    // This requires a parent selector in the schema.
                    // To keep it simple, we support flat arrays or standard element selections.
                    return [];
                }}
                
                const elements = document.querySelectorAll(selector);
                return Array.from(elements).map(el => el.innerText.trim() || el.textContent.trim());
            }} else if (typeof spec === 'object' && spec !== null) {{
                const result = {{}};
                for (const [key, value] of Object.entries(spec)) {{
                    result[key] = evaluateNode(value);
                }}
                return result;
            }}
            return null;
        }}
        
        try {{
            // Add helper trim implementation
            String.prototype.strip = String.prototype.strip || function() {{ return this.trim(); }};
            return evaluateNode(schema);
        }} catch (e) {{
            return {{ error: e.toString() }};
        }}
    }})();
    """
    
    try:
        response = await session.send("Runtime.evaluate", {
            "expression": js_expression,
            "returnByValue": True,
            "awaitPromise": True
        }, timeout=timeout)
        
        result = response.get("result", {})
        if result.get("subtype") == "error" or "error" in result.get("value", {}):
            err_msg = result.get("value", {}).get("error", "Extraction execution failed")
            logger.error("Structured extraction failed in browser", error=err_msg)
            return {
                "status": "error",
                "error_type": "extraction_failed",
                "error_detail": err_msg
            }
            
        value = result.get("value")
        return {
            "status": "ok",
            "data": value
        }
        
    except Exception as e:
        logger.error("Extraction action failed", error=str(e))
        return {
            "status": "error",
            "error_type": "extraction_failed",
            "error_detail": str(e)
        }
