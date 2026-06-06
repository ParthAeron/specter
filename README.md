<p align="center">
  <img src="./assets/specter_mascot.png" alt="Specter Logo" width="105" />
</p>
<h1 align="center">Specter</h1>
<p align="center">
  <strong>The ultra-lightweight, high-performance headless browser harness built for AI agents and automation.</strong><br>
  Direct Chrome DevTools Protocol (CDP) engine. Zero-bloat flat session multiplexing. Stealth built-in.
</p>

<p align="center">
  <img src="./assets/execution_time.svg" alt="Execution Time Chart" width="340" />
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="./assets/memory_usage.svg" alt="Memory Usage Chart" width="340" />
</p>

---

## Performance Benchmarks

Below is the empirical benchmark matrix measured on a developer machine comparing our different modes against standard headless execution environments:

| Operation / Metric | Standard Mode (Default) | Excision Mode (`--excision`) | RGX Mode (`--rgx`) | Description |
| :--- | :---: | :---: | :---: | :--- |
| **Cold Start Latency** | 1621.01 ms | — | — | Initial browser process boot-up & pool warming of 2 idle tabs (done once). |
| **Warm Context Acquisition** | 0.02 ms | 0.02 ms | — | Checking out an isolated, sandboxed browser context from the pool. |
| **Navigation & Load Speed** | 225.40 ms | **87.01 ms** | — | Timing to load page layouts and stabilize document resources. |
| **V8 DOM Parsing & AXTree** | 62.15 ms | **29.53 ms** | — | V8-side tree construction and structured markdown representation. |
| **Tab Recycling & State Reset**| 26.20 ms | 26.20 ms | — | Wiping cookies, storage, cache, and history to recycle tab state. |
| **Token Reduction Rate** | 0.0% | — | **77.39% - 95%** | Context savings on structured lists by collapsing duplicate siblings. |
| **V8 JS Heap Memory** | 4.25 MB | **0.37 MB** | — | Memory footprint of the active JS runtime heap (91.3% RAM reduction). |
| **OS RSS Process Memory** | ~180 MB | **~42 MB** | — | Resident memory used by Chrome processes on the system level. |
| **CreepJS Trust Score** | 100% | 100% | — | Fingerprint verification trust rating (no bot anomalies detected). |
| **Sannysoft Verification** | Passed | Passed | — | Automated bot detection checklists (all green). |

---

## Features

- **🚀 Direct CDP Engine**: Multi-target flat session multiplexing over a single persistent WebSocket. No extra layers or Node.js process hops.
- **✂️ Excision Mode**: Replicates a minimalist philosophy inside Chrome Headless Shell. Toggle off images, audio, WebGL, notifications, and speech synthesis to slash RAM usage and speed up page loads.
- **🌀 RGX Mode**: Sibling container collapsing inspired by `rgx`. Collapses consecutive sibling elements of the same role exceeding a threshold of 5 (e.g., repetitive links or menus) into sample lists with exact truncation counts to conserve LLM context.
- **🕵️ CreepJS-Proof Stealth**: Native function `toString()` masking, deterministic session-seeded canvas/audio noise, spoofed Navigator properties, and dynamic browser-native `Sec-Fetch-*` metadata header management (ensuring stylesheets, scripts, and layouts load correctly without violating security policies or triggering anti-bot flags).
- **🔒 Network Leak Protections**: Prevents WebRTC local IP disclosures and configures remote DNS resolution to block DNS leaks behind proxies.
- **🌐 Playwright-Style Proxy Auth**: Configure proxies at context creation with dynamic authentication challenge handling via `Fetch.continueWithAuth`.
- **🧩 Integrated CAPTCHA Solving**: Pluggable adapters for solvers (CapSolver/2Captcha) with a simple `solve_captcha` toggle.
- **🛡️ Rate Limit Resilience**: Automatically detects HTTP `429` / `403` blocks, recycles browser contexts, rotates proxy IPs, and re-submits navigations transparently.
- **🤖 LLM-Native AXTree Engine**: Fetches accessibility trees, filters out non-semantic nodes, and compiles structured page snapshots with token budgeting (via `tiktoken`).
- **🖱️ Humanized Actions**: Click coordinates translation for subframes, Bezier curve cursor path generation, and log-normal reaction distributions.
- **📺 Developer Live Screencast**: Streams real-time browser frames (`Page.startScreencast`) over WebSockets to a built-in debugging web viewer.

---

## Project Structure

