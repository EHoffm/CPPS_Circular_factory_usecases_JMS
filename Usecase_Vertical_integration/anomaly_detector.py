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

    def fetch_process_model(self, instance_iri: IRI) -> dict:
        """retrieves Time Series Data of an unscrewing process as a node via OGM.fetch(), processes well known json format, returns Time Serias as
        preferred Data Structure (e.g. list of floats)
        """

        property_chains = [
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
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData"
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
        ]

        class_scope = ClassScope.from_property_chains(property_chains)  # type: ignore
        fetched_instance = self.ogm.fetch(
            class_scope=class_scope,
            instance_iri=instance_iri,
        )
        print("Fetched instance for anomaly detection:")
        print(
            fetched_instance
        )  # This will print the raw fetched instance, which may include nested structures and IRIs
        pydantic_model = fetched_instance.materialize(reload=True)  # type: ignore
        serialized = pydantic_model.model_dump()
        print("Fetched data for anomaly detection:")
        print(json.dumps(serialized, indent=2))

        return serialized

    def detect_anomaly(self, data: dict) -> dict:
        """processes fetched data, detects anomalies, returns annotated data structure
        This is a mocked implementation - in a real implementation, the time series data is from the robot control directly and not from the knowledge graph
        """
        # TODO MG: Hier implementieren wir die Anomalieerkennung Logik
        # Parameters for the anomaly detection, to check features of the time series data - learned in learner.py

        hasScrew_iri_lined = IRI(
            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"
        ).lined
        lower_tightening_torque = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque').lined}"
        ]  # double, Indicates the minimum torque required to properly tighten the screw - to check if torque can be applied to it.

        hasUpperDynamicLoseningTorque = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque').lined}"
        ]  # double, Specifies the maximum torque at which the screw may loosen during unscrewing
        hasLowerAxialForce = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce').lined}"
        ]  # double; minimum axial force that indicates the screw moving towards the screwdriver
        hasSuccessStatus = data[
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus').lined}"
        ]  # "Successfull" or "Loose Anchor" or Rounded Head" or ...
        # TODO: Max fragen, ob das drin sein muss
        # hasAxialForceApproach = data[
        #    f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceApproach').lined}"
        # ]  # double; The axial force measured while the screwdriver approaches the screw head.
        hasPositionOnApproach = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach').lined}"
        ]  # double; The position along the screw axis when approaching the screw

        # TODO: hier ändern und neu setzen von hasSuccessStatus oder soll das den Zustand wiederspiegeln?
        data[
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus').lined}"
        ] = ["Successful"]

        # mocked Timeseries, in this case from knwoledge graph - in real implementation from robot control
        unscrewing_torque_time_series_string = str(
            data[
                f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData').lined}"
            ][0][
                f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData').lined}"
            ][
                0
            ]
        )
        unscrewing_torque_time_series = json.loads(unscrewing_torque_time_series_string)
        axial_force_time_series_string = data[
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData').lined}"
        ][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData').lined}"
        ][
            0
        ]

        axial_force_time_series = json.loads(axial_force_time_series_string)

        # Anomaly detection logic
        # iterate over unscrewing_torque_time_series and axial_force_time_series and position time series simultaneously
        # first check while position > position_on_approach: axial_force < hasAxialForceApproach ; else: Suceess_state = "Occluded Screw"
        # then
        # then check if the unscrewing_torque > lower_tightening_torque. else: Success_state = "Rounded Head"
        # then check if axial_force > lower_axial_force
        # then check if unscrewing_torque < hasUpperDynamicLoseningTorque

        return data

    def update_instance(
        self,
        instance_iri: IRI,
        data: dict,
        named_graph_iri: IRI = IRI(
            "http://w3id.org/circularfactory/UsecaseVerticalIntegrationInstances"
        ),
    ):
        """updates the instance in the graphdb with the annotated data"""
        self.ogm.commit(instance_iri=instance_iri, data=data, named_graph=named_graph_iri)  # type: ignore #Todo für Etienne in KW 4
