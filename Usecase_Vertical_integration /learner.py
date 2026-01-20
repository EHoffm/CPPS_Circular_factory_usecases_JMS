from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from circular_factory_ogm.ogm import OGM
import json


credentials = GraphDBCredentials(
    base_url="http://graphdb.iam-mms.kit.edu/",
    username="your_username",
    password="your_password",
    repository="OGM",
)

# GraphdbCredentials.from_env()


class Learner:
    process_desriptions = []
    screws = [s for s,p,o in self.ogm.db.triples_get(
        pred=IRI("w3.org/1999/02/22-rdf-syntax-ns#type"),
        obj=IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Screw"),
    )]
    prop_chains = ["as in anomaly_detector" ]
    def __init__(self):
        self.ogm = OGM(db=GraphDB(credentials=credentials), loader=None)

    def get_all_process_descriptions(self) -> list[IRI]:
        iris = [
            s
            for s, p, o in self.ogm.db.triples_get(
                pred=IRI("https://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                obj=IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#ProcessDescription"
                ),
            )
        ]
        for iri in iris:
            self.process_desriptions.append(self.ogm.fetch(iri, property_chains= self.prop_chains).instance.model_dump())

    def learn_from_process_descriptions(self) -> dict:
        learned_parameters = {}
        for screw in self.screws: #TODO:MG: Hier implementieren wir die Lernlogik
        # implement learning logic here
         #der dict hat die struktur Screw_instance_iri: learned_parameters_dict
        
        return learned_parameters
    
    def update_screwing_process_parameters(self, process_iri: IRI, parameters: dict):
        self.ogm.commit(process_iri, parameters, persist=True)