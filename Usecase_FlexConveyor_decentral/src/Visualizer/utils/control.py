"""Runtime control helpers for the FlexConveyor visualizer.

Provides utilities to inject boxes into running FlexConveyor modules
via their `receive` workflow endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from kapps_ogm.ogm import OGM

from .system_state_monitor import discover_modules as _discover_modules


def discover_modules(ogm: OGM) -> List[Dict[str, str | None]]:
    """Discover instantiated modules and their service URLs.

    Thin wrapper around the system_state_monitor helper so callers
    don't need to import it directly.
    """

    return _discover_modules(ogm)


def inject_box_via_url(
    entry_module_url: str,
    box_iri: str,
    destination_iri: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Fast path: inject a box using a known module service URL.

    This avoids any GraphDB/OGM calls and behaves like a direct
    HTTP request to the module's `receive` workflow.
    """

    entry_module_url = (entry_module_url or "").strip()
    if not entry_module_url:
        return {"status": "error", "error": "Entry module URL must not be empty"}

    if not box_iri:
        return {"status": "error", "error": "Box IRI must not be empty"}

    base_url = entry_module_url.rstrip("/")
    receive_url = f"{base_url}/workflows/receive/execute"

    payload: Dict[str, Any] = {"box_iri": box_iri}
    if destination_iri:
        payload["destination_iri"] = destination_iri

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
        entry_module_url=accessible_at,
        box_iri=box_iri,
        destination_iri=destination_iri,
        timeout=timeout,
    )
