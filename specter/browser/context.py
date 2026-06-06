import asyncio
import structlog
from typing import Any, Dict, Optional, List, Callable
from specter.cdp import CDPSession, CDPTransport

logger = structlog.get_logger()

class BrowserContext:
    def __init__(self, transport: CDPTransport, context_id: str, proxy_config: Optional[dict[str, Any]] = None):
        self.transport = transport
        self.context_id = context_id
        self.proxy_config = proxy_config
        self.sessions: List[CDPSession] = []
        self._closed = False

    async def create_page(self, url: str = "about:blank") -> CDPSession:
        if self._closed:
            raise RuntimeError("Browser context already closed")

        logger.info("Creating page in context", context_id=self.context_id, url=url)
        
        # 1. Create target
        response = await self.transport.send("Target.createTarget", {
            "url": url,
            "browserContextId": self.context_id
        })
        target_id = response["targetId"]
        
        # 2. Attach to target
        attach_response = await self.transport.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        session_id = attach_response["sessionId"]
        
        session = CDPSession(self.transport, session_id, target_id)
        self.sessions.append(session)
        
        # 3. Setup proxy auth if credentials are provided
        if self.proxy_config and "username" in self.proxy_config and "password" in self.proxy_config:
            await self._setup_proxy_auth(session)
            
        return session

    async def close(self) -> None:
        if self._closed:
            return
            
        logger.info("Closing browser context", context_id=self.context_id)
        self._closed = True
        
        # Detach all session wrappers
        for session in self.sessions:
            try:
                session.detach()
            except Exception:
                pass
        self.sessions.clear()
        
        # Dispose context in Chrome
        try:
            await self.transport.send("Target.disposeBrowserContext", {
                "browserContextId": self.context_id
            })
        except Exception as e:
            logger.error("Failed to dispose browser context in Chrome", error=str(e), context_id=self.context_id)

    async def _setup_proxy_auth(self, session: CDPSession) -> None:
        username = self.proxy_config["username"]
        password = self.proxy_config["password"]
        
        # Enable Fetch intercept for this page session
        await session.send("Fetch.enable", {
            "patterns": [{"requestStage": "Request"}]
        })
        
        # Subscribe to auth challenges
        session.subscribe("Fetch.authRequired", self._make_auth_handler(session, username, password))
        
    def _make_auth_handler(self, session: CDPSession, username: str, password: str) -> Callable[[dict[str, Any]], Any]:
        async def handle_auth(params: dict[str, Any]) -> None:
            request_id = params["requestId"]
            challenge = params.get("authChallenge", {})
            
            if challenge.get("source") == "Proxy":
                logger.debug("Handling proxy auth challenge", request_id=request_id, username=username)
                try:
                    await session.send("Fetch.continueWithAuth", {
                        "requestId": request_id,
                        "authChallengeResponse": {
                            "response": "ProvideCredentials",
                            "username": username,
                            "password": password
                        }
                    })
                except Exception as e:
                    logger.error("Failed to solve proxy auth challenge", error=str(e), request_id=request_id)
            else:
                # If server auth, just default cancel or continue
                try:
                    await session.send("Fetch.continueWithAuth", {
                        "requestId": request_id,
                        "authChallengeResponse": {
                            "response": "Default"
                        }
                    })
                except Exception as e:
                    logger.error("Failed to pass default auth challenge", error=str(e), request_id=request_id)
                    
        return lambda params: asyncio.create_task(handle_auth(params))
