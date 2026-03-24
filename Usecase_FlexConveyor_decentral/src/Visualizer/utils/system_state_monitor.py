"""System state monitoring helpers for the FlexConveyor visualizer."""

from typing import Any

from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
from graph_db_interface import IRI, GraphDB


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


def _as_dict(instance: Any) -> dict[str, Any]:
    if isinstance(instance, dict):
        return instance
    if hasattr(instance, "model_dump"):
        return instance.model_dump(by_alias=True)
    if hasattr(instance, "dict"):
        return instance.dict()
    return {}


def discover_modules(ogm: OGM) -> list[dict[str, str | None]]:
    print("discover_modules triggered")

    db: GraphDB = ogm.db
    triples = db.triples_get(
        pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
        obj=IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"),
    )
    modules = [triple[0] for triple in triples]
    discovered: list[dict[str, str | None]] = []

    if not modules:
        print("No instantiated modules found")
        return discovered

    has_service_key = IRI(
        "http://w3id.org/circularfactory/FlexConveyor#hasService"
    ).lined
    accessible_at_key = IRI(
        "http://w3id.org/circularfactory/FlexConveyor#accessibleAt"
    ).lined

    for module in modules:
        print(f"Discovered module: {module}")
        prop_chains = [
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasService"),
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
                IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
            ],
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection"),
            ],
        ]
        module_service = ogm.fetch(
            instance_iri=module,
            class_scope=ClassScope.from_property_chains(prop_chains),
            materialize=True,
        )
        module_data = _as_dict(module_service.instance)
        services = module_data.get(has_service_key, [])

        accessible_at: str | None = None
        for service in services:
            if not isinstance(service, dict):
                continue
            locations = service.get(accessible_at_key, [])
            if not locations:
                continue
            first_location = locations[0].split("workflows")[0]
            if isinstance(first_location, dict):
                accessible_at = first_location.get("id")
            else:
                accessible_at = str(first_location)
            if accessible_at:
                break

        discovered.append({"module_id": str(module), "accessible_at": accessible_at})

    return discovered


def get_box_locations(ogm: OGM) -> dict[str, list[str]]:
    """Query the knowledge graph to find where boxes currently are located.

    Returns:
        A dictionary mapping module IRIs to lists of box IRIs currently
        possessed by that module. Format: {module_iri: [box_iri, ...]}
    """

    locations: dict[str, list[str]] = {}

    try:
        has_possession = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#hasPossession"
        )
        rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        module_class = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"
        )

        # Get all modules
        module_triples = ogm.db.triples_get(pred=rdf_type, obj=module_class)
        modules = [triple[0] for triple in module_triples]

        # For each module, find boxes it possesses
        for module_iri in modules:
            possession_triples = ogm.db.triples_get(sub=module_iri, pred=has_possession)
            boxes = (
                [str(triple[2]) for triple in possession_triples]
                if possession_triples
                else []
            )
            if boxes:
                locations[str(module_iri)] = boxes

        return locations

    except Exception as e:
        print(f"Error querying box locations: {e}")
        return {}
