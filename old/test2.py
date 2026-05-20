from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from kapps_ogm import OGM, ClassScope


db = GraphDB(credentials=GraphDBCredentials.from_env())
ogm = OGM(db=db)

data = {
    "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module44",
    "http://w3id.org/circularfactory/Workflow#hasWorkflow": [
        {
            "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Workflow1",
        }
    ],
}

ogm.create(
    class_iri=IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"),
    class_scope=ClassScope.from_data_dict(data),
    data=data,
)

appended_data = {
    "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module44",
    "http://w3id.org/circularfactory/Workflow#hasWorkflow": [
        {
            "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Workflow2",
        }
    ],
}

ogm.create(
    class_iri=IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"),
    class_scope=ClassScope.from_data_dict(appended_data),
    data=appended_data,
)