```
specter/
├── pyproject.toml               # Package configuration
├── README.md                    # Project documentation
├── scripts/
│   ├── stealth/
│   │   └── patches.js           # Master fingerprint overrides (loaded at runtime)
│   └── readability/
│       └── readability.min.js   # Mozilla Readability parser (downloaded on demand)
├── specter/
│   ├── install/
│   │   └── installer.py         # Binary auto-downloader
│   ├── cdp/                     # CDP WebSocket client & session wrappers
│   ├── browser/                 # Browser process lifecycle & pool management
│   ├── page/                    # AXTree parsing, diffing & Readability
│   ├── actions/                 # click, fill, scroll, extract, wait_for
│   ├── stealth/                 # Humanization, overrides, and injections
│   ├── evasion/                 # CAPTCHA, proxy, and request interceptors
│   ├── state/                   # Cookie/storage persistence and ring memory
│   ├── api/                     # FastAPI HTTP & WebSocket server
│   └── observability/           # telemetries, tracers, and error captures
└── examples/                    # Quickstart scripts
```

---

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/ParthAeron/specter.git
   cd specter
   ```

2. **Install the package and dependencies**:
   ```bash
   pip install -e .
   ```

3. **Install the Chrome Headless Shell binary**:
   Specter provides a built-in utility to download the correct platform-specific stable build of `chrome-headless-shell` from Google's Chrome for Testing endpoints:
   ```bash
   python -m specter install
   ```

---

## Quickstart

### 1. Library Usage

Here is a basic example of checking out a context, loading a page, and extracting the accessibility representation:

```python
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
```

### 2. Run as a Web Service

You can run Specter as a self-contained REST API server:

```bash
python -m specter serve --port 8000
```

#### API Endpoints:
- `POST /sessions`: Creates an isolated browser context, returning a `session_id`. (Defaults to standard mode; set `excision_mode: true` for advanced excision)
- `DELETE /sessions/{id}`: Disposes of the context and closes session streams.
- `POST /sessions/{id}/action`: Executes a page action (`navigate`, `click`, `fill`, `scroll`, `extract`, `text`, `wait_for`, `snapshot`, `screenshot`), returning the updated AXTree snapshot, incremental DOM diff, performance metrics, CAPTCHA status, and custom output data payload.
- `GET /sessions/{id}/screenshot`: Captures a live screenshot and returns it as a binary `image/png` response.
- `GET /sessions/{id}/cookies`: Fetches all active cookies currently set in the session context.
- `POST /sessions/{id}/cookies`: Injects or updates cookies in the session context.
- `GET /debug/{session_id}`: Launches the built-in HTML live-view debugger. Go to this URL in your browser to watch the agent interact in real-time.

### Step-by-Step API Walkthrough

Follow this guide to run and test Specter as an API service:

#### 1. Start the API Server
Run the FastAPI server locally:
```bash
python -m specter serve --port 8000
```

#### 2. Create a Session
Initialize a new browser context session:

**PowerShell**:
```powershell
$session = Invoke-RestMethod -Uri "http://127.0.0.1:8000/sessions" -Method Post -ContentType "application/json" -Body '{"excision_mode": false, "solve_captcha": true}'
$session_id = $session.session_id
$session_id
```

**Command Prompt / Windows Bash**:
```bash
curl.exe -X POST http://127.0.0.1:8000/sessions -H "Content-Type: application/json" -d "{\"excision_mode\": false, \"solve_captcha\": true}"
```

#### 3. Navigate to a URL
Instruct the browser session to navigate to a target web page (e.g. `https://example.com`):

**PowerShell**:
```powershell
$response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/sessions/$session_id/action" -Method Post -ContentType "application/json" -Body '{"action": "navigate", "params": {"url": "https://example.com"}}'
$response.snapshot
```

**Command Prompt / Windows Bash**:
```bash
curl.exe -X POST http://127.0.0.1:8000/sessions/YOUR_SESSION_UUID/action -H "Content-Type: application/json" -d "{\"action\": \"navigate\", \"params\": {\"url\": \"https://example.com\"}}"
```

#### 4. Extract Text Content
Extract the raw text content of the visited page:

**PowerShell**:
```powershell
$text_resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/sessions/$session_id/action" -Method Post -ContentType "application/json" -Body '{"action": "text", "params": {"mode": "raw"}}'
$text_resp.data.text
```

**Command Prompt / Windows Bash**:
```bash
curl.exe -X POST http://127.0.0.1:8000/sessions/YOUR_SESSION_UUID/action -H "Content-Type: application/json" -d "{\"action\": \"text\", \"params\": {\"mode\": \"raw\"}}"
```

#### 5. Capture a Screenshot
Download the live screen image of the page:

**PowerShell**:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/sessions/$session_id/screenshot" -OutFile "page.png"
```

**Command Prompt / Windows Bash**:
```bash
curl.exe http://127.0.0.1:8000/sessions/YOUR_SESSION_UUID/screenshot --output page.png
```

#### 6. Close the Session
Release the browser context and clean up resources:

**PowerShell**:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/sessions/$session_id" -Method Delete
```

