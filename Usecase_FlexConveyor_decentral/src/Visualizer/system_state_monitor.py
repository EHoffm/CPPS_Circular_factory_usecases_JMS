"""System state monitoring helpers for the FlexConveyor visualizer."""

from typing import Any
from Visualizer.utils.system_state_monitor import discover_modules as _discover_modules


def discover_modules(ogm: Any) -> None:
    """Discover instantiated modules in the knowledge graph."""
    _discover_modules(ogm)
