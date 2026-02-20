from __future__ import annotations

import importlib

from graph_db_interface import IRI
from FlexConveyor_Module.FlexConveyorModule import FlexConveyor


def build_adjacency_matrix(module: FlexConveyor):
    """Build an adjacency matrix of connected modules based on the knowledge graph."""
    ogm = module.get_ogm()
    adj: dict[str, list[tuple[str | None, str | None]]] = {}

    has_connection_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection")
    connects_to_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo")
    has_direction_iri = "http://w3id.org/circularfactory/FlexConveyor#hasDirection"

    triples = ogm.db.triples_get(
        pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
        obj=IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"),
    )
    modules = [triple[0] for triple in triples]

    property_chains = [
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection"),
        ],
    ]

    class_scope = importlib.import_module(
        "circular_factory_ogm.utils.class_scope"
    ).ClassScope.from_property_chains(property_chains)

    for module_iri in modules:
        module_instance = ogm.fetch(
            instance_iri=module_iri,
            class_scope=class_scope,
            materialize=True,
        ).instance
        module_data = module_instance if isinstance(module_instance, dict) else {}

        connections = module_data.get(has_connection_iri, [])
        adjacency_entries: list[tuple[str | None, str | None]] = []

        for connection in connections:
            connects_to_list = connection.get(connects_to_iri, [])
            direction_list = connection.get(has_direction_iri, [])

            connects_to = None
            if connects_to_list:
                first_connect = connects_to_list[0]
                if isinstance(first_connect, dict):
                    connects_to = first_connect.get("id")
                else:
                    connects_to = str(first_connect)

            has_direction = str(direction_list[0]) if direction_list else None
            adjacency_entries.append((connects_to, has_direction))

        adj[str(module_iri)] = adjacency_entries

    return adj
    
