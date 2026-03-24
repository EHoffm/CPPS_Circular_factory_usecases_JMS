"""Runtime control helpers for the FlexConveyor visualizer.

Provides utilities to inject boxes into running FlexConveyor modules
via their `receive` workflow endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from kapps_ogm.ogm import OGM
from graph_db_interface.utils.iri import IRI

from .system_state_monitor import discover_modules as _discover_modules


def discover_modules(ogm: OGM) -> List[Dict[str, str | None]]:
    """Discover instantiated modules and their service URLs.

    Thin wrapper around the system_state_monitor helper so callers
    don't need to import it directly.
    """

    return _discover_modules(ogm)


def _setup_box_ownership(
    ogm: OGM,
    box_iri: str,
    entry_module_iri: str,
) -> bool:
    """Set up box ownership in knowledge graph before injection.

    Creates the box if it doesn't exist and transfers ownership to the
    entry module. This is required because the receive workflow no longer
    handles ownership transfer.

    Returns:
        True if successful, False otherwise.
    """
    try:
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        box = IRI(box_iri)
        entry_module = IRI(entry_module_iri)

        rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        box_class = IRI(f"{FC}Box")
        has_possession = IRI(f"{FC}hasPossession")
        is_possessed_by = IRI(f"{FC}isPossessedBy")

        # Ensure box exists
        existing = ogm.db.triples_get(sub=box, pred=rdf_type, obj=box_class)
        if not existing:
            ogm.db.triples_add(
                [(box, rdf_type, box_class)],
                check_exist=False,
                named_graph=named_graph,
            )

        # Set box status to "inTransit"
        hasState = IRI(f"{FC}hasState")
        inTransit = IRI(f"{FC}InTransit")
        state = ogm.db.triples_get(sub=box, pred=hasState)
        if state:
            ogm.db.triples_delete(state, check_exist=False, named_graph=named_graph)
        ogm.db.triples_add(
            [(box, hasState, inTransit)],
            check_exist=False,
            named_graph=named_graph,
        )

        # Remove from any previous owner
        old_possessions = ogm.db.triples_get(pred=has_possession, obj=box)
        if old_possessions:
            ogm.db.triples_delete(
                old_possessions, check_exist=False, named_graph=named_graph
            )

        old_possessed = ogm.db.triples_get(sub=box, pred=is_possessed_by)
        if old_possessed:
            ogm.db.triples_delete(
                old_possessed, check_exist=False, named_graph=named_graph
            )

        # Transfer to entry module
        ogm.db.triples_add(
            [
                (entry_module, has_possession, box),
                (box, is_possessed_by, entry_module),
            ],
            check_exist=False,
            named_graph=named_graph,
        )
        return True

    except Exception as e:
        print(f"Error setting up box ownership: {e}")
        return False


def inject_box_via_url(
    ogm: OGM,
    entry_module_iri: str,
    entry_module_url: str,
    box_iri: str,
    destination_iri: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Fast path: inject a box using a known module service URL.

    Sets up ownership in the knowledge graph first, then calls receive
    workflow on the entry module.
    """
    FC = "http://w3id.org/circularfactory/FlexConveyor#"
    INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
    named_graph = IRI(INST)
    has_destination = IRI(f"{FC}hasDestination")

    entry_module_url = (entry_module_url or "").strip()
    if not entry_module_url:
        return {"status": "error", "error": "Entry module URL must not be empty"}

    if not box_iri:
        return {"status": "error", "error": "Box IRI must not be empty"}

    # Set up ownership before calling receive
    if not _setup_box_ownership(ogm, box_iri, entry_module_iri):
        return {
            "status": "error",
            "error": "Failed to set up box ownership in knowledge graph",
        }

    base_url = entry_module_url.rstrip("/")
    receive_url = f"{base_url}/workflows/receive/execute"

    if destination_iri:
        old_destination = ogm.db.triples_get(sub=box_iri, pred=has_destination)
        if old_destination:
            ogm.db.triples_delete(
                old_destination, check_exist=False, named_graph=named_graph
            )
        ogm.db.triples_add(
            [(box_iri, has_destination, IRI(destination_iri))],
            check_exist=False,
            named_graph=named_graph,
        )

    payload: Dict[str, Any] = {"box_iri": box_iri}

    try:
        response = requests.post(receive_url, json=payload, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network / env dependent
        return {
            "status": "error",
            "error": str(exc),
            "receive_url": receive_url,
            "payload": payload,
        }

    status = "ok"
    if response.status_code >= 400:
        status = "downstream_error"

    try:
        body = response.json() if response.text else None
    except Exception:
        body = response.text

    return {
        "status": status,
        "http_status": response.status_code,
        "receive_url": receive_url,
        "payload": payload,
        "response": body,
    }


def inject_box(
    ogm: OGM,
    entry_module_id: str,
    box_iri: str,
    destination_iri: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Backward-compatible helper that resolves a module by ID via OGM.

    Prefer :func:`inject_box_via_url` when you already know the
    module's service URL (e.g. from cached discovery in the UI).
    """

    if ogm is None:
        return {"status": "error", "error": "OGM instance is not initialized"}

    if not box_iri:
        return {"status": "error", "error": "Box IRI must not be empty"}

    discovered = discover_modules(ogm)
    if not discovered:
        return {"status": "error", "error": "No instantiated modules discovered"}

    target = None
    for module in discovered:
        if module.get("module_id") == entry_module_id:
            target = module
            break

    if target is None:
        return {
            "status": "error",
            "error": f"Entry module '{entry_module_id}' not found among discovered modules",
            "available_modules": [m.get("module_id") for m in discovered],
        }

    accessible_at = (target.get("accessible_at") or "").strip()
    if not accessible_at:
        return {
            "status": "error",
            "error": f"Module '{entry_module_id}' has no accessibleAt service URL",
        }

    return inject_box_via_url(
        ogm=ogm,
        entry_module_iri=entry_module_id,
        entry_module_url=accessible_at,
        box_iri=box_iri,
        destination_iri=destination_iri,
        timeout=timeout,
    )
