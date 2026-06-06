import asyncio
import json
import itertools
import websockets
import structlog
from typing import Any, Callable, Dict, Optional, Set
from specter.cdp.types import CDPRequest, CDPResponse, CDPEvent

logger = structlog.get_logger()

class CDPError(Exception):
    def __init__(self, error_data: dict[str, Any]):
        self.code = error_data.get("code")
        self.message = error_data.get("message")
        self.data = error_data.get("data")
        super().__init__(f"CDP Error {self.code}: {self.message} ({self.data})")

class CDPTransport:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._id_counter = itertools.count(start=1)
        self._in_flight: Dict[int, asyncio.Future[CDPResponse]] = {}
        self._event_handlers: Dict[str, Set[Callable[[CDPEvent], Any]]] = {}
        self._generic_event_handlers: Set[Callable[[CDPEvent], Any]] = set()
        self._disconnect_handlers: Set[Callable[[], Any]] = set()
        self._reader_task: Optional[asyncio.Task] = None
        self._is_connected = False

    async def connect(self, timeout: float = 10.0) -> None:
        if self._is_connected:
            return
            
        logger.info("Connecting to Chrome CDP", url=self.ws_url)
        try:
            self.ws = await websockets.connect(self.ws_url, max_size=None)
            self._is_connected = True
            self._reader_task = asyncio.create_task(self._read_loop())
            logger.info("Connected to Chrome CDP successfully")
        except Exception as e:
            logger.error("Failed to connect to Chrome CDP", error=str(e))
            self._is_connected = False
            raise

    async def disconnect(self) -> None:
        self._is_connected = False
        
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
            
        if self.ws:
            await self.ws.close()
            self.ws = None
            
        # Cancel all in-flight futures
        for fut in self._in_flight.values():
            if not fut.done():
                fut.set_exception(ConnectionError("CDP transport disconnected"))
        self._in_flight.clear()
        
        logger.info("Disconnected from Chrome CDP")

    async def send(self, method: str, params: dict[str, Any], session_id: Optional[str] = None, timeout: Optional[float] = 30.0) -> dict[str, Any]:
        if not self._is_connected or not self.ws:
            raise ConnectionError("Not connected to CDP")
            
        msg_id = next(self._id_counter)
        request: CDPRequest = {
            "id": msg_id,
            "method": method,
            "params": params
        }
        if session_id:
            request["sessionId"] = session_id

        fut = asyncio.get_running_loop().create_future()
        self._in_flight[msg_id] = fut
        
        payload = json.dumps(request)
        logger.debug("CDP send", method=method, id=msg_id, session_id=session_id)
        await self.ws.send(payload)
        
        try:
            if timeout is not None:
                response = await asyncio.wait_for(fut, timeout=timeout)
            else:
                response = await fut
        except asyncio.TimeoutError:
            self._in_flight.pop(msg_id, None)
            logger.error("CDP command timeout", method=method, id=msg_id)
            raise TimeoutError(f"CDP command {method} timed out after {timeout}s")
        except Exception:
            self._in_flight.pop(msg_id, None)
            raise
            
        if "error" in response:
            logger.error("CDP command error response", method=method, id=msg_id, error=response["error"])
            raise CDPError(response["error"])
            
        return response.get("result", {})

    def subscribe(self, method: str, handler: Callable[[CDPEvent], Any]) -> Callable[[], None]:
        if method not in self._event_handlers:
            self._event_handlers[method] = set()
        self._event_handlers[method].add(handler)
        
        def unsubscribe():
            self._event_handlers[method].remove(handler)
            if not self._event_handlers[method]:
                del self._event_handlers[method]
        return unsubscribe

    def subscribe_all(self, handler: Callable[[CDPEvent], Any]) -> Callable[[], None]:
        self._generic_event_handlers.add(handler)
        
        def unsubscribe():
            self._generic_event_handlers.remove(handler)
        return unsubscribe

    def on_disconnect(self, handler: Callable[[], Any]) -> Callable[[], None]:
        self._disconnect_handlers.add(handler)
        
        def remove():
            self._disconnect_handlers.remove(handler)
        return remove

    async def _read_loop(self) -> None:
        try:
            while self._is_connected and self.ws:
                message_str = await self.ws.recv()
                message: dict[str, Any] = json.loads(message_str)
                
                msg_id = message.get("id")
                if msg_id is not None:
                    # Resolve command response
                    fut = self._in_flight.pop(msg_id, None)
                    if fut and not fut.done():
                        fut.set_result(message)
                else:
                    # Process event
                    event: CDPEvent = {
                        "method": message["method"],
                        "params": message.get("params", {}),
                        "sessionId": message.get("sessionId")
                    }
                    logger.debug("CDP event received", method=event["method"], session_id=event["sessionId"])
                    
                    # Fan out to generic handlers
                    for handler in list(self._generic_event_handlers):
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                asyncio.create_task(handler(event))
                            else:
                                handler(event)
                        except Exception as e:
                            logger.error("Error in generic event handler", error=str(e), method=event["method"])
                            
                    # Fan out to specific handlers
                    handlers = self._event_handlers.get(event["method"], set())
                    for handler in list(handlers):
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                asyncio.create_task(handler(event))
                            else:
                                handler(event)
                        except Exception as e:
                            logger.error("Error in cdp event handler", error=str(e), method=event["method"])
                            
        except websockets.exceptions.ConnectionClosed as e:
            logger.warn("CDP WebSocket connection closed", code=e.code, reason=e.reason)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Exception in CDP read loop", error=str(e))
        finally:
            self._is_connected = False
            for handler in list(self._disconnect_handlers):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                except Exception as ex:
                    logger.error("Error running disconnect handler", error=str(ex))
