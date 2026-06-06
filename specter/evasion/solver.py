import asyncio
import time
import aiohttp
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = structlog.get_logger()

@dataclass
class SolveParams:
    sitekey: str
    page_url: str
    image_data: Optional[str] = None  # Base64 string for image captchas

@dataclass
class SolveResult:
    token: str
    latency_ms: int

class CaptchaSolver(ABC):
    @abstractmethod
    async def solve(self, captcha_type: str, params: SolveParams) -> SolveResult:
        """
        Solves the given captcha type and returns a token with latency metrics.
        """
        pass

class CapSolver(CaptchaSolver):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoint = "https://api.capsolver.com"

    async def solve(self, captcha_type: str, params: SolveParams) -> SolveResult:
        start_time = time.time()
        
        # Map our types to CapSolver's task types
        task_type = "ReCaptchaV2TaskProxyLess"
        if captcha_type == "hcaptcha":
            task_type = "HCaptchaTaskProxyLess"
        elif captcha_type == "cloudflare_turnstile":
            task_type = "AntiTurnstileTaskProxyLess"
            
        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": task_type,
                "websiteURL": params.page_url,
                "websiteKey": params.sitekey
            }
        }
        
        async with aiohttp.ClientSession() as session:
            # 1. Create task
            async with session.post(f"{self.endpoint}/createTask", json=payload) as resp:
                result = await resp.json()
                if result.get("errorId", 0) != 0:
                    raise RuntimeError(f"CapSolver error: {result.get('errorDescription')}")
                task_id = result.get("taskId")
                
            logger.info("CapSolver task created", task_id=task_id)
            
            # 2. Poll for solution
            poll_payload = {"clientKey": self.api_key, "taskId": task_id}
            max_retries = 30
            for _ in range(max_retries):
                await asyncio.sleep(2.0)
                async with session.post(f"{self.endpoint}/getTaskResult", json=poll_payload) as resp:
                    task_res = await resp.json()
                    status = task_res.get("status")
                    
                    if status == "ready":
                        token = task_res.get("solution", {}).get("gRecaptchaResponse") or task_res.get("solution", {}).get("token")
                        if not token:
                            raise RuntimeError("Task succeeded but no solution token was returned")
                        latency = int((time.time() - start_time) * 1000)
                        return SolveResult(token=token, latency_ms=latency)
                    elif status == "failed":
                        raise RuntimeError("CapSolver task failed inside solver engine")
                        
            raise TimeoutError("CapSolver solve timeout exceeded")

class TwoCaptcha(CaptchaSolver):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.endpoint = "https://2captcha.com"

    async def solve(self, captcha_type: str, params: SolveParams) -> SolveResult:
        start_time = time.time()
        
        method = "userrecaptcha"
        if captcha_type == "hcaptcha":
            method = "hcaptcha"
        elif captcha_type == "cloudflare_turnstile":
            method = "turnstile"
            
        payload = {
            "key": self.api_key,
            "method": method,
            "googlekey": params.sitekey,
            "pageurl": params.page_url,
            "json": 1
        }
        
        async with aiohttp.ClientSession() as session:
            # 1. Create request
            async with session.post(f"{self.endpoint}/in.php", data=payload) as resp:
                res = await resp.json()
                if res.get("status") != 1:
                    raise RuntimeError(f"2Captcha creation failed: {res.get('request')}")
                request_id = res.get("request")
                
            logger.info("2Captcha task created", request_id=request_id)
            
            # 2. Poll result
            poll_url = f"{self.endpoint}/res.php?key={self.api_key}&action=get&id={request_id}&json=1"
            max_retries = 30
            for _ in range(max_retries):
                await asyncio.sleep(3.0)
                async with session.get(poll_url) as resp:
                    poll_res = await resp.json()
                    if poll_res.get("status") == 1:
                        token = poll_res.get("request")
                        latency = int((time.time() - start_time) * 1000)
                        return SolveResult(token=token, latency_ms=latency)
                    elif poll_res.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                        raise RuntimeError("2Captcha flagged challenge as unsolvable")
                        
            raise TimeoutError("2Captcha solve timeout exceeded")
