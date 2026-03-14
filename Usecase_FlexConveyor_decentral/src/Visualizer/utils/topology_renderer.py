"""Helpers to convert GraphDB adjacency data into topology row format."""

from __future__ import annotations

from collections import deque
from typing import Any
from graph_db_interface import IRI
import matplotlib.patches as patches
import matplotlib.pyplot as plt


class FlexConveyorNode:
    def __init__(self, node_id: IRI):
        self.id = node_id
        self.upper_connected_module: FlexConveyorNode | None = None
        self.right_connected_module: FlexConveyorNode | None = None
        self.lower_connected_module: FlexConveyorNode | None = None
        self.left_connected_module: FlexConveyorNode | None = None
        self.x = 0
        self.y = 0


def _direction_to_index(direction: str | None) -> int | None:
    if not direction:
        return None
    direction_map = {
        "http://w3id.org/circularfactory/FlexConveyor#North": 1,
        "http://w3id.org/circularfactory/FlexConveyor#East": 2,
        "http://w3id.org/circularfactory/FlexConveyor#South": 3,
        "http://w3id.org/circularfactory/FlexConveyor#West": 4,
    }
    return direction_map.get(str(direction))


def _find_key_containing(data: dict[str, Any], token: str) -> str | None:
    token_lower = token.lower()
    for key in data:
        if token_lower in key.lower():
            return key
    return None


def _first_nested_id(items: Any) -> str | None:
    if not isinstance(items, list) or not items:
        return None

    first_item = items[0]
    if isinstance(first_item, dict):
        value = first_item.get("id")
        return str(value) if value else None

    return str(first_item)


def modules_payload_to_adjacency_map(
    modules_payload: list[dict[str, Any]],
) -> dict[IRI, list[tuple[IRI | None, str | None]]]:
    """Convert module payload list into {module_id: [(target, direction), ...]} map."""
    adjacency_map: dict[IRI, list[tuple[IRI | None, str | None]]] = {}

    for module in modules_payload:
        if not isinstance(module, dict):
            continue

        module_id_value = module.get("id")
        if not module_id_value:
            continue
        module_id = IRI(str(module_id_value))

        has_connection_key = _find_key_containing(module, "hasConnection")
        connections = module.get(has_connection_key, []) if has_connection_key else []

        entries: list[tuple[IRI | None, str | None]] = []
        if isinstance(connections, list):
            for connection in connections:
                if not isinstance(connection, dict):
                    continue

                connects_to_key = _find_key_containing(connection, "connectsTo")
                has_direction_key = _find_key_containing(connection, "hasDirection")

                target_text = _first_nested_id(
                    connection.get(connects_to_key, []) if connects_to_key else []
                )
                target = IRI(target_text) if target_text else None
                direction = _first_nested_id(
                    connection.get(has_direction_key, []) if has_direction_key else []
                )
                entries.append((target, direction))

        adjacency_map[module_id] = entries

    return adjacency_map


def adjacency_map_to_directional_rows(
    adjacency_map: dict[str | IRI, list[tuple[str | IRI | None, str | None]]] | list[dict[str, Any]],
) -> list[list[IRI | int]]:
    """Convert adjacency data to [module, up, right, down, left] rows.

    Accepts either:
    - {module_id: [(target_id, direction_id), ...]}
    - [{id: ..., hasConnection: [{connectsTo: [{id: ...}], hasDirection: [{id: ...}]}]}]

    Direction mapping: North->up, East->right, South->down, West->left.
    """
    normalized_map: dict[IRI, list[tuple[IRI | None, str | None]]] = {}
    if isinstance(adjacency_map, list):
        normalized_map = modules_payload_to_adjacency_map(adjacency_map)
    else:
        for module_id, entries in adjacency_map.items():
            module_iri = module_id if isinstance(module_id, IRI) else IRI(str(module_id))
            normalized_entries: list[tuple[IRI | None, str | None]] = []
            for target, direction in entries:
                target_iri = (
                    target if isinstance(target, IRI) else IRI(str(target)) if target else None
                )
                normalized_entries.append((target_iri, direction))
            normalized_map[module_iri] = normalized_entries

    rows: list[list[IRI | int]] = []

    for module_iri in sorted(normalized_map.keys(), key=str):
        row: list[IRI | int] = [module_iri, 0, 0, 0, 0]

        for target, direction in normalized_map[module_iri]:
            if not target:
                continue
            index = _direction_to_index(direction)
            if index is None:
                continue
            if row[index] == 0:
                row[index] = target

        rows.append(row)

    return rows


def _build_nodes_from_directional_rows(
    directional_rows: list[list[IRI | int]],
) -> list[FlexConveyorNode]:
    nodes_by_id: dict[str, FlexConveyorNode] = {}
    for row in directional_rows:
        if not row:
            continue
        node_id = row[0] if isinstance(row[0], IRI) else IRI(str(row[0]))
        node_key = str(node_id)
        if node_key not in nodes_by_id:
            nodes_by_id[node_key] = FlexConveyorNode(node_id)

    for row in directional_rows:
        if len(row) < 5:
            continue
        current_id = row[0] if isinstance(row[0], IRI) else IRI(str(row[0]))
        current_node = nodes_by_id[str(current_id)]

        neighbors = [row[1], row[2], row[3], row[4]]
        for index, neighbor_id in enumerate(neighbors):
            if neighbor_id == 0 or neighbor_id is None:
                continue

            neighbor_iri = neighbor_id if isinstance(neighbor_id, IRI) else IRI(str(neighbor_id))
            neighbor_key = str(neighbor_iri)
            if neighbor_key not in nodes_by_id:
                nodes_by_id[neighbor_key] = FlexConveyorNode(neighbor_iri)

            neighbor_node = nodes_by_id[neighbor_key]
            if index == 0:
                current_node.upper_connected_module = neighbor_node
            elif index == 1:
                current_node.right_connected_module = neighbor_node
            elif index == 2:
                current_node.lower_connected_module = neighbor_node
            else:
                current_node.left_connected_module = neighbor_node

    return [nodes_by_id[str(row[0] if isinstance(row[0], IRI) else IRI(str(row[0])))] for row in directional_rows if row]


