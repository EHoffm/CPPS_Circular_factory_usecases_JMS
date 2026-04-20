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

    def write_time_series_data_to_knowledge_graph(
        self,
        screw_type: IRI,
        instance_iri: IRI = IRI(
            "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingOperationDefaultInstance"
        ),
    ):
        named_graph_iri = IRI(
            "http://w3id.org/circularfactory/UsecaseVerticalIntegrationInstances"
        )
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

        # Create screw instance with properties if it doesn't exist
        screw_class_scope = ClassScope.from_property_chains(
            [
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque"
                    )
                ],
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque"
                    )
                ],
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce"
                    )
                ],
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach"
                    )
                ],
            ]
        )

        # Mock values for screw properties (in real implementation, these would come from a database or configuration)
        screw_data = {
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerTighteningTorque"
            ): [5.0],
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUpperDynamicLoseningTorque"
            ): [10.0],
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasLowerAxialForce"
            ): [2.0],
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPositionOnApproach"
            ): [0.0],
        }

        try:
            # Try to create/update the screw instance
            self.ogm.create(
                instance_iri=screw_type,
                class_iri=IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#screw"
                ),
                class_scope=screw_class_scope,
                data=screw_data,
                persist=True,
                named_graph=named_graph_iri,
            )
            print(f"Created/updated screw instance: {screw_type}")
        except Exception as e:
            print(f"Screw instance {screw_type} might already exist or error: {e}")

        fetched_instance = self.ogm.fetch(
            class_scope=screw_class_scope, instance_iri=screw_type
        )  # type: ignore TODO: class_scope.from_property_chains(prop_chains)
        # pydantic_model = fetched_instance.materialize()
        # serialized = pydantic_model.model_dump()
        # print("Fetched screw type data:")
        # print(json.dumps(serialized, indent=2))  # Pretty-print the fetched screw type

        # TODO: MG: Hier mocken wir zeitreihen Daten. In der echten Implementierung würde hier eine transformerzelle angesteuert
        # die zeitreihen werden dann im KG Abgelegt
        # simulates a screwing process and randomly generates a result data structure
        result = {}
        # data: {hasScrew: screw_type,
        #    hasunscrewingTorqueTimeSeriesData: [...],
        #    hasAxialForceTimeSeriesData: [...]}
        pdData = pd.read_csv(f"unscrewing_timeseries/{screw_types[screw_type]}.csv")
        unscrewing_torque_time_series = pdData[
            "UnscrewingTorque"
        ].to_list()  # TODO: das hier muss noch als daten in TimeSeriesData Instanz
        axial_force_time_series = pdData["AxialForce"].to_list()
        robot_position_time_series = pdData["RobotPosition"].to_list()

        # Create the 3 new TimeSeriesData instances and persist it to the knowledge graph
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
        timeSeriesInstanceTorque = self.ogm.create(
            instance_iri=IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingTorqueTimeSeriesDataInstance1"
            ),
            class_iri=time_series_iri,
            class_scope=time_series_scope,
            data={
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                ): [json.dumps(unscrewing_torque_time_series)],
            },
            persist=True,
            named_graph=named_graph_iri,
        )

        timeSeriesInstanceAxialForce = self.ogm.create(
            instance_iri=IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#AxialForceTimeSeriesDataInstance1"
            ),
            class_iri=time_series_iri,
            class_scope=time_series_scope,
            data={
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                ): [json.dumps(axial_force_time_series)],
            },
            persist=True,
            named_graph=named_graph_iri,
        )

        timeSeriesInstancePosition = self.ogm.create(
            instance_iri=IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#RobotPositionTimeSeriesDataInstance1"
            ),
            class_iri=time_series_iri,
            class_scope=time_series_scope,
            data={
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasJSONEncodedTimeSeriesData"
                ): [json.dumps(robot_position_time_series)],
            },
            persist=True,
            named_graph=named_graph_iri,
        )
        fetched_instance = self.ogm.fetch(
            class_scope=time_series_scope,
            instance_iri=IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#RobotPositionTimeSeriesDataInstance1"
            ),
        )
        pydantic_model = fetched_instance.materialize()  # TEST
        serialized = pydantic_model.model_dump()
        print("Fetched robot position time series data:")
        print(json.dumps(serialized, indent=2))

        # Data for the unscrewing operation instance, linking to the screw type and the time series data
        property_chains = [
            [IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew")],
            [IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasResource")],
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
            [
                IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus"
                )
            ],
        ]
        unscrewing_operation_scope = ClassScope.from_property_chains(property_chains)
        data = {
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrew"): [
                {"id": screw_type}
            ],
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasResource"): [
                {
                    "id": IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#ScrewingResource_1"
                    )
                }
            ],
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasUnscrewingTorqueTimeSeriesData"
            ): [
                {
                    "id": IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#UnscrewingTorqueTimeSeriesDataInstance1"
                    )
                }
            ],
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasAxialForceTimeSeriesData"
            ): [
                {
                    "id": IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#AxialForceTimeSeriesDataInstance1"
                    )
                }
            ],
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasRobotPositionTimeSeriesData"
            ): [
                {
                    "id": IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#RobotPositionTimeSeriesDataInstance1"
                    )
                }
            ],
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasSuccessStatus"
            ): [
                "unknown"
            ],  # Placeholder, to be updated by anomaly detector after analysis
        }

        # TODO: hier bitte instance_iri anpassen, wenn nicht mehr fest eine instanz in der demo genutzt wird
        # oder wenn noch geprüft wird, ob die instance_iri so schon existiert
        self.ogm.create(
            instance_iri=instance_iri,
            class_iri=IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#unscrewingOperation"
            ),
            class_scope=unscrewing_operation_scope,
            data=data,
            persist=True,
            named_graph=named_graph_iri,
        )
