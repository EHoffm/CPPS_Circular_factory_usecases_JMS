from graph_db_interface import IRI, GraphDBCredentials
from circular_factory_ogm.ogm import OGM
import json


credentials = GraphDBCredentials(
    base_url="http://graphdb.iam-mms.kit.edu/",
    username="your_username",
    password="your_password",
    repository="OGM",
)

#GraphdbCredentials.from_env()

class AnomalyDetector:
    def __init__(self, threshold: float):
        self.threshold = threshold
        ogm = OGM(db=GraphDB(credentials=credentials), loader=None)
        


    def fetch_process_model(instance_iri: IRI):
        """ retrieves Time Series Data of an unscrewing process as a node via OGM.fetch(), processes well known json format, returns Time Serias as 
        preferred Data Structure (e.g. list of floats)
        """
        property_chains= [[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData"), IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData")],
            [IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData"), IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus")] ]]
        fetched_instance= self.ogm.fetch(instance_iri, property_chains=property_chains).instance
        return fetched_instance.model_dump()
    def detect_anomaly(self, data: dict) -> dict:
        """ processes fetched data, detects anomalies, returns annotated data structure
        """
        
       lower_tightening_torque = data.hasLowerTighteningTorque
         
        data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus")] = "Successful"
        
        return data
    
    def update_instance(self, instance_iri: IRI, data: dict):
        """ updates the instance in the graphdb with the annotated data
        """
        self.ogm.commit(instance_iri, data, persist=True) #Todo für Etienne in KW 4
        
    


