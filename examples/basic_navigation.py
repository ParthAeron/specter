import asyncio
import structlog
from specter.browser import ProcessPool
from specter.page import AXTreeParser, RefRegistry
from specter.actions import navigate_page

# Setup pretty console logging
structlog.configure()

async def main():
    # 1. Initialize process pool (min 1, max 2 processes)
    pool = ProcessPool(min_processes=1, max_processes=2, excision_mode=True)
    await pool.start()
    
    try:
        # 2. Create an isolated browser context
        context = await pool.create_context()
        
        # 3. Create a new page/tab session
        session = await context.create_page()
        
        # 4. Navigate to httpbin
        print("Navigating to httpbin.org...")
        result = await navigate_page(session, "https://httpbin.org/html")
        print(f"Status: {result['status']}")
        print(f"Loaded Page: {result['title']} ({result['url']})")
        
        # 5. Extract accessibility representation
        registry = RefRegistry()
        parser = AXTreeParser(registry)
        snapshot, count = await parser.fetch_and_format(session)
        
        print("\n--- Accessibility Tree Snapshot ---")
        print(snapshot)
        print("------------------------------------")
        print(f"Total interactive elements: {count}")
        
        # 6. Release context
        await pool.release_context(context)
        
    finally:
        # 7. Clean up and shut down browser processes
        await pool.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
