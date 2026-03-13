from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from kapps_ogm.ogm import OGM
import json
import pandas as pd




#GraphdbCredentials.from_env()

class ScrewingResource:
    def __init__(self):
        credentials = GraphDBCredentials.from_env()
        self.ogm = OGM(db=GraphDB(credentials=credentials), loader=None)
        
    def  write_time_series_data_to_knowledge_graph(self, screw_type:IRI):
        screw_types = {
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M3_Screw"): "success",
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M4_Screw"): "missing_screw",
            #IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M5_Screw"): "M5_Screw",
        }
        for screw in screw_types: #TODO: MG: Hier mocken wir zeitreihen Daten. In der echten Implementierung würde hier eine transformerzelle angesteuert
            #die zeitreihen werden dann im KG Abgelegt
            #simulates a screwing process and randomly generates a result data structure
            result= {}
            #data: {hasScrew: screw_type,
            #    hasunscrewingTorqueTimeSeriesData: [...],
            #    hasAxialForceTimeSeriesData: [...]}
            pdData = pd.read_csv(f"Usecase_Vertical_integration/unscrewing_timeseries/{screw_types[screw]}.csv")
            data = {
                "hasScrew": screw,
                "hasUnscrewingTorqueTimeSeriesData": pdData["UnscrewingTorque"].to_list(),
                "hasAxialForceTimeSeriesData": pdData["AxialForce"].to_list(), 
                "hasRobotPositionTimeSeriesData": pdData["RobotPosition"].to_list(),
            }
            self.ogm.create(class_iri=IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#unscrewingOperation"), data=data, persist=True)
        
    