"""Runtime control façade for the FlexConveyor visualizer.

Thin wrapper that re-exports helpers from `Visualizer.utils.control` so
that they can be imported from a stable top-level module regardless of
execution context.
"""

from typing import Any, Dict, List, Optional

from Visualizer.utils.control import (
    discover_modules as _discover_modules,
    inject_box as _inject_box,
)


def discover_modules(ogm: Any) -> List[Dict[str, str | None]]:
    return _discover_modules(ogm)


def inject_box(
    ogm: Any,
    entry_module_id: str,
    box_iri: str,
    destination_iri: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    return _inject_box(
        ogm=ogm,
        entry_module_id=entry_module_id,
        box_iri=box_iri,
        destination_iri=destination_iri,
        timeout=timeout,
    )
