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
        Possible status values: "Occluded Screw" "Missing Screw", "Rounded Head", "Stuck Screw", "Finished or Failed", "Successful"
        """
        # TODO MG: Hier implementieren wir die Anomalieerkennung Logik
        # Parameters for the anomaly detection, to check features of the time series data - learned in learner.py
        hasScrew_iri_lined = IRI(
            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"
        ).lined

        # here the comparison values for the screw type are saved in variables, to use in the decision tree
        lower_tightening_torque = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque').lined}"
        ][
            0
        ]  # double, Indicates the minimum torque required to properly tighten the screw - to check if torque can be applied to it.
        hasUpperDynamicLoseningTorque = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque').lined}"
        ][
            0
        ]  # double, Specifies the maximum torque at which the screw may loosen during unscrewing
        hasLowerAxialForce = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce').lined}"
        ][
            0
        ]  # double; minimum axial force that indicates the screw moving towards the screwdriver
        hasAxialForceApproach = data[
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceApproach').lined}"
        ]  # double; The axial force measured while the screwdriver approaches the screw head.
        hasPositionOnApproach = data[f"{hasScrew_iri_lined}"][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach').lined}"
        ][
            0
        ]  # double; The position along the screw axis when approaching the screw
        print(f"lower tightening torque: {lower_tightening_torque}")
        print(f"upper dynamic losening torque: {hasUpperDynamicLoseningTorque}")
        print(f"lower axial force: {hasLowerAxialForce}")
        print(f"position on approach: {hasPositionOnApproach}")
        print(f"axial force approach: {hasAxialForceApproach}")

        # TODO: entweder Vergleichswerte der Schraube oder success_process Daten anpassen
        # für den moment hier die Vergleichswerte der Schraube nur für diese Funktion angepasst
        lower_tightening_torque = 1.0
        hasLowerAxialForce = 0.5

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

        axial_force_time_series_string = data[
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData').lined}"
        ][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData').lined}"
        ][
            0
        ]
        approach_position_time_series_string = data[
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach').lined}"
        ][0][
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData').lined}"
        ][
            0
        ]
        # lists with the data from the unscrewing process
        unscrewing_torque_time_series = json.loads(unscrewing_torque_time_series_string)
        axial_force_time_series = json.loads(axial_force_time_series_string)
        approach_position_time_series = json.loads(approach_position_time_series_string)

        # Anomaly detection logic
        # iterate over unscrewing_torque_time_series and axial_force_time_series and position time series simultaneously
        # first check while position > position_on_approach: axial_force < hasAxialForceApproach ; else: Suceess_state = "Occluded Screw"
        # then
        # then check if the unscrewing_torque > lower_tightening_torque. else: Success_state = "Rounded Head"
        # then check if axial_force > lower_axial_force
        # then check if unscrewing_torque < hasUpperDynamicLoseningTorque
        # Decision tree for anomaly detection during the unscrewing process.

        # The three time series are assumed to be synchronized, i.e. each index represents the same time step.

        # Default status, will be overwritten as soon as an anomaly is detected
        status = "Successful"

        # Basic validation: all time series must have the same length
        if not (
            len(unscrewing_torque_time_series)
            == len(axial_force_time_series)
            == len(approach_position_time_series)
        ):
            raise ValueError(
                "Unscrewing torque, axial force, and position time series must have the same length."
            )

        # Flags to keep track of the process state
        approach_finished = False  # True once the screwdriver has reached the screw head, i.e. position_value <= hasPositionOnApproach
        screw_detected = False  # True once a screw is considered present, i.e. axial_force_value >= hasLowerAxialForce after approach_finished
        torque_applied = False  # True once sufficient torque is applied, i.e. abs(torque_value) >= lower_tightening_torque after screw detection
        disassembly_started = False  # True once unscrewing has started, i.e. torque_value < 0 after torque_applied
        disassembly_finished = False  # True once the screw has been removed and the tool retracts, i.e. disassembly_started and position_value > hasPositionOnApproach and axial_force_value == 0 and torque_value == 0

        for torque_value, axial_force_value, position_value in zip(
            unscrewing_torque_time_series,
            axial_force_time_series,
            approach_position_time_series,
        ):
            # ------------------------------------------------------------
            # 1) Approach phase
            # ------------------------------------------------------------
            # During approach, an occluded screw can be detected.
            # The original text requires a dedicated approach force threshold.
            # This value is currently not available in your variables.
            # Therefore, hasLowerAxialForce is used here as an approximation.
            # This does NOT exactly match the text.
            if not approach_finished:
                if position_value > hasPositionOnApproach:
                    if axial_force_value > hasLowerAxialForce:
                        status = "Occluded Screw"
                        break
                    continue
                else:
                    # The screwdriver has reached the screw head.
                    approach_finished = True

            # ------------------------------------------------------------
            # 2) Screw presence check
            # ------------------------------------------------------------
            # After approach is finished, check whether a screw is present.
            # If the axial force does not reach the lower threshold, the screw is missing.
            if approach_finished and not screw_detected:
                if axial_force_value < hasLowerAxialForce:
                    status = "Missing Screw"
                    break
                screw_detected = True

            # ------------------------------------------------------------
            # 3) Check whether torque can be applied
            # ------------------------------------------------------------
            # If the screw is present but sufficient torque cannot be transmitted,
            # the screw head is considered rounded.
            #
            # Important mismatch with the text:
            # The text excerpt mentions an example lower torque threshold of 0.1 Nm.
            # Your KG value lower_tightening_torque may differ, e.g. 5.0.
            # This implementation uses YOUR KG value.
            if screw_detected and not torque_applied:
                if abs(torque_value) < lower_tightening_torque:
                    # Still allow the loop to continue until torque is actually attempted.
                    # A rounded head should only be decided once torque application is expected.
                    if torque_value != 0:
                        status = "Rounded Head"
                        break
                else:
                    torque_applied = True

            # ------------------------------------------------------------
            # 4) Preparation / unscrewing starts
            # ------------------------------------------------------------
            # In your example, negative torque indicates unscrewing direction.
            if torque_applied and not disassembly_started:
                if torque_value < 0:
                    disassembly_started = True

            # ------------------------------------------------------------
            # 5) Monitor disassembly process
            # ------------------------------------------------------------
            if disassembly_started:
                # If the torque exceeds the upper threshold, the screw is stuck.
                if abs(torque_value) >= hasUpperDynamicLoseningTorque:
                    status = "Stuck Screw"
                    break

                # Successful removal / retract condition based on your example data.
                if (
                    position_value > hasPositionOnApproach
                    and axial_force_value == 0
                    and torque_value == 0
                ):
                    disassembly_finished = True
                    status = "Successful"
                    break
        # Save the detected status back into the data structure
        data[
            f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus').lined}"
        ] = [status]

        print(
            "Detected unscrewing status:",
            data[
                f"{IRI('https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus').lined}"
            ][0],
        )

        return data

    def updateUnscrewingOperationviaProfiNet(
        self,
        instance_iri: IRI,
        data: dict,
        named_graph_iri: IRI = IRI(
            "http://w3id.org/circularfactory/UsecaseVerticalIntegrationInstances"
        ),
    ):
        """updates the instance in the graphdb with the annotated data"""
        self.ogm.commit(instance_iri=instance_iri, data=data, named_graph=named_graph_iri)  # type: ignore #Todo für Etienne in KW 4
