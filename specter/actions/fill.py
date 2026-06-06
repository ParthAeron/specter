import asyncio
import random
import structlog
from typing import Any
from specter.cdp import CDPSession
from specter.page.refs import RefRegistry

logger = structlog.get_logger()

# Map of close keys to simulate typing mistakes (adjacent keys on QWERTY keyboard)
TYPO_MAP = {
    'a': 'qwsz', 'b': 'vghn', 'c': 'xdfv', 'd': 'ersfxc', 'e': 'wsdr',
    'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yujnbg', 'i': 'ujko', 'j': 'uikmnh',
    'k': 'ijlm', 'l': 'okp', 'm': 'njk', 'n': 'bhjm', 'o': 'iklp',
    'p': 'ol', 'q': 'wa', 'r': 'edft', 's': 'wedxza', 't': 'rfgy',
    'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu',
    'z': 'asx'
}

async def type_character(session: CDPSession, char: str) -> None:
    # Send KeyDown for character
    await session.send("Input.dispatchKeyEvent", {
        "type": "keyDown",
        "text": char,
        "unmodifiedText": char,
        "key": char
    })
    # Slight press duration
    await asyncio.sleep(random.uniform(0.01, 0.03))
    # Send KeyUp
    await session.send("Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": char
    })

async def type_backspace(session: CDPSession) -> None:
    await session.send("Input.dispatchKeyEvent", {
        "type": "keyDown",
        "key": "Backspace",
        "windowsVirtualKeyCode": 8,
        "code": "Backspace"
    })
    await asyncio.sleep(random.uniform(0.01, 0.03))
    await session.send("Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": "Backspace",
        "windowsVirtualKeyCode": 8,
        "code": "Backspace"
    })

async def fill_input(
    session: CDPSession,
    ref_registry: RefRegistry,
    ref: str,
    text: str,
    simulate_typos: bool = True,
    timeout: float = 10.0
) -> dict[str, Any]:
    """
    Focuses the target element, clears its value, and types the text character-by-character
    with randomized human-like typing speeds and simulated errors.
    """
    logger.info("Filling input field", ref=ref, text_len=len(text))
    
    try:
        # 1. Resolve short ref to active nodeId
        node_id = await ref_registry.resolve_to_node_id(session, ref)
        
        # 2. Focus the element
        await session.send("DOM.focus", {
            "nodeId": node_id
        }, timeout=timeout)
        
        # 3. Clear existing text via Runtime.evaluate (avoiding keyboard selection bugs)
        await session.send("Runtime.evaluate", {
            "expression": "document.activeElement.value = ''; document.activeElement.dispatchEvent(new Event('input', { bubbles: true }));",
            "returnByValue": True
        })
        
        # 4. Type character by character with delays and typo simulation
        for i, char in enumerate(text):
            # Check typo chance (2% probability, only on letters, not the last char, and if typing is sufficiently long)
            if simulate_typos and char.lower() in TYPO_MAP and len(text) > 3 and i < len(text) - 1 and random.random() < 0.02:
                typo_char = random.choice(TYPO_MAP[char.lower()])
                logger.debug("Simulating typing mistake", expected=char, typed=typo_char)
                
                # Type wrong character
                await type_character(session, typo_char)
                await asyncio.sleep(random.uniform(0.1, 0.25))
                
                # Type backspace to correct
                await type_backspace(session)
                await asyncio.sleep(random.uniform(0.15, 0.3))
                
            # Type correct character
            await type_character(session, char)
            
            # Normal keyboard speed delay (50ms to 120ms)
            await asyncio.sleep(random.uniform(0.05, 0.12))
            
            # Pause slightly longer after punctuation (150ms to 300ms)
            if char in ".,!?":
                await asyncio.sleep(random.uniform(0.15, 0.3))
                
        # 5. Verify the input value
        verify_resp = await session.send("Runtime.evaluate", {
            "expression": "document.activeElement.value",
            "returnByValue": True
        })
        actual_val = verify_resp.get("result", {}).get("value", "")
        
        confirmed = actual_val == text
        if not confirmed:
            logger.warn("Input value mismatch after typing", expected=text, actual=actual_val)
            
        logger.info("Finished filling input", ref=ref, confirmed=confirmed)
        return {
            "status": "ok",
            "ref": ref,
            "confirmed": confirmed
        }
        
    except Exception as e:
        logger.error("Fill action failed", ref=ref, error=str(e))
        return {
            "status": "error",
            "error_type": "fill_failed",
            "error_detail": str(e)
        }