**Command Prompt / Windows Bash**:
```bash
curl.exe -X DELETE http://127.0.0.1:8000/sessions/YOUR_SESSION_UUID
```

## Verified Capabilities

Specter's core engines are verified across the following capabilities:

1. **Navigation and Metadata Resolution**: Confirms CDP-level navigation and metadata parsing.
2. **AXTree Link Harvesting**: Asserts accessibility tree parsing and formatting correctness.
3. **Bezier Mouse-Path Actions**: Humanized clicks routed accurately to elements.
4. **Log-Normal Typing**: Jittered character inputs simulating manual form submissions.
5. **Mozilla Readability**: Cleans raw article layouts into readable markdown prose.
6. **RGX Mode Sibling Collapsing**: Collapses redundant sibling elements to conserve token budget.
7. **Stealth & Bot Evasion**: Evades Google Search and anti-bot fingerprints (CreepJS and Sannysoft verification).
8. **Network Protection**: WebRTC IP disclosure prevention and remote DNS resolution.

---

## End-to-End Search Testing

Specter provides a built-in search tool to test navigation, cookie injection, stealth, typing, and AXTree parsing. Follow this step-by-step walkthrough to run a manual search test:

### Step 1: Open Terminal & Activate Environment
Open your VS Code terminal (or standard powershell terminal) and navigate to the project directory, then activate the local virtual environment:
```powershell
.venv\Scripts\activate.ps1
```

### Step 2: Run a Search
Execute the CLI search command with a query of your choice (e.g., `"headless browser"`). The `--engine` parameter is completely open-ended and accepts recognized shortcut names (Google, DuckDuckGo, Bing), custom site domains (Yahoo, Yandex, etc.), or direct full URLs:
```powershell
# Search using Google (default shortcut)
specter search "headless browser" --engine google

# Search using DuckDuckGo (shortcut)
specter search "headless browser" --engine duckduckgo

# Search using Yahoo (custom site name, maps to search.yahoo.com)
specter search "headless browser" --engine yahoo

# Search using Yandex (custom site name, maps to yandex.com)
specter search "headless browser" --engine yandex

# Search using a direct URL (starts with http/https)
specter search "headless browser" --engine https://duckduckgo.com
```
You will see the step-by-step engine status prints in your console, followed by a list of search result links harvested directly from the selected search engine:
```
Initializing Specter engine for query: 'headless browser' using duckduckgo...
Waiting for results...

--- Search Results links (duckduckgo) ---
[n21] link  "samuelgilman/specter: node.js wrapper..."
...
```

### Step 3: Run a Search in RGX Mode
To test sibling collapsing and token reduction, run a search query with the `--rgx` flag:
```powershell
specter search "headless browser" --rgx
```
Compare the output and observe that repetitive sibling container elements (e.g., menus or result items) exceeding the threshold of 5 consecutive items are collapsed into a single concise count placeholder:
```
... 5 elements of role 'link' collapsed (RGX Mode)
```

### Step 4: Run the Example Script (Alternative)
You can also run our pre-configured example agent script:
```powershell
python examples/google_search_agent.py
```

---

## Page Inspection CLI Command

Specter also provides an `info` subcommand to quickly fetch metadata, access performance telemetry, and get a semantic AXTree snapshot of *any* target URL.

*Note: By default, subcommands use Standard Mode. Advanced features can be toggled using command-line flags.*

- **Standard Info Inspection**:
  ```powershell
  specter info "https://news.ycombinator.com"
  ```

- **Extract clean readability prose**:
  ```powershell
  specter info "https://news.ycombinator.com" --readability
  ```

- **Extract raw text content**:
  ```powershell
  specter info "https://news.ycombinator.com" --text
  ```

- **Enable Excision Mode** (disables images, audio, WebGL):
  ```powershell
  specter info "https://news.ycombinator.com" --excision
  ```

- **Info Inspection in RGX Mode**:
  ```powershell
  specter info "https://news.ycombinator.com" --rgx
  ```

- **Save a Screenshot during Inspection**:
  ```powershell
  specter info "https://news.ycombinator.com" --screenshot ycombinator.png
  ```

- **Pass a residential proxy**:
  ```powershell
  specter info "https://news.ycombinator.com" --proxy "socks5://user:pass@host:port"
  ```

- **Solve CAPTCHAs automatically**:
  ```powershell
  specter info "https://google.com" --solve-captcha
  ```

- **Output as structured JSON**:
  ```powershell
  specter info "https://news.ycombinator.com" --json
  ```

---

## License

MIT License.
