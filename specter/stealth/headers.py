import random
import structlog
from typing import Any, Dict, Optional
from specter.cdp import CDPSession

logger = structlog.get_logger()

# Realistic desktop User-Agent strings matching recent Chrome releases
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def get_ua_metadata(ua: str) -> dict[str, Any]:
    # Determine platform from user agent string
    platform = "Windows"
    platform_version = "10.0.0"
    if "Macintosh" in ua:
        platform = "macOS"
        platform_version = "14.2.1"
    elif "Linux" in ua:
        platform = "Linux"
        platform_version = ""
        
    return {
        "brands": [
            {"brand": "Chromium", "version": "122"},
            {"brand": "Not(A:Brand", "version": "24"},
            {"brand": "Google Chrome", "version": "122"}
        ],
        "fullVersionList": [
            {"brand": "Chromium", "version": "122.0.6261.94"},
            {"brand": "Not(A:Brand", "version": "24.0.0.0"},
            {"brand": "Google Chrome", "version": "122.0.6261.94"}
        ],
        "fullVersion": "122.0.6261.94",
        "platform": platform,
        "platformVersion": platform_version,
        "architecture": "x86",
        "model": "",
        "mobile": False,
        "bitness": "64",
        "wow64": False
    }

async def apply_stealth_headers(session: CDPSession, user_agent: Optional[str] = None) -> None:
    if not user_agent:
        user_agent = random.choice(UA_POOL)
        
    metadata = get_ua_metadata(user_agent)
    logger.info("Applying User-Agent and client hints override", user_agent=user_agent, platform=metadata["platform"])
    
    try:
        # 1. Override Network User Agent
        await session.send("Network.setUserAgentOverride", {
            "userAgent": user_agent,
            "userAgentMetadata": metadata
        })
        
        # 2. Inject extra client-hint headers
        headers = {
            "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": f'"{metadata["platform"]}"'
        }
        await session.send("Network.setExtraHTTPHeaders", {
            "headers": headers
        })
    except Exception as e:
        logger.error("Failed to apply stealth headers", error=str(e), session_id=session.session_id)
