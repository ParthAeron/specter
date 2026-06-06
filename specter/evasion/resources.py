import base64
import asyncio
import structlog
from typing import Any, Dict, List, Optional
from specter.cdp import CDPSession

logger = structlog.get_logger()

# Common ad/analytics domains to block
TRACKER_PATTERNS = [
    "google-analytics.com",
    "googletagmanager.com",
    "googleadservices.com",
    "doubleclick.net",
    "amplitude.com",
    "mixpanel.com",
    "hotjar.com",
    "facebook.net",
    "sentry.io",
    "bugsnag.com"
]

class RequestInterceptor:
    def __init__(
        self,
        block_media: bool = True,
        block_fonts: bool = True,
        block_trackers: bool = True,
        allow_images: bool = False
    ):
        self.block_media = block_media
        self.block_fonts = block_fonts
        self.block_trackers = block_trackers
        self.allow_images = allow_images
        
        self.mocks: Dict[str, Dict[str, Any]] = {} # Maps URL substring -> Mock response dict
        self._unsub = None

    def register_mock(self, url_pattern: str, body: str, status_code: int = 200, content_type: str = "application/json") -> None:
        """
        Registers a stub response for any request containing url_pattern.
        """
        self.mocks[url_pattern] = {
            "body": body,
            "status": status_code,
            "headers": [
                {"name": "Content-Type", "value": content_type},
                {"name": "Access-Control-Allow-Origin", "value": "*"}
            ]
        }
        logger.info("Registered mock route", pattern=url_pattern)

    def clear_mocks(self) -> None:
        self.mocks.clear()

    async def enable(self, session: CDPSession) -> None:
        """
        Enables Fetch interception and hooks up the requestPaused listener.
        """
        await session.send("Fetch.enable", {
            "patterns": [{"requestStage": "Request"}]
        })
        self._unsub = session.subscribe("Fetch.requestPaused", lambda p: asyncio.create_task(self._on_request_paused(session, p)))

    def disable(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _on_request_paused(self, session: CDPSession, params: dict[str, Any]) -> None:
        request_id = params["requestId"]
        request = params["request"]
        url = request.get("url", "")
        resource_type = params.get("resourceType")
        
        # 1. Check if resource needs blocking
        should_block = False
        reason = "BlockedByClient"
        
        # Block fonts
        if self.block_fonts and resource_type == "Font":
            should_block = True
            reason = "BlockedByClient"
            
        # Block media (video/audio)
        elif self.block_media and resource_type in ("Media", "Audio", "Video"):
            should_block = True
            reason = "BlockedByClient"
            
        # Block images (if not explicitly allowed)
        elif not self.allow_images and resource_type == "Image":
            should_block = True
            reason = "BlockedByClient"
            
        # Block trackers/analytics
        elif self.block_trackers:
            for pattern in TRACKER_PATTERNS:
                if pattern in url:
                    should_block = True
                    reason = "BlockedByClient"
                    break
                    
        if should_block:
            logger.debug("Blocking resource request", url=url[:60], type=resource_type)
            try:
                await session.send("Fetch.failRequest", {
                    "requestId": request_id,
                    "errorReason": reason
                })
            except Exception as e:
                logger.error("Failed to block request", error=str(e), request_id=request_id)
            return

        # 2. Check if resource matches a stub mock
        for pattern, mock_data in self.mocks.items():
            if pattern in url:
                logger.info("Intercepted and mocking request", url=url[:60])
                
                # Base64 encode the body
                body_str = mock_data["body"]
                b64_body = base64.b64encode(body_str.encode("utf-8")).decode("utf-8")
                
                try:
                    await session.send("Fetch.fulfillRequest", {
                        "requestId": request_id,
                        "responseCode": mock_data["status"],
                        "responseHeaders": mock_data["headers"],
                        "body": b64_body
                    })
                except Exception as e:
                    logger.error("Failed to mock fulfill request", error=str(e), request_id=request_id)
                return

        # 3. Otherwise, continue request normally
        try:
            await session.send("Fetch.continueRequest", {
                "requestId": request_id
            })
        except Exception as e:
            logger.debug("Failed to continue request (might be resolved)", error=str(e), request_id=request_id)
