import asyncio
import structlog
from specter.browser import ProcessPool
from specter.page import AXTreeParser, RefRegistry
from specter.actions import navigate_page, fill_input, click_element
from specter.stealth import inject_stealth, apply_stealth_headers

# Setup pretty logging
structlog.configure()

async def main():
    pool = ProcessPool(min_processes=1, max_processes=2, excision_mode=True)
    await pool.start()
    
    try:
        context = await pool.create_context()
        session = await context.create_page()
        
        # Apply stealth patches and headers to bypass detection
        print("Injecting stealth overrides...")
        await inject_stealth(session)
        await apply_stealth_headers(session)
        
        # 1. Pre-inject SOCS cookie to bypass Google consent pages
        print("Injecting Google consent preference cookie...")
        await session.send("Network.enable", {})
        await session.send("Network.setCookies", {
            "cookies": [{
                "name": "SOCS",
                "value": "CAESHAgBEhJnd3NfMjAyNDA2MDMtMF9SQzIaAnVzIAEaBgiA4Ne0Bg",
                "domain": ".google.com",
                "path": "/",
                "secure": True,
                "httpOnly": False
            }]
        })
        
        # 2. Load Google Home Page (NCR: No Country Redirect ensures cookie matches .google.com)
        print("Navigating to google.com...")
        await navigate_page(session, "https://www.google.com/ncr")
        
        # 3. Fetch AXTree to locate the search box
        registry = RefRegistry()
        parser = AXTreeParser(registry)
        snapshot, _ = await parser.fetch_and_format(session)
        
        search_ref = None
        for line in snapshot.splitlines():
            if "textbox" in line or "searchbox" in line:
                search_ref = line.strip().split(" ", 1)[0].strip("[]")
                break
                
        if not search_ref:
            # Fallback using standard selector resolution
            doc_resp = await session.send("DOM.getDocument", {})
            node_resp = await session.send("DOM.querySelector", {
                "nodeId": doc_resp["root"]["nodeId"],
                "selector": "textarea[name='q'], input[name='q']"
            })
            node_id = node_resp.get("nodeId")
            if node_id:
                info_resp = await session.send("DOM.describeNode", {"nodeId": node_id})
                search_ref = registry.register(info_resp["node"]["backendNodeId"])
                
        if not search_ref:
            print("Error: Could not find google search box")
            return
            
        # 4. Fill search query
        print("Entering search query...")
        await fill_input(session, registry, search_ref, "Specter headless browser github")
        
        # 5. Submit query using Enter key
        print("Submitting query...")
        await session.send("Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "key": "Enter",
            "windowsVirtualKeyCode": 13,
            "code": "Enter"
        })
        await session.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": "Enter",
            "windowsVirtualKeyCode": 13,
            "code": "Enter"
        })
        
        # Wait for results page to load
        print("Waiting for search results...")
        await asyncio.sleep(4.0)
        
        # 6. Extract search hits
        snapshot, _ = await parser.fetch_and_format(session)
        print("\n--- Search Results links ---")
        
        links = []
        for line in snapshot.splitlines():
            if "link" in line and not any(k in line.lower() for k in ("search", "google", "sign in", "web results")):
                print(line.strip())
                
        await pool.release_context(context)
        
    finally:
        await pool.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
