import structlog
from typing import Dict
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def fetch_performance_metrics(session: CDPSession) -> Dict[str, float]:
    """
    Fetches the browser's performance metrics (e.g. JS heap size, layout counts, DOM nodes)
    and returns them formatted as a dictionary.
    """
    try:
        # Enable Performance monitoring
        await session.send("Performance.enable", {})
        
        response = await session.send("Performance.getMetrics", {})
        raw_metrics = response.get("metrics", [])
        
        # Flatten metric lists
        # Raw structure: [{"name": "JSHeapUsedSize", "value": 123456}, ...]
        metrics = {}
        for item in raw_metrics:
            metrics[item["name"]] = item["value"]
            
        logger.debug("Fetched browser performance metrics", 
                     js_heap_mb=round(metrics.get("JSHeapUsedSize", 0) / (1024 * 1024), 2),
                     dom_nodes=metrics.get("DOMNodes", 0))
                     
        return metrics
    except Exception as e:
        logger.error("Failed to retrieve performance metrics", error=str(e))
        return {}
