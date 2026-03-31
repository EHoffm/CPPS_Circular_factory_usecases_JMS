"""System state monitoring helpers for the FlexConveyor visualizer."""

from typing import Any

from kapps_ogm import OGM
from graph_db_interface import IRI


def build_adjacency_matrix(ogm: OGM) -> dict[str, list[tuple[str | None, str | None]]]:
    """Build adjacency map: {module_iri: [(connectsTo, hasDirection), ...]}.

    This version reads triples directly from the FlexConveyorInstances
    named graph so that topology changes (like adding modules or
    connections) are always reflected, even if OGM caches instances.
    """

    adj: dict[str, list[tuple[str | None, str | None]]] = {}

    try:
        instances_graph = "http://w3id.org/circularfactory/FlexConveyorInstances"
        query = (
            "SELECT ?s ?p ?o WHERE { "
            f"GRAPH <{instances_graph}> {{ ?s ?p ?o . }} "
            "}"
        )
        res = ogm.db.query(query=query, convert_bindings=True)
        bindings = (res or {}).get("results", {}).get("bindings", [])
        all_triples = [(b["s"], b["p"], b["o"]) for b in bindings]

        triples_by_subject: dict[str, list[tuple[Any, Any, Any]]] = {}
        for s, p, o in all_triples:
            triples_by_subject.setdefault(str(s), []).append((s, p, o))

        rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
        module_class = "http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"

        modules: set[Any] = set()
        for s, p, o in all_triples:
            if str(p) == rdf_type and str(o) == module_class:
                modules.add(s)

        for module_iri in modules:
            module_key = str(module_iri)
            module_triples = triples_by_subject.get(module_key, [])
            adjacency_entries: list[tuple[str | None, str | None]] = []

            for _s, pred, obj in module_triples:
                pred_str = str(pred).lower()
                if "hasconnection" not in pred_str:
                    continue

                connection_node_str = str(obj)
                conn_triples = triples_by_subject.get(connection_node_str, [])
                target: str | None = None
                direction: str | None = None

                for _cs, c_pred, c_obj in conn_triples:
                    c_pred_str = str(c_pred).lower()
                    if "connectsto" in c_pred_str:
                        target = str(c_obj)
                    elif "hasdirection" in c_pred_str:
                        direction = str(c_obj)

                adjacency_entries.append((target, direction))

            adj[module_key] = adjacency_entries

    except Exception as e:  # pragma: no cover - defensive
        print(f"Exception while building adjacency matrix: {e}")

    return adj


def discover_modules(ogm: OGM) -> list[dict[str, str | None]]:
    print("discover_modules triggered")
    discovered: list[dict[str, str | None]] = []
    instances_graph = "http://w3id.org/circularfactory/FlexConveyorInstances"

    query = f"""
    SELECT DISTINCT ?module ?service_url
    WHERE {{
      GRAPH <{instances_graph}> {{
        ?module <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>
                <http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule> .

        OPTIONAL {{
          {{
            ?module <http://w3id.org/circularfactory/FlexConveyor#hasService> ?service .
          }}
          UNION
          {{
            ?service <http://w3id.org/circularfactory/FlexConveyor#isServiceOf> ?module .
          }}
          ?service <http://w3id.org/circularfactory/FlexConveyor#accessibleAt> ?service_url .
        }}
      }}
    }}
    """

    try:
        res = ogm.db.query(query=query, convert_bindings=True)
        bindings = (res or {}).get("results", {}).get("bindings", [])
    except Exception as e:
        print(f"Error discovering modules: {e}")
        return discovered

    module_to_url: dict[str, str | None] = {}
    for row in bindings:
        module = str(row.get("module")) if row.get("module") else None
        if not module:
            continue

        module_to_url.setdefault(module, None)
        service_url = row.get("service_url")
        if service_url and module_to_url[module] is None:
            module_to_url[module] = str(service_url).split("workflows", 1)[0]

    for module in sorted(module_to_url.keys()):
        print(f"Discovered module: {module}")
        discovered.append(
            {"module_id": module, "accessible_at": module_to_url[module]}
        )

    if not discovered:
        print("No instantiated modules found")

    return discovered


def get_box_locations(ogm: OGM) -> dict[str, list[str]]:
    """Query the knowledge graph to find where boxes currently are located.

    Returns:
        A dictionary mapping module IRIs to lists of box IRIs currently
        possessed by that module. Format: {module_iri: [box_iri, ...]}
    """

    locations: dict[str, list[str]] = {}

    try:
        instances_graph = "http://w3id.org/circularfactory/FlexConveyorInstances"
        query = (
            "SELECT ?module ?box WHERE { "
            f"GRAPH <{instances_graph}> {{ "
            "?module <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
            "<http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule> . "
            "OPTIONAL { "
            "?module <http://w3id.org/circularfactory/FlexConveyor#hasPossession> ?box . "
            "} "
            "}}"
        )
        res = ogm.db.query(query=query, convert_bindings=True)
        bindings = (res or {}).get("results", {}).get("bindings", [])

        for row in bindings:
            module = str(row.get("module")) if row.get("module") else None
            box = str(row.get("box")) if row.get("box") else None
            if not module or not box:
                continue
            locations.setdefault(module, []).append(box)

        return locations

    except Exception as e:
        print(f"Error querying box locations: {e}")
        return {}
