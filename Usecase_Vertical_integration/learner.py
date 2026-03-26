from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from kapps_ogm.ogm import OGM
import json


# GraphdbCredentials.from_env()


class Learner:
    def __init__(self):
        credentials = GraphDBCredentials.from_env()
        self.ogm = OGM(db=GraphDB(credentials=credentials), loader=None)
        self.process_desriptions = (
            []
        )  # list to hold fetched process descriptions per screw type
        self.learned_parameters = {}  # dict to hold learned parameters per screw type
        self.screws = [
            s
            for s, p, o in self.ogm.db.triples_get(
                # pred=IRI("w3.org/1999/02/22-rdf-syntax-ns#type"),
                pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                obj=IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Screw"),
            )
        ]
        self.prop_chains = ["as in anomaly_detector"]

    def get_all_process_descriptions(self):
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
            # self.process_desriptions.append(self.ogm.fetch(self.prop_chains,instance_iri=iri).instance.model_dump()) # type: ignore TODO: Etienne
            self.process_desriptions.append(self.ogm.fetch(self.prop_chains, instance_iri=iri).instance.model_dump(), materialize=True)  # type: ignore TODO: class_scope.from_property_chains(prop_chains)

    def learn_from_process_descriptions(self):
        learned_parameters = {}

        # Parameters for the anomaly detection, to check features of the time series data - learned in learner.py
        # lower_tightening_torque = data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque")] # double, Indicates the minimum torque required to properly tighten the screw - to check if torque can be applied to it.
        # hasUpperDynamicLoseningTorque = data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque")] # double, Specifies the maximum torque at which the screw may loosen during unscrewing
        # hasLowerAxialForce = data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce")] # double; minimum axial force that indicates the screw moving towards the screwdriver
        # hasSuccessStatus = data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus")] # "Successfull" or "Loose Anchor" or Rounded Head" or ...

        # data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus")] = "Successful"

        # mocked Timeseries, in this case from knwoledge graph - in real implementation from robot control
        # unscrewing_torque_time_series = json.loads(data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData")][IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData")])
        # axial_force_time_series = json.loads(data[IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData")][IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData")])

        for screw in self.screws:  # TODO:MG: Hier implementieren wir die Lernlogik
            # implement learning logic here
            # der dict hat die struktur Screw_instance_iri: learned_parameters_dict
            learned_parameters[screw] = {
                "hasOptimalUnscrewingTorque": 5.0,
                "hasOptimalAxialForce": 10.0,
            }  # mocked data
        self.learned_parameters = learned_parameters

    def update_screwing_process_parameters(self, process_iri: IRI, parameters: dict):
        """updates the screwing process parameters in the graphdb with the learned parameters"""
        self.ogm.commit(process_iri, self.learned_parameters, persist=True)  # type: ignore #Todo für Etienne in KW 4
