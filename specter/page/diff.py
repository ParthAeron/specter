from typing import Any, Dict, List, Tuple

def parse_axtree_to_dict(axtree_str: str) -> Dict[str, Dict[str, str]]:
    """
    Parses the formatted accessibility tree text into a structured dictionary.
    Keys are refs (e.g. n1), values are dictionaries containing role, name, and details.
    """
    nodes = {}
    for line in axtree_str.splitlines():
        line = line.strip()
        if not line or not line.startswith("["):
            continue
            
        # Parse: [n1] link "Issues" value="x" required
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
            
        ref = parts[0].strip("[]")
        role = parts[1]
        remaining = parts[2] if len(parts) > 2 else ""
        
        # Simple extraction of name (string in quotes)
        name = ""
        if remaining.startswith('"'):
            end_quote_idx = remaining.find('"', 1)
            if end_quote_idx != -1:
                name = remaining[1:end_quote_idx]
                remaining = remaining[end_quote_idx+1:].strip()
                
        nodes[ref] = {
            "role": role,
            "name": name,
            "details": remaining # Contains properties and values
        }
    return nodes

def compute_axtree_diff(old_tree_str: str, new_tree_str: str) -> Dict[str, List[Any]]:
    """
    Computes a delta of additions, removals, and changes between two formatted AXTree states.
    """
    old_nodes = parse_axtree_to_dict(old_tree_str)
    new_nodes = parse_axtree_to_dict(new_tree_str)
    
    added = []
    removed = []
    changed = []
    
    # Check for removals and changes
    for ref, old_node in old_nodes.items():
        if ref not in new_nodes:
            removed.append(ref)
        else:
            new_node = new_nodes[ref]
            if old_node != new_node:
                changed.append({
                    "ref": ref,
                    "role": new_node["role"],
                    "name": new_node["name"],
                    "details": new_node["details"]
                })
                
    # Check for additions
    for ref, new_node in new_nodes.items():
        if ref not in old_nodes:
            added.append({
                "ref": ref,
                "role": new_node["role"],
                "name": new_node["name"],
                "details": new_node["details"]
            })
            
    return {
        "added": added,
        "removed": removed,
        "changed": changed
    }
