import json
import structlog
from pathlib import Path
from specter.cdp import CDPSession

logger = structlog.get_logger()

async def save_storage(session: CDPSession, file_path: str | Path) -> None:
    """
    Extracts localStorage and sessionStorage data and writes them to a JSON file on disk.
    """
    logger.info("Saving web storage to disk", path=str(file_path))
    
    script = """
    (function() {
        return {
            local: { ...localStorage },
            session: { ...sessionStorage }
        };
    })()
    """
    try:
        response = await session.send("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True
        })
        val = response.get("result", {}).get("value", {})
        
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(val, indent=2), encoding="utf-8")
        
        logger.info("Web storage successfully saved", local_keys=len(val.get("local", {})), session_keys=len(val.get("session", {})))
    except Exception as e:
        logger.error("Failed to save web storage", error=str(e))
        raise

async def restore_storage(session: CDPSession, file_path: str | Path) -> None:
    """
    Reads web storage from a JSON file and applies it to the current page.
    Note: The browser must already be navigated to the target domain,
    otherwise standard origin security checks will block writing.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warn("Storage file not found. Skipping restoration.", path=str(file_path))
        return
        
    logger.info("Restoring web storage from disk", path=str(file_path))
    try:
        val = json.loads(path.read_text(encoding="utf-8"))
        local_data = val.get("local", {})
        session_data = val.get("session", {})
        
        # Inject scripts to write items
        # JSON.stringify is used to safely escape data strings in Javascript expressions
        script = f"""
        (function() {{
            const localData = {json.dumps(local_data)};
            const sessionData = {json.dumps(session_data)};
            
            try {{
                for (const [k, v] of Object.entries(localData)) {{
                    localStorage.setItem(k, v);
                }}
                for (const [k, v] of Object.entries(sessionData)) {{
                    sessionStorage.setItem(k, v);
                }}
                return true;
            }} catch (e) {{
                return e.toString();
            }}
        }})()
        """
        
        response = await session.send("Runtime.evaluate", {
            "expression": script,
            "returnByValue": True
        })
        result = response.get("result", {}).get("value")
        if result is not True:
            raise RuntimeError(f"Browser rejected storage injection: {result}")
            
        logger.info("Web storage successfully restored", local_keys=len(local_data), session_keys=len(session_data))
    except Exception as e:
        logger.error("Failed to restore web storage", error=str(e))
        raise
