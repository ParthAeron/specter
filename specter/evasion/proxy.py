import aiohttp
import structlog
from typing import Any, List, Optional

logger = structlog.get_logger()

class ProxyConfig:
    def __init__(self, server: str, username: Optional[str] = None, password: Optional[str] = None, bypass: Optional[str] = None):
        self.server = server # E.g. "http://1.2.3.4:5678" or "socks5://1.2.3.4:5678"
        self.username = username
        self.password = password
        self.bypass = bypass

    def to_dict(self) -> dict[str, Any]:
        d = {"server": self.server}
        if self.username:
            d["username"] = self.username
        if self.password:
            d["password"] = self.password
        if self.bypass:
            d["bypass"] = self.bypass
        return d

class ProxyRotator:
    def __init__(self, proxies: List[ProxyConfig]):
        self.proxies = proxies
        self._index = 0
        self._failures: dict[str, int] = {}
        
    def get_current(self) -> Optional[ProxyConfig]:
        if not self.proxies:
            return None
        return self.proxies[self._index]

    def get_next(self, failed_proxy: Optional[ProxyConfig] = None) -> Optional[ProxyConfig]:
        """
        Rotates to the next proxy in the list.
        If a failed_proxy is specified, increments its failure count and potentially discards it.
        """
        if not self.proxies:
            return None
            
        if failed_proxy:
            server = failed_proxy.server
            self._failures[server] = self._failures.get(server, 0) + 1
            logger.warn("Proxy failure logged", server=server, total_failures=self._failures[server])
            
            # If a proxy fails 3 consecutive times, remove it from rotation
            if self._failures[server] >= 3:
                logger.error("Discarding broken proxy from rotation pool", server=server)
                if failed_proxy in self.proxies:
                    self.proxies.remove(failed_proxy)
                    
        if not self.proxies:
            return None
            
        self._index = (self._index + 1) % len(self.proxies)
        selected = self.proxies[self._index]
        logger.info("Rotated to next proxy", server=selected.server)
        return selected

    @staticmethod
    async def verify_proxy(proxy: ProxyConfig, test_url: str = "https://httpbin.org/ip") -> Optional[str]:
        """
        Verifies that a proxy connection works and returns the external IP.
        Returns None if verification fails.
        """
        logger.info("Verifying proxy connection", server=proxy.server)
        
        # Configure aiohttp proxy args
        proxy_url = proxy.server
        proxy_auth = None
        if proxy.username and proxy.password:
            proxy_auth = aiohttp.BasicAuth(proxy.username, proxy.password)
            
        try:
            async with aiohttp.ClientSession() as session:
                # Set a strict 5-second timeout for verification
                timeout = aiohttp.ClientTimeout(total=5.0)
                async with session.get(test_url, proxy=proxy_url, proxy_auth=proxy_auth, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        origin = data.get("origin")
                        logger.info("Proxy connection verified successfully", external_ip=origin)
                        return origin
                    else:
                        logger.warn("Proxy verification returned bad status", status=resp.status)
                        return None
        except Exception as e:
            logger.warn("Proxy verification failed", error=str(e), server=proxy.server)
            return None

def parse_proxy_string(proxy_str: Optional[str]) -> Optional[dict[str, Any]]:
    """
    Parses a proxy URI string (e.g. 'socks5://user:pass@host:port') into a dict.
    """
    if not proxy_str:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_str)
        # If no scheme, default to http
        scheme = parsed.scheme if parsed.scheme else "http"
        hostname = parsed.hostname if parsed.hostname else parsed.path.split(":")[0]
        port = parsed.port
        if not port and ":" in parsed.path:
            try:
                port = int(parsed.path.split(":")[-1])
            except ValueError:
                pass
        
        server = f"{scheme}://{hostname}"
        if port:
            server += f":{port}"
            
        config = {"server": server}
        if parsed.username:
            config["username"] = parsed.username
        if parsed.password:
            config["password"] = parsed.password
        return config
    except Exception:
        return {"server": proxy_str}

