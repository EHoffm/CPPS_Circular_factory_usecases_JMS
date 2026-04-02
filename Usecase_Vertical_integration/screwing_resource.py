from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
import json
import pandas as pd


# GraphdbCredentials.from_env()


class ScrewingResource:
    def __init__(self):
        credentials = GraphDBCredentials.from_env()
        self.ogm = OGM(db=GraphDB(credentials=credentials), loader=None)

    def write_time_series_data_to_knowledge_graph(self, screw_type: IRI):
        # Hinweis die values success und missing_screw werden hier aktuell nicht genutzt
        screw_types = {
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M3_Screw"
            ): "success",
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M4_Screw"
            ): "missing_screw",
            # IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M5_Screw"): "M5_Screw",
        }
        if screw_type in screw_types:
            screw_types = {screw_type: screw_types[screw_type]}

        for i, screw in enumerate(
            screw_types
        ):  # TODO: MG: Hier mocken wir zeitreihen Daten. In der echten Implementierung würde hier eine transformerzelle angesteuert
            # die zeitreihen werden dann im KG Abgelegt
            # simulates a screwing process and randomly generates a result data structure
            result = {}
            # data: {hasScrew: screw_type,
            #    hasunscrewingTorqueTimeSeriesData: [...],
            #    hasAxialForceTimeSeriesData: [...]}
            pdData = pd.read_csv(f"unscrewing_timeseries/{screw_types[screw]}.csv")
            unscrewing_torque_time_series = pdData[
                "UnscrewingTorque"
            ].to_list()  # TODO: das hier muss noch als daten in TimeSeriesData Instanz
            axial_force_time_series = pdData["AxialForce"].to_list()
            robot_position_time_series = pdData["RobotPosition"].to_list()

            named_graph_iri = IRI(
                "http://w3id.org/circularfactory/UsecaseVerticalIntegrationInstances"
            )

            # Create the new TimeSeriesData instances and persist it to the knowledge graph
            time_series_scope = ClassScope.from_property_chains(
                [
                    [
                        IRI(
                            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                        )
                    ]
                ]
            )
            time_series_iri = IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#TimeSeriesData"
            )
            temp_timeSeriesInstance = self.ogm.create(
                class_iri=time_series_iri,
                class_scope=time_series_scope,
                data={
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                    ): [str(unscrewing_torque_time_series)],
                },
                persist=True,
                named_graph=named_graph_iri,
            )
            unscrewing_torque_time_series_iri = temp_timeSeriesInstance.id

            temp_timeSeriesInstance = self.ogm.create(
                class_iri=time_series_iri,
                class_scope=time_series_scope,
                data={
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                    ): [str(axial_force_time_series)],
                },
                persist=True,
                named_graph=named_graph_iri,
            )
            axial_force_time_series_iri = temp_timeSeriesInstance.id

            temp_timeSeriesInstance = self.ogm.create(
                class_iri=time_series_iri,
                class_scope=time_series_scope,
                data={
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                    ): [str(robot_position_time_series)],
                },
                persist=True,
                named_graph=named_graph_iri,
            )
            robot_position_time_series_iri = temp_timeSeriesInstance.id

            # Data for the unscrewing operation instance, linking to the screw type and the time series data
            property_chains = [
                [IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew")],
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData"
                    )
                ],
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData"
                    )
                ],
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasRobotPositionTimeSeriesData"
                    )
                ],
            ]
            unscrewing_operation_scope = ClassScope.from_property_chains(
                property_chains
            )
            data = {
                IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"): [
                    {"id": screw}
                ],
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData"
                ): [{"id": unscrewing_torque_time_series_iri}],
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData"
                ): [{"id": axial_force_time_series_iri}],
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasRobotPositionTimeSeriesData"
                ): [{"id": robot_position_time_series_iri}],
            }

            # TODO: hier bitte instance_iri anpassen, wenn nicht mehr fest eine instanz in der demo genutzt wird
            # oder wenn noch geprüft wird, ob die instance_iri so schon existiert
            self.ogm.create(
                instance_iri=IRI(
                    f"https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingOperation{i+1}"
                ),
                class_iri=IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#unscrewingOperation"
                ),
                class_scope=unscrewing_operation_scope,
                data=data,
                persist=True,
                named_graph=named_graph_iri,
            )