def _layout_nodes(nodes: list[FlexConveyorNode]) -> None:
    if not nodes:
        return

    width = 50
    height = 50
    base_x = 150
    base_y = 150
    root = nodes[0]

    positioned: dict[FlexConveyorNode, tuple[int, int]] = {root: (base_x, base_y)}
    queueing: deque[FlexConveyorNode] = deque([root])

    deltas = [
        (0, 1),
        (1, 0),
        (0, -1),
        (-1, 0),
    ]

    while queueing:
        current = queueing.popleft()
        current_x, current_y = positioned[current]
        current.x = current_x
        current.y = current_y

        neighbors = [
            current.upper_connected_module,
            current.right_connected_module,
            current.lower_connected_module,
            current.left_connected_module,
        ]

        for index, neighbor in enumerate(neighbors):
            if neighbor is None or neighbor in positioned:
                continue
            delta_x, delta_y = deltas[index]
            positioned[neighbor] = (current_x + delta_x * width, current_y + delta_y * height)
            queueing.append(neighbor)


def _compute_figure_geometry(nodes: list[FlexConveyorNode]):
    """Compute figure size and axis limits based on node layout."""

    min_x = min(node.x for node in nodes)
    max_x = max(node.x for node in nodes)
    min_y = min(node.y for node in nodes)
    max_y = max(node.y for node in nodes)

    padding = 100
    width_range = max_x - min_x + 2 * padding
    height_range = max_y - min_y + 2 * padding
    fig_width = min(max(8, width_range / 80), 20)
    fig_height = min(max(6, height_range / 80), 16)

    return (min_x, max_x, min_y, max_y, padding, fig_width, fig_height)


def directional_rows_to_figure(directional_rows: list[list[IRI | int]]):
    """Render a matplotlib topology figure from [module, up, right, down, left] rows."""
    nodes = _build_nodes_from_directional_rows(directional_rows)
    _layout_nodes(nodes)

    fig, ax = plt.subplots(figsize=(8, 6))

    if not nodes:
        ax.set_title("FlexConveyor Topology")
        ax.set_axis_off()
        return fig

    min_x, max_x, min_y, max_y, padding, fig_width, fig_height = _compute_figure_geometry(nodes)
    fig.set_size_inches(fig_width, fig_height)

    for node in nodes:
        rect = patches.Rectangle(
            (node.x - 25, node.y - 25),
            50,
            50,
            linewidth=2,
            edgecolor="black",
            facecolor="lightblue",
        )
        ax.add_patch(rect)
        ax.text(
            node.x,
            node.y,
            str(node.id.fragment),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_xlim(min_x - padding, max_x + padding)
    ax.set_ylim(min_y - padding, max_y + padding)
    ax.set_aspect("equal")
    ax.set_axis_off()

    try:
        fig.tight_layout()
    except UserWarning:
        fig.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.1)

    return fig


def directional_rows_to_figure_with_box(
    directional_rows: list[list[IRI | int]],
    box_module_iri: str | IRI | None,
):
    """Render topology with an overlaid brown box at the given module.

    Uses the same layout and node rendering as `directional_rows_to_figure`
    and draws an additional smaller rectangle centered on the selected
    module to represent a moving box.
    """

    nodes = _build_nodes_from_directional_rows(directional_rows)
    _layout_nodes(nodes)

    fig, ax = plt.subplots(figsize=(8, 6))

    if not nodes:
        ax.set_title("FlexConveyor Topology")
        ax.set_axis_off()
        return fig

    min_x, max_x, min_y, max_y, padding, fig_width, fig_height = _compute_figure_geometry(nodes)
    fig.set_size_inches(fig_width, fig_height)

    box_module_str = str(box_module_iri) if box_module_iri is not None else None

    for node in nodes:
        rect = patches.Rectangle(
            (node.x - 25, node.y - 25),
            50,
            50,
            linewidth=2,
            edgecolor="black",
            facecolor="lightblue",
        )
        ax.add_patch(rect)
        ax.text(
            node.x,
            node.y,
            str(node.id.fragment),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
        )

        if box_module_str is not None and str(node.id) == box_module_str:
            # Draw a smaller brown box centered in the module to
            # represent the moving parcel.
            box_rect = patches.Rectangle(
                (node.x - 10, node.y - 10),
                20,
                20,
                linewidth=1.5,
                edgecolor="saddlebrown",
                facecolor="peru",
            )
            ax.add_patch(box_rect)

    ax.set_xlim(min_x - padding, max_x + padding)
    ax.set_ylim(min_y - padding, max_y + padding)
    ax.set_aspect("equal")
    ax.set_axis_off()

    try:
        fig.tight_layout()
    except UserWarning:
        fig.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.1)

    return fig
