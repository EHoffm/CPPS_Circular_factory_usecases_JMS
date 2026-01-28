from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from circular_factory_ogm.ogm import OGM
import json


credentials = GraphDBCredentials.from_env()

#GraphdbCredentials.from_env()

class ScrewingResource:
    def __init__(self):
        self.ogm = OGM(db=GraphDB(credentials=credentials), loader=None)
        
    def  write_time_series_data_to_knowledge_graph(self, screw_type:IRI):
        screw_types = {
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M3_Screw"): "M3_Screw",
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M4_Screw"): "M4_Screw",
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M5_Screw"): "M5_Screw",
        }
        for screw in screw_types: #TODO: MG: Hier mocken wir zeitreihen Daten. In der echten Implementierung würde hier eine transformerzelle angesteuert
            #die zeitreihen werden dann im KG Abgelegt
            #simulates a screwing process and randomly generates a result data structure
            result= {}
            data: {hasScrew: screw_type,
                hasunscrewingTorqueTimeSeriesData: [...],
                hasAxialForceTimeSeriesData: [...]}
            self.ogm.create(class_iri=IRI(":unscrewingOperation"), data=data, persist=True)
        
    