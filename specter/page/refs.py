import structlog
from typing import Dict, Optional
from specter.cdp import CDPSession

logger = structlog.get_logger()

class RefRegistry:
    def __init__(self):
        self._ref_to_id: Dict[str, int] = {}
        self._id_to_ref: Dict[int, str] = {}
        self._counter = 1

    def register(self, backend_node_id: int) -> str:
        """
        Registers a stable backend_node_id and returns a short reference string (e.g. n1).
        If already registered, returns the existing ref.
        """
        if backend_node_id in self._id_to_ref:
            return self._id_to_ref[backend_node_id]
            
        ref = f"n{self._counter}"
        self._counter += 1
        
        self._ref_to_id[ref] = backend_node_id
        self._id_to_ref[backend_node_id] = ref
        return ref

    def get_backend_id(self, ref: str) -> Optional[int]:
        return self._ref_to_id.get(ref)

    def get_ref(self, backend_node_id: int) -> Optional[str]:
        return self._id_to_ref.get(backend_node_id)

    def clear(self) -> None:
        self._ref_to_id.clear()
        self._id_to_ref.clear()
        self._counter = 1

    async def resolve_to_node_id(self, session: CDPSession, ref: str) -> int:
        """
        Translates a short ref (e.g. n4) into the active context's volatile DOM nodeId.
        Sends DOM.resolveNode to retrieve the runtime ID.
        """
        backend_id = self.get_backend_id(ref)
        if not backend_id:
            raise ValueError(f"Reference '{ref}' is not registered or has expired.")
            
        try:
            # We must ensure the DOM domain is initialized for this session by requesting the document root once
            await session.send("DOM.getDocument", {"depth": 0})
            
            response = await session.send("DOM.pushNodesByBackendIdsToFrontend", {
                "backendNodeIds": [backend_id]
            })
            node_ids = response.get("nodeIds")
            if not node_ids or not isinstance(node_ids, list):
                raise RuntimeError(f"Failed to push backendNodeId to frontend: {backend_id}")
            return node_ids[0]
        except Exception as e:
            logger.error("Failed to resolve stable ref to runtime nodeId", ref=ref, backend_id=backend_id, error=str(e))
            raise RuntimeError(f"Could not resolve element '{ref}' in the active DOM session. Element might have been detached.") from e
