from graph_db_interface import GraphDB, GraphDBCredentials, IRI
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
import json


# GraphdbCredentials.from_env()


class AnomalyDetector:
    def __init__(self, threshold: float):
        credentials = GraphDBCredentials.from_env()
        self.threshold = threshold
        self.ogm = OGM(db=GraphDB(credentials=credentials), loader=None)

    def fetch_process_model(self, instance_iri: IRI):
        """retrieves Time Series Data of an unscrewing process as a node via OGM.fetch(), processes well known json format, returns Time Serias as
        preferred Data Structure (e.g. list of floats)
        """
        property_chains = [
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
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus"
                ),
            ],
        ]

        class_scope = ClassScope.from_property_chains(property_chains)  # type: ignore
        fetched_instance = self.ogm.fetch(class_scope, instance_iri=instance_iri).instance  # type: ignore TODO: class_scope.from_property_chains(prop_chains)

        return fetched_instance.model_dump()

    def detect_anomaly(self, data: dict) -> dict:
        """processes fetched data, detects anomalies, returns annotated data structure
        This is a mocked implementation - in a real implementation, the time series data is from the robot control directly and not from the knowledge graph
        """
        # TODO MG: Hier implementieren wir die Anomalieerkennung Logik
        # Parameters for the anomaly detection, to check features of the time series data - learned in learner.py
        lower_tightening_torque = data[
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque"
            )
        ]  # double, Indicates the minimum torque required to properly tighten the screw - to check if torque can be applied to it.
        hasUpperDynamicLoseningTorque = data[
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque"
            )
        ]  # double, Specifies the maximum torque at which the screw may loosen during unscrewing
        hasLowerAxialForce = data[
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce"
            )
        ]  # double; minimum axial force that indicates the screw moving towards the screwdriver
        hasSuccessStatus = data[
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus")
        ]  # "Successfull" or "Loose Anchor" or Rounded Head" or ...
        hasAxialForceApproach = data[
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceApproach"
            )
        ]  # double; The axial force measured while the screwdriver approaches the screw head.
        hasPositionOnApproach = data[
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach"
            )
        ]  # double; The position along the screw axis when approaching the screw

        data[
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus")
        ] = "Successful"

        # mocked Timeseries, in this case from knwoledge graph - in real implementation from robot control
        unscrewing_torque_time_series = json.loads(
            data[
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData"
                )
            ][
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                )
            ]
        )
        axial_force_time_series = json.loads(
            data[
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData"
                )
            ][
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                )
            ]
        )

        # Anomaly detection logic
        # iterate over unscrewing_torque_time_series and axial_force_time_series and position time series simultaneously
        # first check while position > position_on_approach: axial_force < hasAxialForceApproach ; else: Suceess_state = "Occluded Screw"
        # then
        # then check if the unscrewing_torque > lower_tightening_torque. else: Success_state = "Rounded Head"
        # then check if axial_force > lower_axial_force
        # then check if unscrewing_torque < hasUpperDynamicLoseningTorque

        return data

    def update_instance(self, instance_iri: IRI, data: dict):
        """updates the instance in the graphdb with the annotated data"""
        self.ogm.commit(instance_iri, data, persist=True)  # type: ignore #Todo für Etienne in KW 4
