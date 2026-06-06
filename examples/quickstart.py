import asyncio
from specter.browser import ProcessPool
from specter.page import AXTreeParser, RefRegistry
from specter.actions import navigate_page

async def run():
    # Initialize the process pool (Standard Mode is default, toggle excision_mode=True for Excision Mode)
    pool = ProcessPool(min_processes=1, max_processes=2, excision_mode=False)
    await pool.start()
    
    try:
        # Create an isolated context and tab session
        context = await pool.create_context()
        session = await context.create_page()
        
        # Navigate to a target site
        result = await navigate_page(session, "https://httpbin.org/html")
        print(f"Loaded Page: {result['title']}")
        
        # Fetch and format accessibility tree
        registry = RefRegistry()
        parser = AXTreeParser(registry)
        snapshot, count = await parser.fetch_and_format(session)
        
        print("\n--- Semantic Page Snapshot ---")
        print(snapshot)
        
        await pool.release_context(context)
    finally:
        await pool.shutdown()

asyncio.run(run())