"""Runtime control utilities used by the FlexConveyor visualizer.

This module provides small helpers that are re-exported from
`Visualizer.utils` and used by the UI. The implementations here are
kept simple and rely on the FlexConveyor modules' REST API `receive`
workflow.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


def filter_modules_with_urls(
    discovered_modules: List[Dict[str, str | None]],
) -> List[Dict[str, str]]:
    """Return only modules that expose an accessibleAt URL.

    Each item in *discovered_modules* is expected to have at least the
    keys ``module_id`` and ``accessible_at`` (as produced by the
    monitoring helpers).
    """

    filtered: List[Dict[str, str]] = []
    for module in discovered_modules:
        module_id = (module.get("module_id") or "").strip()
        accessible_at = (module.get("accessible_at") or "").strip()
        if not module_id or not accessible_at:
            continue
        filtered.append({"module_id": module_id, "accessible_at": accessible_at})
    return filtered


def inject_box_via_receive(
    entry_module_url: str,
    box_iri: str,
    destination_iri: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Inject a box into a module's `receive` workflow by URL.

    Args:
        entry_module_url: Base service URL of the target module
            (its ``accessibleAt`` value).
        box_iri: IRI of the box to inject.
        destination_iri: Optional destination module IRI to set/override.
        timeout: HTTP request timeout in seconds.

    Returns:
        A dictionary summarizing HTTP status and response body.
    """

    entry_module_url = (entry_module_url or "").strip()
    if not entry_module_url:
        return {"status": "error", "error": "Entry module URL must not be empty"}

    if not box_iri:
        return {"status": "error", "error": "Box IRI must not be empty"}

    base = entry_module_url.rstrip("/")
    receive_url = f"{base}/workflows/receive/execute"

    payload: Dict[str, Any] = {"box_iri": box_iri}
    if destination_iri:
        payload["destination_iri"] = destination_iri

    try:
        response = requests.post(receive_url, json=payload, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network/env dependent
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
