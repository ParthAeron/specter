from typing import Any, TypedDict, Optional

class CDPRequest(TypedDict):
    id: int
    method: str
    params: dict[str, Any]
    sessionId: Optional[str]

class CDPResponse(TypedDict, total=False):
    id: int
    result: dict[str, Any]
    error: dict[str, Any]
    sessionId: str

class CDPEvent(TypedDict):
    method: str
    params: dict[str, Any]
    sessionId: Optional[str]
