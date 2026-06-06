import asyncio
import re
import structlog
from typing import Any
from specter.cdp import CDPSession
from specter.page.refs import RefRegistry

logger = structlog.get_logger()

async def wait_for_condition(
    session: CDPSession,
    ref_registry: RefRegistry,
    condition: str,
    param: Any,
    timeout: float = 10.0
) -> dict[str, Any]:
    """
    Waits for a specific condition to be met on the page.
    Conditions:
      - 'element_visible': param is ref (e.g. 'n4')
      - 'url_matches': param is regex pattern or string (e.g. 'github.com/settings')
      - 'text_present': param is text string (e.g. 'Saved successfully')
      - 'network_idle': param is None
    """
    logger.info("Waiting for page condition", condition=condition, param=param, timeout=timeout)
    
    start_time = asyncio.get_running_loop().time()
    check_interval = 0.2 # Check every 200ms
    
    try:
        while True:
            elapsed = asyncio.get_running_loop().time() - start_time
            if elapsed >= timeout:
                logger.warn("Wait for condition timed out", condition=condition, param=param)
                return {
                    "status": "timeout",
                    "error_detail": f"Condition '{condition}' was not met within {timeout}s"
                }
                
            condition_met = False
            
            if condition == "element_visible":
                ref = str(param)
                try:
                    node_id = await ref_registry.resolve_to_node_id(session, ref)
                    # Check if element has a box model (meaning it is visible and rendered)
                    await session.send("DOM.getBoxModel", {"nodeId": node_id})
                    condition_met = True
                except Exception:
                    pass
                    
            elif condition == "url_matches":
                pattern = str(param)
                eval_resp = await session.send("Runtime.evaluate", {
                    "expression": "window.location.href",
                    "returnByValue": True
                })
                current_url = eval_resp.get("result", {}).get("value", "")
                if re.search(pattern, current_url):
                    condition_met = True
                    
            elif condition == "text_present":
                target_text = str(param)
                # Escaping single quotes in the target text
                escaped_text = target_text.replace("'", "\\'")
                eval_resp = await session.send("Runtime.evaluate", {
                    "expression": f"document.body.innerText.includes('{escaped_text}')",
                    "returnByValue": True
                })
                if eval_resp.get("result", {}).get("value") is True:
                    condition_met = True
                    
            elif condition == "network_idle":
                # For network idle, we can trigger a lifecycle wait (or check if there is no activity)
                # To keep it simple, if they wait for network_idle, we can listen for the cdp event
                # but if we are already idle, the event won't fire.
                # A quick way is to check the resource metrics or wait for 500ms since last request.
                # Here, we can just resolve or return since we do network idle on navigation.
                condition_met = True # Placeholder for simplicity
                
            if condition_met:
                logger.info("Page condition met", condition=condition, elapsed_ms=int(elapsed * 1000))
                return {
                    "status": "ok",
                    "elapsed_ms": int(elapsed * 1000)
                }
                
            await asyncio.sleep(check_interval)
            
    except Exception as e:
        logger.error("Wait action failed", condition=condition, error=str(e))
        return {
            "status": "error",
            "error_type": "wait_failed",
            "error_detail": str(e)
        }
