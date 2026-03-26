"""
Live Monitoring Utilities

Provides auto-refreshing monitoring capabilities for the FlexConveyor system.
"""

import io
import time
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from graph_db_interface import IRI


# Module-level state tracking for box changes
_previous_box_state: Optional[Dict[str, Set[str]]] = None


def update_live_monitoring_data(ogm) -> Dict[str, Any]:
    """
    Placeholder method for updating live monitoring data.

    This method is called periodically by the auto-refresh mechanism
    to fetch the latest system state.

    Args:
        ogm: The OGM instance for querying the knowledge graph

    Returns:
        Dictionary containing updated monitoring data
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # Placeholder: In a full implementation, this would:
    # - Query box locations from the knowledge graph
    # - Check module statuses
    # - Retrieve recent events
    # - Process topology changes

    update_data = {
        "timestamp": timestamp,
        "box_count": 0,
        "active_modules": 0,
        "recent_events": [],
        "status": "monitoring_active",
    }

    return update_data


def fetch_box_locations_for_monitoring(ogm) -> Dict[str, List[str]]:
    """
    Fetch current box locations for live monitoring display.

    Only logs when boxes are added or removed from the system.

    Args:
        ogm: The OGM instance for querying the knowledge graph

    Returns:
        Dictionary mapping module IRIs to lists of box IRIs
    """
    global _previous_box_state

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # Import the monitor module to reuse existing functionality
    from utils.system_state_monitor import get_box_locations

    try:
        box_locations = get_box_locations(ogm)

        # Create current state as a set of (module_iri, box_iri) tuples for comparison
        current_state: Dict[str, Set[str]] = {}
        for module_iri, box_iris in box_locations.items():
            current_state[str(module_iri)] = set(str(b) for b in box_iris)

        # Detect changes if we have previous state
        if _previous_box_state is not None:
            # Find all boxes in current state
            current_boxes = {
                (mod, box) for mod, boxes in current_state.items() for box in boxes
            }
            previous_boxes = {
                (mod, box)
                for mod, boxes in _previous_box_state.items()
                for box in boxes
            }

            # Detect added and removed boxes
            added_boxes = current_boxes - previous_boxes
            removed_boxes = previous_boxes - current_boxes

            # Detect moved boxes (same box IRI, different module)
            added_box_iris = {box_iri for _, box_iri in added_boxes}
            removed_box_iris = {box_iri for _, box_iri in removed_boxes}
            moved_box_iris = added_box_iris & removed_box_iris

            # Log moved boxes
            for box_iri in moved_box_iris:
                # Find old and new modules for this box
                old_module = next(mod for mod, box in removed_boxes if box == box_iri)
                new_module = next(mod for mod, box in added_boxes if box == box_iri)

                box_short = box_iri.split("#")[-1] if "#" in box_iri else box_iri
                old_module_short = (
                    old_module.split("#")[-1] if "#" in old_module else old_module
                )
                new_module_short = (
                    new_module.split("#")[-1] if "#" in new_module else new_module
                )
                print(
                    f"[{timestamp}] 📦 ➡️  Box moved: {box_short} | {old_module_short} → {new_module_short}"
                )

            # Remove moved boxes from added/removed sets
            added_boxes = {
                (mod, box) for mod, box in added_boxes if box not in moved_box_iris
            }
            removed_boxes = {
                (mod, box) for mod, box in removed_boxes if box not in moved_box_iris
            }

            # Detect newly added boxes (not moves)
            for module_iri, box_iri in added_boxes:
                box_short = box_iri.split("#")[-1] if "#" in box_iri else box_iri
                module_short = (
                    module_iri.split("#")[-1] if "#" in module_iri else module_iri
                )
                print(f"[{timestamp}] 📦 ➕ Box added: {box_short} @ {module_short}")

            # Detect removed boxes (not moves)
            for module_iri, box_iri in removed_boxes:
                box_short = box_iri.split("#")[-1] if "#" in box_iri else box_iri
                module_short = (
                    module_iri.split("#")[-1] if "#" in module_iri else module_iri
                )
                print(f"[{timestamp}] 📦 ➖ Box removed: {box_short} @ {module_short}")

        # Update previous state
        _previous_box_state = current_state

        return box_locations
    except Exception as e:
        print(f"[{timestamp}] ⚠️ Error fetching box locations: {e}")
        return {}


def format_monitoring_logs(
    box_locations: Dict[str, List[str]], max_entries: int = 20
) -> List[str]:
    """
    Format box location data as log entries for display.

    Args:
        box_locations: Dictionary mapping module IRIs to box IRIs
        max_entries: Maximum number of log entries to return

    Returns:
        List of formatted log strings
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs = []

    if not box_locations:
        logs.append(f"[{timestamp}] No boxes in system")
    else:
        total_boxes = sum(len(boxes) for boxes in box_locations.values())
        logs.append(
            f"[{timestamp}] Monitoring {total_boxes} box(es) across {len(box_locations)} module(s)"
        )

        for module_iri, box_iris in sorted(box_locations.items()):
            module_short = (
                module_iri.split("#")[-1] if "#" in module_iri else module_iri
            )
            for box_iri in box_iris:
                box_short = box_iri.split("#")[-1] if "#" in box_iri else box_iri
                logs.append(f"  • {box_short} @ {module_short}")

    return logs[-max_entries:]


