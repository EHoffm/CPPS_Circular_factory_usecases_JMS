"""System state monitoring helpers for the FlexConveyor visualizer."""

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.class_scope import ClassScope
from circular_factory_ogm.utils.json_ogm_encoder import OGMEncoder
from graph_db_interface import IRI, GraphDB
import json


def discover_modules(ogm: OGM) -> None:
    print("discover_modules triggered")

    db: GraphDB = ogm.db
    triples = db.triples_get(
        pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
        obj=IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"),
    )
    modules = [triple[0] for triple in triples]
    if not modules:
        print("No instantiated modules found")
    

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
        print(f"Module {module} service info: {json.dumps(module_service.instance, cls=OGMEncoder, indent=2)}")
        
