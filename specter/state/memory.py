from collections import deque
from typing import Any, Dict, List

class AgentMemory:
    def __init__(self, max_turns: int = 5):
        self.turns = deque(maxlen=max_turns)

    def add_turn(self, action: str, params: Dict[str, Any], status: str, error_detail: str | None = None, nodes_diff: dict[str, Any] | None = None) -> None:
        """
        Appends a turn representation to the short-term memory ring buffer.
        """
        turn = {
            "action": action,
            "params": params,
            "status": status
        }
        if error_detail:
            turn["error"] = error_detail
            
        if nodes_diff:
            # Keep counts instead of full nodes to preserve memory size
            turn["added_count"] = len(nodes_diff.get("added", []))
            turn["removed_count"] = len(nodes_diff.get("removed", []))
            turn["changed_count"] = len(nodes_diff.get("changed", []))
            
        self.turns.append(turn)

    def get_context_summary(self) -> str:
        """
        Formats the history of recent actions into a concise text representation.
        """
        if not self.turns:
            return "No previous actions in this session."
            
        summary = ["Recent Actions:"]
        for idx, turn in enumerate(self.turns, start=1):
            action = turn["action"]
            params = turn["params"]
            status = turn["status"]
            
            detail_parts = []
            for k, v in params.items():
                if k in ("url", "ref", "text"):
                    detail_parts.append(f"{k}={v}")
            details = f" ({', '.join(detail_parts)})" if detail_parts else ""
            
            line = f"{idx}. {action}{details} -> {status}"
            if "error" in turn:
                line += f" (Error: {turn['error']})"
            elif "added_count" in turn:
                line += f" (Added {turn['added_count']} nodes, removed {turn['removed_count']}, changed {turn['changed_count']})"
                
            summary.append(line)
            
        return "\n".join(summary)

    def clear(self) -> None:
        self.turns.clear()
