from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from kapps_ogm.utils.class_scope import ClassScope
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
                pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                obj=IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Screw"),
            )
        ]
        self.prop_chains = [
            [
                IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque"
                ),
            ],
            [
                IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque"
                ),
            ],
            [
                IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce"
                ),
            ],
            [
                IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach"
                ),
            ],
            [
                IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceApproach"
                ),
            ],
            [IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasResource")],
            [
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData"
                ),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                ),
            ],
            [
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData"
                ),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                ),
            ],
            [
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasRobotPositionTimeSeriesData"
                ),
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                ),
            ],
            [
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus"
                ),
            ],
        ]

    def get_all_process_descriptions(
        self,
        named_graph_iri: IRI = IRI(
            "http://w3id.org/circularfactory/UsecaseVerticalIntegrationInstances"
        ),
    ) -> None:

        iris = [
            s
            for s, p, o in self.ogm.db.triples_get(
                pred=IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                obj=IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingOperation"
                ),
            )
        ]
        print(f"Found {len(iris)} unscrewing operation instances for learning.")
        print(iris)

        for iri in iris:
            print(f"Fetching data for IRI: {iri}")
            try:
                fetch_result = self.ogm.fetch(
                    class_scope=ClassScope.from_property_chains(self.prop_chains),
                    instance_iri=iri,
                )
                pydantic_model = fetch_result.materialize(reload=True)  # type: ignore
                instance_data = pydantic_model.model_dump()
                print(f"Instance data: ")
                print(json.dumps(instance_data, indent=2))
                self.process_desriptions.append(instance_data)
                print(f"Appended data for {iri}")
            except Exception as e:
                print(f"Error fetching data for {iri}: {e}")
                # Optional: continue or break

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
            # soll sich je Schraube die unscrewingOperations fetchen und dann mit den echten Daten lernen, welche Parameter zu welchen Ergebnissen führen.
            learned_parameters[screw] = {
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque"
                ).lined: [5.0],
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque"
                ).lined: [15.0],
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce"
                ).lined: [10.0],
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceApproach"
                ).lined: [0.5],
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach"
                ).lined: [0.2],
            }  # mocked data

        self.learned_parameters = learned_parameters

    def update_screwing_process_parameters(self, process_iri: IRI, parameters: dict):
        """updates the screwing process parameters in the graphdb with the learned parameters"""
        self.ogm.commit(instance_iri=process_iri, data=parameters, named_graph=IRI("http://w3id.org/circularfactory/UsecaseVerticalIntegrationInstances"))  # type: ignore #Todo für Etienne in KW 4
