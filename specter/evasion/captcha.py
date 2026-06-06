import structlog
from typing import Any, Dict, Optional
from specter.cdp import CDPSession
from specter.evasion.solver import CaptchaSolver, SolveParams

logger = structlog.get_logger()

# Javascript probe to query the DOM for captcha widgets and extract sitekeys
CAPTCHA_PROBE_JS = """
(function() {
    // 1. Detect reCAPTCHA v2
    const recaptchaFrame = document.querySelector('iframe[src*="recaptcha"]');
    if (recaptchaFrame) {
        const src = recaptchaFrame.src;
        const kMatch = src.match(/k=([a-zA-Z0-9_-]+)/);
        if (kMatch) {
            return { type: 'recaptcha_v2', sitekey: kMatch[1], iframe: true };
        }
    }
    const recaptchaContainer = document.querySelector('[data-sitekey]');
    if (recaptchaContainer) {
        const sitekey = recaptchaContainer.getAttribute('data-sitekey');
        return { type: 'recaptcha_v2', sitekey: sitekey, iframe: false };
    }

    // 2. Detect hCaptcha
    const hcaptchaFrame = document.querySelector('iframe[src*="hcaptcha.com"]');
    if (hcaptchaFrame) {
        const src = hcaptchaFrame.src;
        const hostMatch = src.match(/host=([a-zA-Z0-9_.-]+)/);
        // Sometimes hcaptcha puts sitekey in src parameters
        const sitekeyMatch = src.match(/sitekey=([a-f0-9-]+)/);
        if (sitekeyMatch) {
            return { type: 'hcaptcha', sitekey: sitekeyMatch[1] };
        }
    }
    const hcaptchaContainer = document.querySelector('.h-captcha');
    if (hcaptchaContainer) {
        const sitekey = hcaptchaContainer.getAttribute('data-sitekey');
        return { type: 'hcaptcha', sitekey: sitekey };
    }

    // 3. Detect Cloudflare Turnstile
    const turnstileFrame = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
    if (turnstileFrame) {
        // Parse Turnstile sitekey from the frame source
        const src = turnstileFrame.src;
        // The URL format has the sitekey inside the path/query parameters
        const sitekeyMatch = src.match(/\\/h\\/[b|g]\\/([a-zA-Z0-9_-]+)/) || src.match(/sitekey=([a-zA-Z0-9_-]+)/);
        if (sitekeyMatch) {
            return { type: 'cloudflare_turnstile', sitekey: sitekeyMatch[1] };
        }
    }

    // 4. Cloudflare Interstitial
    if (document.title.includes('Just a moment') || document.querySelector('#cf-challenge-running')) {
        return { type: 'cloudflare_interstitial', sitekey: null };
    }

    return null;
})();
"""

async def detect_captcha(session: CDPSession) -> Optional[dict[str, Any]]:
    try:
        response = await session.send("Runtime.evaluate", {
            "expression": CAPTCHA_PROBE_JS,
            "returnByValue": True
        })
        val = response.get("result", {}).get("value")
        if val:
            logger.info("CAPTCHA challenge detected on page", type=val["type"])
            return val
        return None
    except Exception as e:
        logger.error("Failed to execute CAPTCHA detection probe", error=str(e))
        return None

async def solve_captcha_pipeline(session: CDPSession, captcha_info: dict[str, Any], solver: CaptchaSolver) -> bool:
    captcha_type = captcha_info["type"]
    sitekey = captcha_info.get("sitekey")
    
    if captcha_type == "cloudflare_interstitial":
        logger.warn("Cloudflare interstitial (Just a Moment) detected. Automated bypass via clicking is not reliable. Please use residential proxies and session warming.")
        return False
        
    if not sitekey:
        logger.error("No sitekey found for CAPTCHA challenge. Cannot solve.", captcha_type=captcha_type)
        return False

    # Get page URL
    url_resp = await session.send("Runtime.evaluate", {
        "expression": "window.location.href",
        "returnByValue": True
    })
    page_url = url_resp.get("result", {}).get("value", "")
    
    logger.info("Submitting challenge to solver API", type=captcha_type, sitekey=sitekey, url=page_url)
    
    params = SolveParams(sitekey=sitekey, page_url=page_url)
    try:
        result = await solver.solve(captcha_type, params)
        token = result.token
        logger.info("CAPTCHA successfully solved", type=captcha_type, latency_ms=result.latency_ms)
        
        # Inject token into DOM depending on captcha type
        inject_script = ""
        if captcha_type == "recaptcha_v2":
            inject_script = f"""
            (function() {{
                document.getElementById('g-recaptcha-response').value = '{token}';
                // Attempt to call standard callbacks
                const callbacks = [
                    window.recaptchaCallback, 
                    window.onSuccess, 
                    window.submitCallback,
                    ...Object.keys(window).filter(k => k.toLowerCase().includes('recaptcha') && typeof window[k] === 'function').map(k => window[k])
                ];
                for (const cb of callbacks) {{
                    if (typeof cb === 'function') {{
                        try {{ cb('{token}'); }} catch(e) {{}}
                    }}
                }}
            }})();
            """
        elif captcha_type == "hcaptcha":
            inject_script = f"""
            (function() {{
                document.getElementsByName('h-captcha-response')[0].value = '{token}';
                document.getElementsByName('g-recaptcha-response')[0].value = '{token}';
                const callbacks = [
                    window.hcaptchaCallback,
                    window.onSuccess,
                    ...Object.keys(window).filter(k => k.toLowerCase().includes('hcaptcha') && typeof window[k] === 'function').map(k => window[k])
                ];
                for (const cb of callbacks) {{
                    if (typeof cb === 'function') {{
                        try {{ cb('{token}'); }} catch(e) {{}}
                    }}
                }}
            }})();
            """
        elif captcha_type == "cloudflare_turnstile":
            inject_script = f"""
            (function() {{
                document.getElementsByName('cf-turnstile-response')[0].value = '{token}';
                const callbacks = [
                    window.turnstileCallback,
                    ...Object.keys(window).filter(k => k.toLowerCase().includes('turnstile') && typeof window[k] === 'function').map(k => window[k])
                ];
                for (const cb of callbacks) {{
                    if (typeof cb === 'function') {{
                        try {{ cb('{token}'); }} catch(e) {{}}
                    }}
                }}
            }})();
            """
            
        await session.send("Runtime.evaluate", {
            "expression": inject_script,
            "returnByValue": True
        })
        return True
        
    except Exception as e:
        logger.error("CAPTCHA solver integration failed", type=captcha_type, error=str(e))
        return False
