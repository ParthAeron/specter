import argparse
import sys
import uvicorn
import structlog
from typing import Optional

logger = structlog.get_logger()

def main():
    parser = argparse.ArgumentParser(description="Specter CLI - High performance headless browser harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # 1. Install command
    subparsers.add_parser("install", help="Download and install chrome-headless-shell binary")
    
    # 2. Serve command
    serve_parser = subparsers.add_parser("serve", help="Start FastAPI HTTP and WebSocket server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to run server on")
    serve_parser.add_argument("--reload", action="store_true", help="Enable code hot-reloading")
    
    # 3. Search command
    search_parser = subparsers.add_parser("search", help="Perform a stealthy web search (Google, DuckDuckGo, Bing, Yahoo, etc.) and print result links")
    search_parser.add_argument("query", help="The search query string")
    search_parser.add_argument("--engine", default="google", help="The search engine name or URL to use (default: google)")
    search_parser.add_argument("--rgx", action="store_true", help="Enable RGX mode for collapsing sibling links")
    search_parser.add_argument("--excision", action="store_true", help="Enable Excision Mode to disable graphics/audio subsystems")
    search_parser.add_argument("--solve-captcha", action="store_true", help="Automatically detect and solve CAPTCHAs")
    search_parser.add_argument("--proxy", help="Proxy URI configuration (e.g. socks5://user:pass@host:port)")
    search_parser.add_argument("--wait-until", default="networkIdle", choices=["init", "DOMContentLoaded", "load", "networkAlmostIdle", "networkIdle"], help="Navigation wait condition")
    
    # 4. Info command
    info_parser = subparsers.add_parser("info", help="Navigate to a URL and print page information, AXTree snapshot, and performance metrics")
    info_parser.add_argument("url", help="The target web page URL")
    info_parser.add_argument("--rgx", action="store_true", help="Enable RGX mode for collapsing sibling links")
    info_parser.add_argument("--json", action="store_true", help="Print information as raw JSON")
    info_parser.add_argument("--readability", action="store_true", help="Extract and print clean readability prose instead of AXTree snapshot")
    info_parser.add_argument("--text", action="store_true", help="Extract and print raw body text instead of AXTree snapshot")
    info_parser.add_argument("--excision", action="store_true", help="Enable Excision Mode to disable graphics/audio subsystems")
    info_parser.add_argument("--solve-captcha", action="store_true", help="Automatically detect and solve CAPTCHAs")
    info_parser.add_argument("--proxy", help="Proxy URI configuration (e.g. socks5://user:pass@host:port)")
    info_parser.add_argument("--wait-until", default="networkIdle", choices=["init", "DOMContentLoaded", "load", "networkAlmostIdle", "networkIdle"], help="Navigation wait condition")
    info_parser.add_argument("--screenshot", help="Capture screenshot of the page and save to specified file path")
    
    args = parser.parse_args()
    
    if args.command == "install":
        print("Running installer...")
        from specter.install.installer import download_and_install
        try:
            bin_path = download_and_install()
            print(f"\nSuccess! chrome-headless-shell installed at: {bin_path}")
        except Exception as e:
            print(f"\nInstallation failed: {e}", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "serve":
        logger.info("Starting Specter server", host=args.host, port=args.port)
        uvicorn.run("specter.api:app", host=args.host, port=args.port, reload=args.reload)
        
    elif args.command == "search":
        import asyncio
        from specter.browser import ProcessPool
        from specter.page import RefRegistry, AXTreeParser
        from specter.actions import navigate_page, fill_input
        from specter.stealth import inject_stealth, apply_stealth_headers
        
        async def run_search(query: str, engine: str, rgx_mode: bool, excision_mode: bool, solve_captcha: bool, proxy: Optional[str], wait_until: str):
            print(f"Initializing Specter engine for query: '{query}' using {engine}...")
            pool = ProcessPool(min_processes=1, max_processes=1, excision_mode=excision_mode)
            await pool.start()
            try:
                from specter.evasion import parse_proxy_string, detect_captcha, solve_captcha_pipeline, CapSolver, TwoCaptcha
                import os
                
                proxy_config = parse_proxy_string(proxy)
                context = await pool.create_context(proxy_config)
                session = await context.create_page()
                
                # Apply stealth
                await inject_stealth(session)
                await apply_stealth_headers(session)
                
                # Setup URL and cookie configurations
                engine_lower = engine.lower().strip()
                shortcuts = {
                    "google": "https://www.google.com/ncr",
                    "duckduckgo": "https://duckduckgo.com",
                    "ddg": "https://duckduckgo.com",
                    "bing": "https://www.bing.com",
                    "yahoo": "https://search.yahoo.com",
                    "baidu": "https://www.baidu.com",
                    "yandex": "https://yandex.com",
                }
                
                if engine_lower in shortcuts:
                    start_url = shortcuts[engine_lower]
                elif engine_lower.startswith(("http://", "https://")):
                    start_url = engine
                else:
                    start_url = f"https://www.{engine_lower}.com"
                
                if "google.com" in start_url:
                    # Set Google consent cookie
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
                
                # Navigate
                await navigate_page(session, start_url, wait_until=wait_until)
                
                if solve_captcha:
                    captcha_info = await detect_captcha(session)
                    if captcha_info:
                        print(f"Detected CAPTCHA on homepage: {captcha_info['type']}. Attempting to solve...")
                        solver = None
                        if os.environ.get("CAPSOLVER_API_KEY"):
                            solver = CapSolver(os.environ["CAPSOLVER_API_KEY"])
                        elif os.environ.get("TWOCAPTCHA_API_KEY"):
                            solver = TwoCaptcha(os.environ["TWOCAPTCHA_API_KEY"])
                        
                        if solver:
                            if await solve_captcha_pipeline(session, captcha_info, solver):
                                print("CAPTCHA successfully solved!")
                            else:
                                print("CAPTCHA solving failed.")
                        else:
                            print("CAPTCHA detected but no solver API key found in environment.")
                
                # Retrieve search box
                registry = RefRegistry()
                parser = AXTreeParser(registry)
                snapshot, _ = await parser.fetch_and_format(session, rgx_mode=rgx_mode)
                
                search_ref = None
                for line in snapshot.splitlines():
                    if "textbox" in line or "searchbox" in line:
                        search_ref = line.strip().split(" ", 1)[0].strip("[]")
                        break
                
                if not search_ref:
                    # Fallback DOM query matching common search input names and IDs across different engines
                    doc_resp = await session.send("DOM.getDocument", {})
                    node_resp = await session.send("DOM.querySelector", {
                        "nodeId": doc_resp["root"]["nodeId"],
                        "selector": "textarea[name='q'], input[name='q'], input[name='p'], input[name='wd'], input[name='text'], textarea[type='search'], input[type='search'], input[id='search_form_input_homepage'], input[id='sb_form_q']"
                    })
                    node_id = node_resp.get("nodeId")
                    if node_id:
                        info_resp = await session.send("DOM.describeNode", {"nodeId": node_id})
                        search_ref = registry.register(info_resp["node"]["backendNodeId"])
                
                if not search_ref:
                    print(f"Error: Could not locate search box on {start_url}.")
                    return
                
                # Input query
                await fill_input(session, registry, search_ref, query)
                
                # Press Enter
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
                
                # Wait for search results
                print("Waiting for results...")
                await asyncio.sleep(4.0)
                
                if solve_captcha:
                    captcha_info = await detect_captcha(session)
                    if captcha_info:
                        print(f"Detected CAPTCHA on Search Results: {captcha_info['type']}. Attempting to solve...")
                        solver = None
                        if os.environ.get("CAPSOLVER_API_KEY"):
                            solver = CapSolver(os.environ["CAPSOLVER_API_KEY"])
                        elif os.environ.get("TWOCAPTCHA_API_KEY"):
                            solver = TwoCaptcha(os.environ["TWOCAPTCHA_API_KEY"])
                        
                        if solver:
                            if await solve_captcha_pipeline(session, captcha_info, solver):
                                print("CAPTCHA successfully solved!")
                                await asyncio.sleep(3.0)
                            else:
                                print("CAPTCHA solving failed.")
                        else:
                            print("CAPTCHA detected but no solver API key found in environment.")
                
                # Parse results
                snapshot, _ = await parser.fetch_and_format(session, rgx_mode=rgx_mode)
                print(f"\n--- Search Results links ({engine}) ---")
                
                from urllib.parse import urlparse
                parsed = urlparse(start_url)
                domain_parts = parsed.netloc.split('.')
                if len(domain_parts) >= 2:
                    brand_name = domain_parts[-2]
                else:
                    brand_name = engine_lower
                
                excludes = (brand_name, "search", "sign in", "web results", "about", "feedback", "settings", "help", "privacy", "terms")
                
                for line in snapshot.splitlines():
                    if "link" in line and not any(k in line.lower() for k in excludes):
                        print(line.strip())
                        
                await pool.release_context(context)
            finally:
                await pool.shutdown()
                
        asyncio.run(run_search(args.query, args.engine, args.rgx, args.excision, args.solve_captcha, args.proxy, args.wait_until))

    elif args.command == "info":
        import asyncio
        import time
        import json
        from specter.browser import ProcessPool
        from specter.page import RefRegistry, AXTreeParser, extract_readable_content
        from specter.actions import navigate_page, take_screenshot
        from specter.stealth import inject_stealth, apply_stealth_headers
        from specter.observability.metrics import fetch_performance_metrics
        
        async def run_info(url: str, rgx_mode: bool, json_output: bool, readability_mode: bool, text_mode: bool, excision_mode: bool, solve_captcha: bool, proxy: Optional[str], wait_until: str, screenshot_path: Optional[str]):
            if not json_output:
                print(f"Navigating to: '{url}'...")
            
            pool = ProcessPool(min_processes=1, max_processes=1, excision_mode=excision_mode)
            await pool.start()
            try:
                from specter.evasion import parse_proxy_string, detect_captcha, solve_captcha_pipeline, CapSolver, TwoCaptcha
                import os
                
                proxy_config = parse_proxy_string(proxy)
                context = await pool.create_context(proxy_config)
                session = await context.create_page()
                
                # Apply stealth
                await inject_stealth(session)
                await apply_stealth_headers(session)
                
                # Navigate
                t0 = time.perf_counter()
                action_result = await navigate_page(session, url, wait_until=wait_until)
                nav_speed = round((time.perf_counter() - t0) * 1000, 2)
                
                if solve_captcha:
                    captcha_info = await detect_captcha(session)
                    if captcha_info:
                        if not json_output:
                            print(f"Detected CAPTCHA: {captcha_info['type']}. Attempting to solve...")
                        solver = None
                        if os.environ.get("CAPSOLVER_API_KEY"):
                            solver = CapSolver(os.environ["CAPSOLVER_API_KEY"])
                        elif os.environ.get("TWOCAPTCHA_API_KEY"):
                            solver = TwoCaptcha(os.environ["TWOCAPTCHA_API_KEY"])
                        
                        if solver:
                            if await solve_captcha_pipeline(session, captcha_info, solver):
                                if not json_output:
                                    print("CAPTCHA successfully solved!")
                                await asyncio.sleep(2.0)
                            else:
                                if not json_output:
                                    print("CAPTCHA solving failed.")
                        else:
                            if not json_output:
                                print("CAPTCHA detected but no solver API key found in environment.")
                
                # Capture screenshot if requested
                if screenshot_path:
                    if not json_output:
                        print(f"Capturing page screenshot to: '{screenshot_path}'...")
                    await take_screenshot(session, file_path=screenshot_path)
                
                perf_metrics = await fetch_performance_metrics(session)
                
                eval_meta = await session.send("Runtime.evaluate", {
                    "expression": "({ url: window.location.href, title: document.title })",
                    "returnByValue": True
                })
                meta = eval_meta.get("result", {}).get("value", {"url": "", "title": ""})
                
                if readability_mode:
                    article = await extract_readable_content(session)
                    info_data = {
                        "title": article.get("title", ""),
                        "byline": article.get("byline", ""),
                        "excerpt": article.get("excerpt", ""),
                        "content": article.get("content", ""),
                        "metrics": {
                            "navigation_speed_ms": nav_speed,
                            "js_heap_used_bytes": perf_metrics.get("JSHeapUsedSize", 0),
                            "dom_nodes": perf_metrics.get("DOMNodes", 0),
                        }
                    }
                    if json_output:
                        print(json.dumps(info_data, indent=2))
                    else:
                        print("\n" + "="*50)
                        print("READABLE ARTICLE PROSE")
                        print("="*50)
                        print(f"Title:   {info_data['title']}")
                        print(f"Author:  {info_data['byline']}")
                        print(f"Excerpt: {info_data['excerpt']}")
                        print("-"*50)
                        print(info_data['content'])
                        print("="*50 + "\n")
                elif text_mode:
                    from specter.actions import get_page_text
                    action_result = await get_page_text(session, mode="raw")
                    raw_text = action_result.get("text", "") if action_result["status"] == "ok" else ""
                    info_data = {
                        "title": meta.get("title", ""),
                        "url": meta.get("url", ""),
                        "text": raw_text,
                        "metrics": {
                            "navigation_speed_ms": nav_speed,
                            "js_heap_used_bytes": perf_metrics.get("JSHeapUsedSize", 0),
                            "dom_nodes": perf_metrics.get("DOMNodes", 0),
                        }
                    }
                    if json_output:
                        print(json.dumps(info_data, indent=2))
                    else:
                        print("\n" + "="*50)
                        print("RAW BODY TEXT CONTENT")
                        print("="*50)
                        print(f"Title:   {info_data['title']}")
                        print(f"URL:     {info_data['url']}")
                        print("-"*50)
                        print(info_data['text'])
                        print("="*50 + "\n")
                else:
                    # Retrieve AXTree info
                    registry = RefRegistry()
                    parser = AXTreeParser(registry)
                    
                    t0 = time.perf_counter()
                    snapshot, count = await parser.fetch_and_format(session, rgx_mode=rgx_mode)
                    v8_parse_time = round((time.perf_counter() - t0) * 1000, 2)
                    
                    info_data = {
                        "title": meta.get("title", ""),
                        "url": meta.get("url", ""),
                        "metrics": {
                            "navigation_speed_ms": nav_speed,
                            "v8_dom_parsing_and_structuring_ms": v8_parse_time,
                            "js_heap_used_bytes": perf_metrics.get("JSHeapUsedSize", 0),
                            "dom_nodes": perf_metrics.get("DOMNodes", 0),
                            "interactive_elements": count,
                            "rgx_collapsed_elements": getattr(parser, "last_collapsed_count", 0)
                        },
                        "snapshot": snapshot
                    }
                    
                    if json_output:
                        print(json.dumps(info_data, indent=2))
                    else:
                        print("\n" + "="*50)
                        print("PAGE INFORMATION")
                        print("="*50)
                        print(f"Title:        {info_data['title']}")
                        print(f"URL:          {info_data['url']}")
                        print("-"*50)
                        print("PERFORMANCE TELEMETRY")
                        print("-"*50)
                        print(f"Navigation Speed:             {info_data['metrics']['navigation_speed_ms']} ms")
                        print(f"V8 DOM Parsing & Structuring: {info_data['metrics']['v8_dom_parsing_and_structuring_ms']} ms")
                        print(f"JS Heap Memory Footprint:     {info_data['metrics']['js_heap_used_bytes'] / (1024*1024):.2f} MB")
                        print(f"Total DOM Nodes in Page:      {info_data['metrics']['dom_nodes']}")
                        print(f"Interactive Elements Found:   {info_data['metrics']['interactive_elements']}")
                        print(f"RGX Sibling Nodes Collapsed:  {info_data['metrics']['rgx_collapsed_elements']}")
                        print("-"*50)
                        print("SEMANTIC AXTREE SNAPSHOT")
                        print("-"*50)
                        print(snapshot)
                        print("="*50 + "\n")
                    
                await pool.release_context(context)
            finally:
                await pool.shutdown()
                
        asyncio.run(run_info(args.url, args.rgx, args.json, args.readability, args.text, args.excision, args.solve_captcha, args.proxy, args.wait_until, args.screenshot))

if __name__ == "__main__":
    main()
