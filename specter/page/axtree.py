import structlog
from typing import Any, Dict, List, Optional, Set, Tuple
from specter.cdp import CDPSession

logger = structlog.get_logger()

INTERACTIVE_ROLES = {
    "link", "button", "checkbox", "textbox", "searchbox", "combobox", 
    "listbox", "menuitem", "radio", "tab", "treeitem", "slider", "spinbutton"
}

SEMANTIC_ROLES = {
    "heading", "alert", "dialog", "form", "main", "navigation", "article", "status"
}

class AXNode:
    def __init__(self, raw_node: dict[str, Any]):
        self.node_id = raw_node.get("nodeId")
        self.role = raw_node.get("role", {}).get("value")
        self.name = raw_node.get("name", {}).get("value", "")
        self.description = raw_node.get("description", {}).get("value", "")
        self.value = raw_node.get("value", {}).get("value", "")
        self.backend_node_id = raw_node.get("backendDOMNodeId")
        
        # Extract properties
        self.properties: Dict[str, Any] = {}
        for prop in raw_node.get("properties", []):
            name = prop.get("name")
            val = prop.get("value", {})
            self.properties[name] = val.get("value")
            
        self.child_ids: List[str] = raw_node.get("childIds", [])
        self.children: List['AXNode'] = []

    @property
    def is_interactive(self) -> bool:
        if self.role in INTERACTIVE_ROLES:
            return True
        # Check if focusable property is set to True
        return self.properties.get("focusable") is True

    @property
    def is_semantic(self) -> bool:
        return self.role in SEMANTIC_ROLES

    @property
    def is_ignored(self) -> bool:
        if not self.role:
            return True
        if self.role in ("none", "presentation"):
            return True
        if self.properties.get("hidden") is True:
            return True
        return False

def build_ax_tree(raw_nodes: List[dict[str, Any]]) -> Optional[AXNode]:
    if not raw_nodes:
        return None
        
    # Map raw nodes by ID
    node_map = {node["nodeId"]: AXNode(node) for node in raw_nodes}
    
    # Establish child links
    for node in node_map.values():
        for cid in node.child_ids:
            child = node_map.get(cid)
            if child:
                node.children.append(child)
                
    # Usually the first node returned is the root
    root_id = raw_nodes[0]["nodeId"]
    return node_map.get(root_id)

def collapse_repetitive_children(children: List[AXNode], threshold: int = 5) -> Tuple[List[AXNode], int]:
    if not children:
        return [], 0
        
    collapsed: List[AXNode] = []
    collapsed_count = 0
    i = 0
    while i < len(children):
        group_role = children[i].role
        # Find the run of consecutive children with the same role
        j = i
        while j < len(children) and children[j].role == group_role and children[j].role is not None:
            j += 1
            
        group_len = j - i
        if group_len > threshold:
            # Collapse: keep first 2, collapse the rest except the last 1
            collapsed.append(children[i])
            collapsed.append(children[i+1])
            
            suppressed_count = group_len - 3
            collapsed_count += suppressed_count
            # Create a virtual placeholder node
            placeholder = AXNode({
                "nodeId": f"collapsed-{i}-{j}",
                "role": {"value": "collapsed-placeholder"},
                "name": {"value": f"{suppressed_count} elements of role '{group_role}' collapsed (RGX Mode)"},
                "backendDOMNodeId": None
            })
            collapsed.append(placeholder)
            collapsed.append(children[j-1])
        else:
            # Keep as is
            for k in range(i, j):
                collapsed.append(children[k])
        i = j
    return collapsed, collapsed_count

class AXTreeParser:
    def __init__(self, ref_registry: Any):
        self.ref_registry = ref_registry
        self.last_collapsed_count = 0

    async def fetch_and_format(self, session: CDPSession, rgx_mode: bool = False) -> Tuple[str, int]:
        """
        Fetches the full accessibility tree and formats it into a structured text snapshot.
        Supports rgx_mode for sibling container collapsing.
        Returns the formatted string and the count of interactive elements found.
        """
        try:
            await session.send("Accessibility.enable", {})
            response = await session.send("Accessibility.getFullAXTree", {})
        except Exception as e:
            logger.error("Failed to fetch accessibility tree", error=str(e))
            return "Error loading page accessibility data.", 0
            
        raw_nodes = response.get("nodes", [])
        root = build_ax_tree(raw_nodes)
        
        if not root:
            return "Empty page.", 0
            
        # Reset and prepare ref registry for this page load snapshot
        self.ref_registry.clear()
        self.last_collapsed_count = 0
        
        formatted_lines = []
        interactive_count = 0
        
        def walk(node: AXNode, depth: int = 0):
            nonlocal interactive_count
            
            if node.is_ignored:
                # Still recurse children but skip formatting
                children_to_walk = node.children
                if rgx_mode:
                    children_to_walk, c_count = collapse_repetitive_children(node.children)
                    self.last_collapsed_count += c_count
                for child in children_to_walk:
                    walk(child, depth)
                return

            if node.role == "collapsed-placeholder":
                indent = "  " * depth
                formatted_lines.append(f"{indent}... {node.name}")
                return

            if node.is_interactive or node.is_semantic:
                # Register stable reference link
                ref = self.ref_registry.register(node.backend_node_id) if node.backend_node_id else "n/a"
                
                # Format node details
                role_str = node.role.lower() if node.role else ""
                name_str = f'"{node.name}"' if node.name else '""'
                
                parts = [f"[{ref}]", f"{role_str:<12}", name_str]
                
                # Append value if input textbox/combobox
                if node.value:
                    parts.append(f'value="{node.value}"')
                    
                # Append properties (like required, invalid, selected)
                if node.properties.get("required") is True:
                    parts.append("required")
                if node.properties.get("selected") is True:
                    parts.append("selected")
                if node.properties.get("disabled") is True:
                    parts.append("disabled")
                if node.properties.get("invalid") is True:
                    parts.append("invalid")
                    
                indent = "  " * depth
                formatted_lines.append(f"{indent}{' '.join(parts)}")
                
                if node.is_interactive:
                    interactive_count += 1
                
                # Recurse with deeper indentation
                children_to_walk = node.children
                if rgx_mode:
                    children_to_walk, c_count = collapse_repetitive_children(node.children)
                    self.last_collapsed_count += c_count
                for child in children_to_walk:
                    walk(child, depth + 1)
            else:
                # Pure container node, recurse children at current depth
                children_to_walk = node.children
                if rgx_mode:
                    children_to_walk, c_count = collapse_repetitive_children(node.children)
                    self.last_collapsed_count += c_count
                for child in children_to_walk:
                    walk(child, depth)
                    
        walk(root)
        return "\n".join(formatted_lines), interactive_count
