from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class SessionCreateRequest(BaseModel):
    proxy_config: Optional[Dict[str, Any]] = Field(default=None, description="Optional dict containing proxy settings (server, username, password, bypass)")
    excision_mode: bool = Field(default=False, description="Enable Excision Mode to disable images, WebGL, audio subsystems")
    solve_captcha: bool = Field(default=True, description="Automatically detect and solve CAPTCHAs via pluggable solver adapters")
    allow_images: bool = Field(default=False, description="Explicitly allow image loading (overrides excision mode)")

class SessionActionRequest(BaseModel):
    action: str = Field(..., description="Action to run: navigate, click, fill, scroll, extract, wait_for, snapshot")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters corresponding to target action type")

class PageMetadata(BaseModel):
    url: str
    title: str

class SessionActionResponse(BaseModel):
    status: str = Field(..., description="Response outcome: ok, error, captcha, recovered")
    session_id: str
    page: Optional[PageMetadata] = None
    snapshot: Optional[str] = None
    diff: Optional[Dict[str, Any]] = None
    captcha_type: Optional[str] = None
    error_type: Optional[str] = None
    error_detail: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    data: Optional[Any] = Field(default=None, description="The payload returned by data extraction, text, or query actions")
