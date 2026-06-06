import asyncio
import structlog
from typing import Any, Callable, Dict, Set
from specter.cdp.transport import CDPTransport
from specter.cdp.types import CDPEvent

logger = structlog.get_logger()

class CDPSession:
    def __init__(self, transport: CDPTransport, session_id: str, target_id: str):
        self.transport = transport
        self.session_id = session_id
        self.target_id = target_id
        self._event_handlers: Dict[str, Set[Callable[[dict[str, Any]], Any]]] = {}
        self._generic_event_handlers: Set[Callable[[str, dict[str, Any]], Any]] = set()
        self._unsub_tokens: list[Callable[[], None]] = []
        
        # Subscribe to transport-level events to filter and route to session-level handlers
        self._unsub_tokens.append(self.transport.subscribe_all(self._on_transport_event))

    async def send(self, method: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        return await self.transport.send(method, params, session_id=self.session_id, timeout=timeout)

    def subscribe(self, method: str, handler: Callable[[dict[str, Any]], Any]) -> Callable[[], None]:
        if method not in self._event_handlers:
            self._event_handlers[method] = set()
        self._event_handlers[method].add(handler)
        
        def unsubscribe():
            if method in self._event_handlers:
                self._event_handlers[method].remove(handler)
                if not self._event_handlers[method]:
                    del self._event_handlers[method]
        return unsubscribe

    def subscribe_all(self, handler: Callable[[str, dict[str, Any]], Any]) -> Callable[[], None]:
        self._generic_event_handlers.add(handler)
        
        def unsubscribe():
            self._generic_event_handlers.remove(handler)
        return unsubscribe

    def detach(self) -> None:
        for unsub in self._unsub_tokens:
            unsub()
        self._unsub_tokens.clear()
        self._event_handlers.clear()
        self._generic_event_handlers.clear()
        logger.debug("CDP session detached", session_id=self.session_id)

    def _on_transport_event(self, event: CDPEvent) -> None:
        if event.get("sessionId") != self.session_id:
            return
            
        method = event["method"]
        params = event.get("params", {})
        
        # Dispatch to generic handlers
        for handler in list(self._generic_event_handlers):
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(method, params))
                else:
                    handler(method, params)
            except Exception as e:
                logger.error("Error in session-level generic event handler", error=str(e), method=method)

        # Dispatch to specific method handlers
        handlers = self._event_handlers.get(method, set())
        for handler in list(handlers):
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(params))
                else:
                    handler(params)
            except Exception as e:
                logger.error("Error in session-level event handler", error=str(e), method=method)
