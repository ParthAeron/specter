import tiktoken
import structlog
from typing import List

logger = structlog.get_logger()

# Use standard cl100k_base encoder (same as GPT-4 / Claude 3)
try:
    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:
    _encoder = tiktoken.get_encoding("gpt2") # Fallback

def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))

def enforce_token_budget_with_stats(axtree_str: str, budget: int = 500) -> tuple[str, dict[str, int]]:
    """
    Enforces a token budget on the accessibility tree, returning the truncated tree and statistics.
    """
    lines = axtree_str.splitlines()
    stats = {
        "original_tokens": 0,
        "original_lines": len(lines),
        "priority_lines_kept": 0,
        "dropped_lines_removed": 0,
        "backfilled_lines_added": 0,
        "hard_truncated_lines": 0,
        "final_tokens": 0,
        "final_lines": 0
    }
    if not lines:
        return "", stats
        
    current_tokens = count_tokens("\n".join(lines))
    stats["original_tokens"] = current_tokens
    
    if current_tokens <= budget:
        stats["final_tokens"] = current_tokens
        stats["final_lines"] = len(lines)
        return axtree_str, stats

    logger.info("AXTree size exceeds budget, compressing", current_tokens=current_tokens, budget=budget)
    
    # Priority roles to preserve
    priority_roles = {
        "button", "link", "textbox", "searchbox", "combobox", "checkbox", 
        "heading", "form", "alert", "dialog", "menuitem", "radio", "tab"
    }
    
    kept_lines: List[str] = []
    dropped_lines: List[str] = []
    
    # First pass: classify lines
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("["):
            # Header lines (URL, Title, etc.) are kept
            kept_lines.append(line)
            continue
            
        parts = stripped.split(" ", 2)
        if len(parts) >= 2:
            role = parts[1].lower()
            if role in priority_roles:
                kept_lines.append(line)
                continue
                
        dropped_lines.append(line)

    stats["priority_lines_kept"] = len(kept_lines)
    stats["dropped_lines_removed"] = len(dropped_lines)
    
    # Reconstruct prioritized tree
    final_text = "\n".join(kept_lines)
    final_tokens = count_tokens(final_text)
    
    # If we are still over budget, truncate lines from the bottom of the kept list
    if final_tokens > budget:
        logger.warn("Prioritized AXTree still exceeds budget, hard-truncating", final_tokens=final_tokens)
        truncated_lines = []
        token_sum = 0
        for line in kept_lines:
            line_tokens = count_tokens(line + "\n")
            if token_sum + line_tokens > budget - 5: # leave buffer for truncation notice
                break
            truncated_lines.append(line)
            token_sum += line_tokens
            
        truncated_lines.append("... [Truncated due to token budget]")
        
        # Calculate how many priority lines were actually truncated
        # We kept len(truncated_lines) - 1 of the original kept_lines
        stats["hard_truncated_lines"] = len(kept_lines) - (len(truncated_lines) - 1)
        
        final_text = "\n".join(truncated_lines)
        stats["final_tokens"] = count_tokens(final_text)
        stats["final_lines"] = len(truncated_lines)
        return final_text, stats
        
    # If we are under budget, we can fill back some of the dropped lines to utilize the remaining budget
    remaining_budget = budget - final_tokens
    if remaining_budget > 20 and dropped_lines:
        logger.info("Prioritized tree under budget, backfilling dropped lines", remaining_budget=remaining_budget)
        backfilled_lines = []
        token_sum = 0
        
        # Sort dropped lines by indentation (prefer shallow elements first)
        dropped_lines.sort(key=lambda l: len(l) - len(l.lstrip()))
        
        for line in dropped_lines:
            line_tokens = count_tokens(line + "\n")
            if token_sum + line_tokens > remaining_budget - 5:
                break
            backfilled_lines.append(line)
            token_sum += line_tokens
            
        stats["backfilled_lines_added"] = len(backfilled_lines)
        stats["dropped_lines_removed"] -= len(backfilled_lines) # they were added back
        
        # Re-interleave lines based on their original order (ref numbers)
        # Sort using reference tags to keep tree structure consistent
        def get_ref_num(l: str) -> int:
            try:
                # l starts with "  [n12] ..." -> extract "12"
                ref_part = l.strip().split(" ", 1)[0]
                return int(ref_part.strip("[]n"))
            except Exception:
                return 999999
                
        all_lines = kept_lines + backfilled_lines
        # Keep header lines at top, rest sorted by ref number
        headers = [l for l in all_lines if not l.strip().startswith("[")]
        body = [l for l in all_lines if l.strip().startswith("[")]
        body.sort(key=get_ref_num)
        
        final_text = "\n".join(headers + body)
        stats["final_tokens"] = count_tokens(final_text)
        stats["final_lines"] = len(headers) + len(body)
        return final_text, stats
        
    stats["final_tokens"] = final_tokens
    stats["final_lines"] = len(kept_lines)
    return final_text, stats

def enforce_token_budget(axtree_str: str, budget: int = 500) -> str:
    """
    Enforces a token budget on the accessibility tree.
    If over budget, prioritizes keeping interactive controls and headings, dropping non-interactive content.
    Truncates the rest if still over budget.
    """
    res, _ = enforce_token_budget_with_stats(axtree_str, budget)
    return res
