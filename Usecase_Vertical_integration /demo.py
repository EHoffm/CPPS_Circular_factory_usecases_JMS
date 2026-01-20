from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from circular_factory_ogm.ogm import OGM
import json


credentials = GraphDBCredentials(
    base_url="http://graphdb.iam-mms.kit.edu/",
    username="your_username",
    password="your_password",
    repository="OGM",
)
def main():
    ogm = OGM(db=GraphDB(credentials=credentials), loader=None)
    screwing_resource = ScrewingResource()
    anomaly_detector = AnomalyDetector(threshold=0.1)
    learner = Learner()
    
    # Example usage:
    screw_type = IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M4_Screw")
    screwing_resource.write_time_series_data_to_knowledge_graph(screw_type)
    process_instance_iri = IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingOperation1")
    fetched_data = anomaly_detector.fetch_process_model(process_instance_iri)
    annotated_data = anomaly_detector.detect_anomaly(fetched_data)
    anomaly_detector.update_instance(process_instance_iri, annotated_data)
    #late at night, the learner awakes. he picks one specific screw type and learns from all process descriptions
    learner.get_all_process_descriptions()
    learned_params = learner.learn_from_process_descriptions()
    for process_iri, params in learned_params.items():
        learner.update_screwing_process_parameters(process_iri, params) 
        
if __name__ == "__main__":
    main()

