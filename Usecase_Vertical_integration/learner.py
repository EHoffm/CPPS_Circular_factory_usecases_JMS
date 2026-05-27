from graph_db_interface import GraphDB, IRI
from kapps_ogm import ClassScope, OGM

# GraphdbCredentials.from_env()

JMS_Usecase_Demo = "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#"


class Learner:
    def __init__(self):
        self.ogm = OGM(db=GraphDB.from_env())

        self.process_desriptions = (
            []
        )  # list to hold fetched process descriptions per screw type
        self.learned_parameters = {}  # dict to hold learned parameters per screw type
        self.screw_types = [
            triple[0]
            for triple in self.ogm.db.triples_get(
                pred=IRI("rdf:type"),
                obj=IRI(f"{JMS_Usecase_Demo}screw"),
            )
        ]
        property_chains = [
            [
                IRI(f"{JMS_Usecase_Demo}hasScrew"),
            ],
            [
                IRI(f"{JMS_Usecase_Demo}hasUnscrewingTorqueTimeSeriesData"),
                IRI(f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData"),
            ],
            [
                IRI(f"{JMS_Usecase_Demo}hasAxialForceTimeSeriesData"),
                IRI(f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData"),
            ],
            [
                IRI(f"{JMS_Usecase_Demo}hasRobotPositionTimeSeriesData"),
                IRI(f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData"),
            ],
            [
                IRI(f"{JMS_Usecase_Demo}hasSuccessStatus"),
            ],
        ]

        self.class_scope = ClassScope.from_property_chains(property_chains)

    def get_all_process_descriptions(self):
        process_instance_iris = [
            triple[0]
            for triple in self.ogm.db.triples_get(
                pred=IRI("rdf:type"),
                obj=IRI(f"{JMS_Usecase_Demo}Process"),
            )
        ]
        for iri in process_instance_iris:
            process_instance = self.ogm.fetch(
                class_scope=self.class_scope,
                instance_iri=iri,
                materialize=True,
            ).instance
            self.process_desriptions.append(process_instance)

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

        for (
            screw_type
        ) in self.screw_types:  # TODO:MG: Hier implementieren wir die Lernlogik
            # implement learning logic here
            # der dict hat die struktur Screw_instance_iri: learned_parameters_dict
            learned_parameters[screw_type] = {
                IRI(f"{JMS_Usecase_Demo}hasLowerTighteningTorque"): [5.0],
                IRI(f"{JMS_Usecase_Demo}hasUpperDynamicLoseningTorque"): [10.0],
                IRI(f"{JMS_Usecase_Demo}hasLowerAxialForce"): [2.0],
                IRI(f"{JMS_Usecase_Demo}hasAxialForceApproach"): [3.0],
            }  # mocked data
        self.learned_parameters = learned_parameters

    def update_screwing_process_parameters(self, screw_type: IRI, parameters: dict):
        """updates the screwing process parameters in the graphdb with the learned parameters"""
        self.ogm.commit(instance_iri=screw_type, data=parameters)
        print(f"Updated screw type {screw_type} with learned parameters: {parameters}")
