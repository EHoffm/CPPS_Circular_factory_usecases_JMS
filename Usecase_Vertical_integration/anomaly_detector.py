from graph_db_interface import GraphDB, IRI
from kapps_ogm import ClassScope, OGM
import json
import requests

# GraphdbCredentials.from_env()

DB_HOST = "127.0.0.1"
DB_PORT = 5050
DB_BASE_URL = f"http://{DB_HOST}:{DB_PORT}"
JMS_Usecase_Demo = "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#"


class AnomalyDetector:

    def __init__(self, threshold: float):
        self.threshold = threshold

        self.ogm = OGM(db=GraphDB.from_env())

    def fetch_process_model(self, instance_iri: IRI):
        """retrieves Time Series Data of an unscrewing process as a node via OGM.fetch(), processes well known json format, returns Time Serias as
        preferred Data Structure (e.g. list of floats)
        """
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

        class_scope = ClassScope.from_property_chains(property_chains)
        fetched_instance = self.ogm.fetch(
            class_scope=class_scope,
            instance_iri=instance_iri,
            materialize=True,
        ).instance

        return fetched_instance.model_dump()

    def fetch_screw_type_parameters(self, screw_type_iri: IRI):
        property_chains = [
            [
                IRI(f"{JMS_Usecase_Demo}hasLowerTighteningTorque"),
            ],
            [
                IRI(f"{JMS_Usecase_Demo}hasUpperDynamicLoseningTorque"),
            ],
            [
                IRI(f"{JMS_Usecase_Demo}hasLowerAxialForce"),
            ],
            [
                IRI(f"{JMS_Usecase_Demo}hasAxialForceApproach"),
            ],
        ]

        class_scope = ClassScope.from_property_chains(property_chains)

        screw_type_instance = self.ogm.fetch(
            class_scope=class_scope,
            instance_iri=screw_type_iri,
            materialize=True,
        ).instance

        lower_tightening_torque = getattr(
            screw_type_instance,
            IRI(f"{JMS_Usecase_Demo}hasLowerTighteningTorque").lined,
        )[0]
        hasUpperDynamicLoseningTorque = getattr(
            screw_type_instance,
            IRI(f"{JMS_Usecase_Demo}hasUpperDynamicLoseningTorque").lined,
        )[0]
        hasLowerAxialForce = getattr(
            screw_type_instance,
            IRI(f"{JMS_Usecase_Demo}hasLowerAxialForce").lined,
        )[0]
        hasAxialForceApproach = getattr(
            screw_type_instance,
            IRI(f"{JMS_Usecase_Demo}hasAxialForceApproach").lined,
        )[0]

        return (
            lower_tightening_torque,
            hasUpperDynamicLoseningTorque,
            hasLowerAxialForce,
            hasAxialForceApproach,
        )

    def detect_anomaly(self, data: dict) -> dict:
        """processes fetched data, detects anomalies, returns annotated data structure
        This is a mocked implementation - in a real implementation, the time series data is from the robot control directly and not from the knowledge graph
        """
        has_screw = IRI(f"{JMS_Usecase_Demo}hasScrew").lined
        screw_type = data[has_screw][0]["id"]

        (
            lower_tightening_torque,
            hasUpperDynamicLoseningTorque,
            hasLowerAxialForce,
            hasAxialForceApproach,
        ) = self.fetch_screw_type_parameters(screw_type)

        url_to_torque = data[
            IRI(f"{JMS_Usecase_Demo}hasUnscrewingTorqueTimeSeriesData").lined
        ][0][IRI(f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData").lined][0]
        url_to_force = data[
            IRI(f"{JMS_Usecase_Demo}hasAxialForceTimeSeriesData").lined
        ][0][IRI(f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData").lined][0]
        url_to_position = data[
            IRI(f"{JMS_Usecase_Demo}hasRobotPositionTimeSeriesData").lined
        ][0][IRI(f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData").lined][0]

        torque_series = requests.get(url_to_torque).json()
        force_series = requests.get(url_to_force).json()
        position_series = requests.get(url_to_position).json()

        # Anomaly detection logic
        # iterate over unscrewing_torque_time_series and axial_force_time_series and position time series simultaneously
        # first check while position > position_on_approach: axial_force < hasAxialForceApproach ; else: Suceess_state = "Occluded Screw"
        # then
        # then check if the unscrewing_torque > lower_tightening_torque. else: Success_state = "Rounded Head"
        # then check if axial_force > lower_axial_force
        # then check if unscrewing_torque < hasUpperDynamicLoseningTorque

        data[IRI(f"{JMS_Usecase_Demo}hasSuccessStatus")] = ["Successful"]

        print(
            f"{'='*70}\n"
            f"  Fetched Parameters for {screw_type.fragment} ({screw_type})\n"
            f"    Lower Tightening Torque:       {lower_tightening_torque}\n"
            f"    Upper Dynamic Losening Torque: {hasUpperDynamicLoseningTorque}\n"
            f"    Lower Axial Force:             {hasLowerAxialForce}\n"
            f"    Axial Force Approach:          {hasAxialForceApproach}\n"
            f"  Fetched Time Series Data\n"
            f"    Unscrewing Torque: {torque_series}\n"
            f"    Axial Force:       {force_series}\n"
            f"    Robot Position:    {position_series}\n"
            f"{'='*70}\n"
            f"  Performing Anomaly Detection Logic...\n"
            f"    Success Status: {data[IRI(f"{JMS_Usecase_Demo}hasSuccessStatus")][0]}\n"
        )

        return data

    def update_instance(self, instance_iri: IRI, data: dict):
        """updates the instance in the graphdb with the annotated data"""
        self.ogm.commit(
            instance_iri=instance_iri,
            data=data,
        )
