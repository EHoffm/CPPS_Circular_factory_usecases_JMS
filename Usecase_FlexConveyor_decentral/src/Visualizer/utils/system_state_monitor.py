"""System state monitoring helpers for the FlexConveyor visualizer."""

from typing import Any

from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
from graph_db_interface import IRI, GraphDB


def build_adjacency_matrix(ogm: OGM) -> dict[str, list[tuple[str | None, str | None]]]:
    """Build adjacency map: {module_iri: [(connectsTo, hasDirection), ...]}."""
    adj: dict[str, list[tuple[str | None, str | None]]] = {}

    rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    module_class = IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule")
    has_connection = IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection")
    connects_to = IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo")
    has_direction = IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection")

    triples = ogm.db.triples_get(pred=rdf_type, obj=module_class)
    modules = [triple[0] for triple in triples]

    property_chains = [
        [has_connection, connects_to],
        [has_connection, has_direction],
    ]
    class_scope = ClassScope.from_property_chains(property_chains)

    has_connection_key = has_connection.lined
    connects_to_key = connects_to.lined
    has_direction_key = has_direction.lined

    for module_iri in modules:
        module_instance = ogm.fetch(
            instance_iri=module_iri,
            class_scope=class_scope,
            materialize=True,
        ).instance

        if isinstance(module_instance, dict):
            module_data = module_instance
        elif hasattr(module_instance, "model_dump"):
            module_data = module_instance.model_dump(by_alias=True)
        elif hasattr(module_instance, "dict"):
            module_data = module_instance.dict()
        else:
            module_data = {}

        connections = module_data.get(has_connection_key, [])
        adjacency_entries: list[tuple[str | None, str | None]] = []

        for connection in connections:
            if not isinstance(connection, dict):
                continue

            connects_to_list = connection.get(connects_to_key, [])
            direction_list = connection.get(has_direction_key, [])

            target: str | None = None
            if connects_to_list:
                first_target = connects_to_list[0]
                if isinstance(first_target, dict):
                    target = first_target.get("id")
                else:
                    target = str(first_target)

            direction: str | None = None
            if direction_list:
                first_direction = direction_list[0]
                if isinstance(first_direction, dict):
                    direction = first_direction.get("id")
                else:
                    direction = str(first_direction)

            adjacency_entries.append((target, direction))

        adj[str(module_iri)] = adjacency_entries

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

    has_service_key = IRI("http://w3id.org/circularfactory/FlexConveyor#hasService").lined
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
            ]
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
            first_location = locations[0]
            if isinstance(first_location, dict):
                accessible_at = first_location.get("id")
            else:
                accessible_at = str(first_location)
            if accessible_at:
                break

        discovered.append(
            {"module_id": str(module), "accessible_at": accessible_at}
        )

    return discovered

