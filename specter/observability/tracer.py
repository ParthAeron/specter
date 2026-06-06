import time
import structlog
from typing import Any, Dict, List
from specter.cdp import CDPSession

logger = structlog.get_logger()

class SessionTracer:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.logs: List[Dict[str, Any]] = []
        self._unsub_tokens = []

    def trace_send(self, method: str, params: dict[str, Any], msg_id: int) -> None:
        entry = {
            "ts": time.time(),
            "dir": "send",
            "id": msg_id,
            "method": method,
            "params": params
        }
        self.logs.append(entry)
        logger.debug("Trace send", **entry)

    def trace_recv(self, response: dict[str, Any], msg_id: int) -> None:
        entry = {
            "ts": time.time(),
            "dir": "recv",
            "id": msg_id,
            "result": response.get("result"),
            "error": response.get("error")
        }
        self.logs.append(entry)
        logger.debug("Trace recv", **entry)

    def trace_event(self, method: str, params: dict[str, Any]) -> None:
        entry = {
            "ts": time.time(),
            "dir": "event",
            "method": method,
            "params": params
        }
        self.logs.append(entry)
        logger.debug("Trace event", **entry)

    async def enable_console_monitoring(self, session: CDPSession) -> None:
        """
        Enables Runtime/Console domains and binds listeners for console calls and page exceptions.
        """
        await session.send("Runtime.enable", {})
        
        # Subscribe to console calls
        t1 = session.subscribe("Runtime.consoleAPICalled", self._handle_console_api_called)
        # Subscribe to unhandled exceptions
        t2 = session.subscribe("Runtime.exceptionThrown", self._handle_exception_thrown)
        
        self._unsub_tokens.extend([t1, t2])

    def disable_console_monitoring(self) -> None:
        for unsub in self._unsub_tokens:
            unsub()
        self._unsub_tokens.clear()

    def _handle_console_api_called(self, params: dict[str, Any]) -> None:
        log_type = params.get("type", "log")
        args = params.get("args", [])
        
        # Convert remote arguments to basic string values
        arg_values = []
        for arg in args:
            val = arg.get("value")
            if val is not None:
                arg_values.append(str(val))
            elif "description" in arg:
                arg_values.append(arg["description"])
                
        message = " ".join(arg_values)
        entry = {
            "ts": time.time(),
            "dir": "console",
            "type": log_type,
            "message": message
        }
        self.logs.append(entry)
        logger.info("Page console log", type=log_type, message=message, session_id=self.session_id)

    def _handle_exception_thrown(self, params: dict[str, Any]) -> None:
        details = params.get("exceptionDetails", {})
        text = details.get("text", "Uncaught Exception")
        exception = details.get("exception", {})
        description = exception.get("description", "No stack trace available")
        
        entry = {
            "ts": time.time(),
            "dir": "exception",
            "message": text,
            "description": description
        }
        self.logs.append(entry)
        logger.error("Page script exception thrown", message=text, description=description, session_id=self.session_id)

    def dump_traces(self) -> List[Dict[str, Any]]:
        return self.logs
