import asyncio
import structlog
from typing import Any, Dict, List, Optional
from specter.browser.process import ChromeProcess
from specter.browser.context import BrowserContext
from specter.cdp import CDPTransport, CDPError

logger = structlog.get_logger()

class BrowserProcessEntry:
    def __init__(self, process: ChromeProcess, transport: CDPTransport):
        self.process = process
        self.transport = transport
        self.active_contexts: int = 0
        self.is_healthy = True

class ProcessPool:
    def __init__(
        self,
        min_processes: int = 2,
        max_processes: int = 5,
        max_contexts_per_proc: int = 10,
        health_check_interval: float = 5.0,
        excision_mode: bool = False
    ):
        self.min_processes = min_processes
        self.max_processes = max_processes
        self.max_contexts_per_proc = max_contexts_per_proc
        self.health_check_interval = health_check_interval
        self.excision_mode = excision_mode
        
        self.entries: List[BrowserProcessEntry] = []
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
            self._running = True
            
            logger.info("Initializing Specter browser process pool", min_processes=self.min_processes)
            
            # Start minimum processes
            for _ in range(self.min_processes):
                await self._spawn_process()
                
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def shutdown(self) -> None:
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            
        async with self._lock:
            logger.info("Shutting down process pool")
            for entry in self.entries:
                try:
                    await entry.transport.disconnect()
                    await entry.process.stop()
                except Exception as e:
                    logger.error("Failed to shutdown process entry", error=str(e))
            self.entries.clear()

    async def create_context(self, proxy_config: Optional[dict[str, Any]] = None) -> BrowserContext:
        async with self._lock:
            if not self._running:
                raise RuntimeError("Process pool is not running")

            # 1. Look for a healthy, available process
            selected_entry: Optional[BrowserProcessEntry] = None
            for entry in self.entries:
                if entry.is_healthy and entry.active_contexts < self.max_contexts_per_proc:
                    selected_entry = entry
                    break
            
            # 2. If none found, spawn a new one if under max ceiling
            if not selected_entry:
                if len(self.entries) < self.max_processes:
                    logger.info("All processes busy, spawning a new instance")
                    selected_entry = await self._spawn_process()
                else:
                    # If at ceiling, grab the least busy process
                    logger.warn("Pool ceiling reached. Sharing process contexts.")
                    selected_entry = min(self.entries, key=lambda e: e.active_contexts)

            # 3. Create context in selected process
            logger.info("Creating browser context in selected process", active_contexts=selected_entry.active_contexts)
            
            context_params = {"disposeOnDetach": True}
            if proxy_config:
                context_params["proxyServer"] = proxy_config.get("server")
                if proxy_config.get("bypass"):
                    context_params["proxyBypassList"] = proxy_config["bypass"]
                    
            try:
                response = await selected_entry.transport.send("Target.createBrowserContext", context_params)
                context_id = response["browserContextId"]
                selected_entry.active_contexts += 1
                
                # Create wrapper context
                return BrowserContext(selected_entry.transport, context_id, proxy_config)
            except Exception as e:
                logger.error("Failed to create context in browser process", error=str(e))
                # Mark as unhealthy if it crashed
                selected_entry.is_healthy = False
                raise

    async def release_context(self, context: BrowserContext) -> None:
        await context.close()
        
        async with self._lock:
            # Find the process entry that owns this context's transport
            for entry in self.entries:
                if entry.transport == context.transport:
                    entry.active_contexts = max(0, entry.active_contexts - 1)
                    logger.info("Released browser context", context_id=context.context_id, remaining_contexts=entry.active_contexts)
                    
                    # If process has zero contexts and we are above minimum processes, scale down
                    if entry.active_contexts == 0 and len(self.entries) > self.min_processes:
                        logger.info("Scaling down process pool, removing idle process entry")
                        self.entries.remove(entry)
                        await entry.transport.disconnect()
                        await entry.process.stop()
                    break

    async def _spawn_process(self) -> BrowserProcessEntry:
        proc = ChromeProcess(excision_mode=self.excision_mode)
        await proc.start()
        
        transport = CDPTransport(proc.ws_url)
        await transport.connect()
        
        entry = BrowserProcessEntry(proc, transport)
        self.entries.append(entry)
        return entry

    async def _health_check_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self.health_check_interval)
                
                for entry in list(self.entries):
                    if not entry.is_healthy:
                        # Process already flagged as dead, recycle it
                        await self._recycle_process(entry)
                        continue
                        
                    try:
                        # Ping Chrome
                        await asyncio.wait_for(
                            entry.transport.send("Browser.getVersion", {}),
                            timeout=2.0
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.warn("Process failed health check, recycling", error=str(e))
                        entry.is_healthy = False
                        await self._recycle_process(entry)
                        
        except asyncio.CancelledError:
            pass

    async def _recycle_process(self, entry: BrowserProcessEntry) -> None:
        async with self._lock:
            if entry in self.entries:
                logger.info("Recycling unhealthy browser process")
                self.entries.remove(entry)
                
                # Cleanup connection and kill process
                try:
                    await entry.transport.disconnect()
                    await entry.process.stop()
                except Exception:
                    pass
                    
                # If we fell below min, spawn a replacement
                if len(self.entries) < self.min_processes:
                    try:
                        await self._spawn_process()
                    except Exception as e:
                        logger.error("Failed to spawn replacement process during recycling", error=str(e))
