"""Route planning utilities for the FlexConveyor visualizer.

Provides Dijkstra-based shortest path computation on top of the
adjacency map returned by `utils.system_state_monitor.build_adjacency_matrix`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional


AdjacencyMap = Dict[str, List[Tuple[Optional[str], Optional[str]]]]
Graph = Dict[str, List[str]]


def build_topology_graph(adj_map: AdjacencyMap) -> Graph:
    """Convert `{module: [(target, direction), ...]}` into an undirected graph.

    The direction information is ignored for route computation; edges
    are treated as bidirectional with equal weight.
    """

    graph: Graph = {}

    # Ensure all modules are present
    for module_id in adj_map.keys():
        graph.setdefault(module_id, [])

    # Add undirected edges
    for module_id, entries in adj_map.items():
        for target, _direction in entries:
            if not target:
                continue
            src = module_id
            dst = target
            if dst not in graph.setdefault(src, []):
                graph[src].append(dst)
            if src not in graph.setdefault(dst, []):
                graph[dst].append(src)

    return graph


def dijkstra_shortest_path(graph: Graph, source: str, target: str) -> List[str]:
    """Compute the shortest path between two modules using Dijkstra.

    All edges are treated with unit weight, matching the behavior of
    the FlexConveyorModule's internal routing.
    """

    import heapq

    if source not in graph or target not in graph:
        return []

    distances: Dict[str, float] = {node: float("inf") for node in graph}
    distances[source] = 0.0
    previous: Dict[str, Optional[str]] = {node: None for node in graph}
    visited: set[str] = set()
    pq: List[Tuple[float, str]] = [(0.0, source)]

    while pq:
        current_dist, current = heapq.heappop(pq)
        if current in visited:
            continue
        visited.add(current)

        if current == target:
            break

        for neighbor in graph.get(current, []):
            if neighbor in visited:
                continue
            new_dist = current_dist + 1.0
            if new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                previous[neighbor] = current
                heapq.heappush(pq, (new_dist, neighbor))

    if distances[target] == float("inf"):
        return []

    path: List[str] = []
    node: Optional[str] = target
    while node is not None:
        path.append(node)
        node = previous[node]
    path.reverse()

    return path
