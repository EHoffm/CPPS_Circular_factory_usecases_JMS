"""System state monitoring helpers for the FlexConveyor visualizer."""

from typing import Any
from Visualizer.utils.system_state_monitor import discover_modules as _discover_modules
from Visualizer.utils.system_state_monitor import (
    build_adjacency_matrix as _build_adjacency_matrix,
)


def discover_modules(ogm: Any) -> list[dict[str, str | None]]:
    """Discover instantiated modules in the knowledge graph."""
    return _discover_modules(ogm)


def build_adjacency_matrix(ogm: Any):
    """Build adjacency map from FlexConveyor module connections."""
    return _build_adjacency_matrix(ogm)