def reset_box_tracking():
    """
    Reset the box tracking state.

    Call this when live monitoring is disabled to clear the tracking state.
    """
    global _previous_box_state
    _previous_box_state = None


def log_monitoring_state_change(enabled: bool):
    """
    Log when live monitoring is activated or deactivated.

    Args:
        enabled: True if monitoring is being enabled, False if disabled
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if enabled:
        print(f"[{timestamp}] 🔴 Live monitoring ACTIVATED")
    else:
        print(f"[{timestamp}] ⏸️  Live monitoring DEACTIVATED")
        reset_box_tracking()


def create_live_topology_figure(
    directional_rows: List[List[Any]], box_locations: Dict[str, List[str]]
) -> io.BytesIO:
    """
    Create a PNG image buffer showing the topology with live box locations.

    This generates a dynamic topology visualization with boxes displayed
    on their current modules, encoded as PNG for fast rendering.

    Args:
        directional_rows: Topology data in [module, north, east, south, west] format
        box_locations: Dictionary mapping module IRIs to lists of box IRIs

    Returns:
        BytesIO buffer containing PNG image data
    """
    # Import the topology module to reuse node building and layout functions
    from utils.topology_renderer import (
        _build_nodes_from_directional_rows,
        _layout_nodes,
        _compute_figure_geometry,
    )

    nodes = _build_nodes_from_directional_rows(directional_rows)
    _layout_nodes(nodes)

    fig, ax = plt.subplots(figsize=(8, 6))

    if not nodes:
        ax.set_title("FlexConveyor Topology")
        ax.set_axis_off()
        return fig

    min_x, max_x, min_y, max_y, padding, fig_width, fig_height = (
        _compute_figure_geometry(nodes)
    )
    fig.set_size_inches(fig_width, fig_height)

    # Create a mapping of module IRI strings to box counts
    module_box_counts = {}
    for module_iri, box_iris in box_locations.items():
        module_box_counts[str(module_iri)] = len(box_iris)

    # Draw modules
    for node in nodes:
        # Determine module color based on whether it has boxes
        module_iri_str = str(node.id)
        has_boxes = (
            module_iri_str in module_box_counts
            and module_box_counts[module_iri_str] > 0
        )

        facecolor = "lightcoral" if has_boxes else "lightblue"

        rect = patches.Rectangle(
            (node.x - 25, node.y - 25),
            50,
            50,
            linewidth=2,
            edgecolor="black",
            facecolor=facecolor,
        )
        ax.add_patch(rect)

        # Module label
        ax.text(
            node.x,
            node.y - 10,
            str(node.id.fragment),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
        )

        # Draw boxes on this module if any
        if has_boxes:
            box_count = module_box_counts[module_iri_str]
            # Draw a box indicator with count
            box_rect = patches.Rectangle(
                (node.x - 10, node.y + 5),
                20,
                10,
                linewidth=1.5,
                edgecolor="saddlebrown",
                facecolor="peru",
            )
            ax.add_patch(box_rect)

            # Box count label
            ax.text(
                node.x,
                node.y + 10,
                f"Box {box_count}",
                ha="center",
                va="center",
                fontsize=7,
                fontweight="bold",
                color="white",
            )

    ax.set_xlim(min_x - padding, max_x + padding)
    ax.set_ylim(min_y - padding, max_y + padding)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title("Live FlexConveyor Topology", fontsize=10, pad=10)

    try:
        fig.tight_layout()
    except UserWarning:
        fig.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.1)

    # Convert figure to PNG buffer for fast rendering
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)  # Close figure to free memory

    return buf
