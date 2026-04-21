from graph_db_interface import GraphDB, GraphDBCredentials, IRI
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
import json

from dotenv import load_dotenv
from screwing_resource import ScrewingResource
from transformercell_resource import TransformercellResource
from anomaly_detector import AnomalyDetector
from learner import Learner


def main():
    credentials = GraphDBCredentials.from_env()
    ogm = OGM(db=GraphDB(credentials=credentials), loader=None)
    screwing_resource = ScrewingResource()
    transformercell_resource = TransformercellResource()
    anomaly_detector = AnomalyDetector(threshold=0.1)
    learner = Learner()

    named_graph_iri = IRI(
        "http://w3id.org/circularfactory/UsecaseVerticalIntegrationInstances"
    )

    # Clear the named graph before instantiation to avoid stale triples
    print("🧹 Clearing existing instances graph...")
    try:
        ogm.db.clear_graph(named_graph_iri)
        print("  ✓ Graph cleared")
    except Exception as clear_err:
        print(f"  ⚠️  Could not clear graph: {clear_err} (continuing anyway)")

    # Example usage:
    # create the Transformercell instance Transformercell_A with an Anglegrinder and a ScrewingResource
    # the anglegrinder has a part screw of type_M4_Screw
    screw_type = IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M4_Screw")

    transformercell_resource.create_transformercell_instance(
        instance_iri=IRI(
            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Transformercell_A"
        ),
        angle_grinder_iri=IRI(
            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Anglegrinder_099"
        ),
        screwing_resource_iri=IRI(
            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#ScrewingResource_1"
        ),
        screw_iri=screw_type,
        named_graph_iri=named_graph_iri,
    )
    process_instance_iri = IRI(
        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingOperation1"
    )

    # this part until the second print is just for demonstrating, that the screw type can be fetched via the Anglegrinder instance
    fetched_instance = transformercell_resource.ogm.fetch(
        class_scope=ClassScope.from_property_chains(
            [[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPartScrew")]]
        ),
        instance_iri=IRI(
            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Anglegrinder_099"
        ),
    )
    pydantic_model = fetched_instance.materialize()  # TEST
    serialized = pydantic_model.model_dump()
    print("Fetched screw type:")
    print(json.dumps(serialized, indent=2))

    # here the screw_type from the fetch can be used, but since we already have it, we can directly use the screw_type IRI
    screwing_resource.write_time_series_data_to_knowledge_graph(
        screw_type,
        instance_iri=process_instance_iri,
    )

    fetched_data = anomaly_detector.fetch_process_model(
        process_instance_iri
    )  # fetches UnscrewingOperation instance

    annotated_data = anomaly_detector.detect_anomaly(fetched_data)
    # when annotated_data = successful, then update UnscrewingOperation instance and set the hasPartScrew of the angle grinder to none
    anomaly_detector.updateUnscrewingOperationviaProfiNet(
        instance_iri=process_instance_iri, data=annotated_data
    )  # TODO: prüfen ob Problem, wenn named_graph_iri nicht mitgegeben
    # late at night, the learner awakes. he picks one specific screw type and learns from all process descriptions
    learner.get_all_process_descriptions()
    learner.learn_from_process_descriptions()
    for process_iri, params in learner.learned_parameters.items():
        learner.update_screwing_process_parameters(process_iri, params)


if __name__ == "__main__":
    main()
