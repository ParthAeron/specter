import asyncio
import os
import re
import signal
import sys
import shutil
import subprocess
import platform
import structlog
from typing import Optional, Callable, Any
from pathlib import Path
from specter.install.installer import get_binary_name, find_binary, get_default_install_dir

logger = structlog.get_logger()

# Regex to parse the DevTools debugging WebSocket URL
DEVTOOLS_RE = re.compile(r"DevTools listening on (ws://127.0.0.1:(\d+)/devtools/browser/([a-f0-9\-]+))")

class ChromeProcess:
    def __init__(self, binary_path: Optional[str] = None, excision_mode: bool = False, window_size: tuple[int, int] = (1920, 1080)):
        self.binary_path = binary_path
        self.excision_mode = excision_mode
        self.window_size = window_size
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.port: Optional[int] = None
        self.ws_url: Optional[str] = None
        self.browser_id: Optional[str] = None

    async def start(self, startup_timeout: float = 10.0) -> None:
        bin_path = self._resolve_binary_path()
        args = self._build_args(bin_path)
        
        logger.info("Starting chrome-headless-shell process", path=str(bin_path), excision_mode=self.excision_mode)
        
        # Start Chrome process with stderr pipe
        self.proc = await asyncio.create_subprocess_exec(
            str(bin_path),
            *args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            preexec_fn=self._get_preexec_fn()
        )
        
        # Read stderr to discover port and ws_url
        try:
            await asyncio.wait_for(self._read_devtools_url(), timeout=startup_timeout)
        except Exception as e:
            logger.error("Failed to start Chrome or discover port within timeout", error=str(e))
            await self.stop()
            raise RuntimeError("Could not discover Chrome DevTools debugging port. Stderr parsing failed.") from e

    async def stop(self) -> None:
        if not self.proc:
            return
            
        logger.info("Stopping Chrome process", pid=self.proc.pid)
        
        try:
            if platform.system().lower() == "windows":
                # subprocess terminate on Windows sends TerminateProcess
                self.proc.terminate()
            else:
                self.proc.send_signal(signal.SIGTERM)
                
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warn("Chrome did not stop on SIGTERM, killing", pid=self.proc.pid)
                self.proc.kill()
                await self.proc.wait()
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error("Error during Chrome process shutdown", error=str(e))
        finally:
            self.proc = None
            self.port = None
            self.ws_url = None
            self.browser_id = None

    def _resolve_binary_path(self) -> Path:
        if self.binary_path:
            p = Path(self.binary_path)
            if p.is_file():
                return p
                
        # Look in default install dir
        default_dir = get_default_install_dir()
        binary_name = get_binary_name()
        bin_path = find_binary(default_dir, binary_name)
        if bin_path:
            return bin_path
            
        # Search PATH
        path_binary = shutil.which(binary_name)
        if path_binary:
            return Path(path_binary)
            
        # Standard system paths if installer was not run
        raise FileNotFoundError(
            "chrome-headless-shell binary not found. "
            "Please run 'python -m specter.install' first to download the binary automatically."
        )

    def _build_args(self, bin_path: Path) -> list[str]:
        args = [
            "--remote-debugging-port=0",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--no-first-run",
            "--safebrowsing-disable-auto-update",
            "--disable-webrtc",
            f"--window-size={self.window_size[0]},{self.window_size[1]}",
            "--js-flags=--max-old-space-size=512",
            "--disable-features=TLS13EarlyData",
            "about:blank"
        ]
        
        # Apply Excision Mode switches to disable unneeded subsystems
        if self.excision_mode:
            args.extend([
                "--blink-settings=imagesEnabled=false",
                "--disable-audio",
                "--mute-audio",
                "--disable-3d-apis",
                "--disable-software-rasterizer",
                "--disable-speech-api",
                "--disable-notifications",
                "--disable-voip-with-rate-control"
            ])
            
        return args

    async def _read_devtools_url(self) -> None:
        if not self.proc or not self.proc.stderr:
            return

        while True:
            line_bytes = await self.proc.stderr.readline()
            if not line_bytes:
                break
                
            line = line_bytes.decode("utf-8").strip()
            match = DEVTOOLS_RE.search(line)
            if match:
                self.ws_url = match.group(1)
                self.port = int(match.group(2))
                self.browser_id = match.group(3)
                logger.info("Discovered Chrome DevTools websocket URL", port=self.port, ws_url=self.ws_url)
                return

    def _get_preexec_fn(self) -> Optional[Callable[[], Any]]:
        # Avoid orphan processes on POSIX systems if parent python exits abruptly
        if platform.system().lower() != "windows":
            # Use prctl to terminate child if parent exits
            def set_death_signal():
                try:
                    import ctypes
                    if platform.system().lower() == "linux":
                        libc = ctypes.CDLL(None)
                        # PR_SET_PDEATHSIG is 1, SIGKILL is 9
                        libc.prctl(1, 9)
                except Exception:
                    pass
            return set_death_signal
        return None
