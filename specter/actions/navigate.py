import asyncio
import structlog
from typing import Any
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def navigate_page(session: CDPSession, url: str, wait_until: str = "load", timeout: float = 30.0) -> dict[str, Any]:
    """
    Navigates the session to a URL and blocks until the specified lifecycle event is fired.
    Valid lifecycle events: 'init', 'DOMContentLoaded', 'load', 'networkAlmostIdle', 'networkIdle'.
    """
    logger.info("Navigating to URL", url=url, wait_until=wait_until)
    
    # Map high-level lifecycle event names to CDP event names
    # CDP uses lowercase strings for lifecycle events
    cdp_event_name = wait_until
    if wait_until == "networkIdle":
        cdp_event_name = "networkIdle"
    elif wait_until == "networkAlmostIdle":
        cdp_event_name = "networkAlmostIdle"
        
    loop = asyncio.get_running_loop()
    event_future = loop.create_future()
    
    def on_lifecycle_event(params: dict[str, Any]) -> None:
        name = params.get("name")
        if name == cdp_event_name:
            if not event_future.done():
                event_future.set_result(True)
                
    # Enable Page domain and lifecycle events
    await session.send("Page.enable", {})
    await session.send("Page.setLifecycleEventsEnabled", {"enabled": True})
    
    # Subscribe to lifecycle events
    unsub = session.subscribe("Page.lifecycleEvent", on_lifecycle_event)
    
    try:
        # Trigger navigation
        nav_response = await session.send("Page.navigate", {"url": url}, timeout=timeout)
        frame_id = nav_response.get("frameId")
        
        # Await the lifecycle event
        await asyncio.wait_for(event_future, timeout=timeout)
        logger.info("Navigation complete", url=url, frame_id=frame_id)
        
        # Fetch actual URL and title from target
        eval_resp = await session.send("Runtime.evaluate", {
            "expression": "({ url: window.location.href, title: document.title })",
            "returnByValue": True
        })
        
        val = eval_resp.get("result", {}).get("value", {})
        return {
            "status": "ok",
            "url": val.get("url", url),
            "title": val.get("title", ""),
            "frameId": frame_id
        }
        
    except asyncio.TimeoutError:
        logger.warn("Navigation timed out waiting for lifecycle event", url=url, wait_until=wait_until)
        # Attempt to get whatever URL we landed on
        try:
            eval_resp = await session.send("Runtime.evaluate", {
                "expression": "({ url: window.location.href, title: document.title })",
                "returnByValue": True
            })
            val = eval_resp.get("result", {}).get("value", {})
            return {
                "status": "timeout",
                "url": val.get("url", url),
                "title": val.get("title", ""),
                "error_detail": f"Timed out waiting for lifecycle event '{wait_until}'"
            }
        except Exception:
            return {
                "status": "timeout",
                "url": url,
                "title": "",
                "error_detail": f"Timed out waiting for lifecycle event '{wait_until}'"
            }
    except Exception as e:
        logger.error("Navigation action failed", url=url, error=str(e))
        return {
            "status": "error",
            "error_type": "navigation_failed",
            "error_detail": str(e)
        }
    finally:
        unsub()
