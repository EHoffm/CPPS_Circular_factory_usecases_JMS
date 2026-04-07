from graph_db_interface import GraphDB, GraphDBCredentials, IRI
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
import json

from dotenv import load_dotenv
from screwing_resource import ScrewingResource
from anomaly_detector import AnomalyDetector
from learner import Learner


def main():
    print(load_dotenv())  # Call this at the start of your script
    credentials = GraphDBCredentials.from_env()
    print(credentials)
    ogm = OGM(db=GraphDB(credentials=credentials), loader=None)
    screwing_resource = ScrewingResource()
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
    # TODO: noch den screw_type als instanz erzeugen, wenn noch nicht drin. aus learner?
    process_instance_iri = IRI(
        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingOperation1"
    )
    screw_type = IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M4_Screw")

    screwing_resource.write_time_series_data_to_knowledge_graph(
        screw_type,
        instance_iri=process_instance_iri,
    )

    fetched_data = anomaly_detector.fetch_process_model(process_instance_iri)

    annotated_data = anomaly_detector.detect_anomaly(
        fetched_data
    )  # TODO: ab einschließlich dieser Zeile noch zu debuggen und schauen, ob fetched_data das richtige Format liefert
    anomaly_detector.update_instance(
        process_instance_iri, annotated_data
    )  # TODO: prüfen ob Problem, wenn named_graph_iri nicht mitgegeben
    # late at night, the learner awakes. he picks one specific screw type and learns from all process descriptions
    learner.get_all_process_descriptions()
    learner.learn_from_process_descriptions()
    for process_iri, params in learner.learned_parameters.items():
        learner.update_screwing_process_parameters(process_iri, params)


if __name__ == "__main__":
    main()
