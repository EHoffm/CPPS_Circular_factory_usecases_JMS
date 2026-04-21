from graph_db_interface import IRI, GraphDB, GraphDBCredentials
from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
import json
import pandas as pd


# GraphdbCredentials.from_env()


class TransformercellResource:
    def __init__(self):
        credentials = GraphDBCredentials.from_env()
        self.ogm = OGM(db=GraphDB(credentials=credentials), loader=None)

    def create_transformercell_instance(
        self,
        instance_iri: IRI,
        angle_grinder_iri: IRI,
        screwing_resource_iri: IRI,
        screw_iri: IRI,
        named_graph_iri: IRI,
    ):
        # Create the angle grinder and screwing resource instances if they don't exist yet
        try:
            self.ogm.create(
                instance_iri=angle_grinder_iri,
                class_iri=IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Anglegrinder"
                ),
                class_scope=ClassScope.from_property_chains(
                    [
                        [
                            IRI(
                                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPartScrew"
                            )
                        ]
                    ]
                ),
                data={
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPartScrew"
                    ): [{"id": screw_iri}]
                },
                persist=True,
                named_graph=named_graph_iri,
            )
            print(f"Created angle grinder instance: {angle_grinder_iri}")
        except Exception as e:
            print(f"Error creating angle grinder instance: {e}")

        try:
            self.ogm.create(
                instance_iri=screwing_resource_iri,
                class_iri=IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#ScrewingResource"
                ),
                class_scope=ClassScope.from_property_chains(
                    [
                        [
                            IRI(
                                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#isScrewingResourceOf"
                            )
                        ]
                    ]
                ),
                data={
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrewingResource"
                    ): []
                },
                persist=True,
                named_graph=named_graph_iri,
            )
            print(f"Created screwing resource instance: {screwing_resource_iri}")
        except Exception as e:
            print(f"Error creating screwing resource instance: {e}")

        # Define the class scope for the Transformercell instance
        transformercell_class_scope = ClassScope.from_property_chains(
            [
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrewingResource"
                    )
                ],
                [
                    IRI(
                        "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPossession"
                    )
                ],
            ],
        )

        # Data for the Transformercell instance, linking to the Anglegrinder and the ScrewingResource
        transformercell_data = {
            IRI(
                "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasScrewingResource"
            ): [
                {"id": screwing_resource_iri},
            ],
            IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#hasPossession"): [
                {"id": angle_grinder_iri},
            ],
        }

        try:
            # Try to create the Transformercell instance. If it already exists, catch the exception and print a message.
            self.ogm.create(
                instance_iri=instance_iri,
                class_iri=IRI(
                    "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#Transformercell"
                ),
                class_scope=transformercell_class_scope,
                data=transformercell_data,
                persist=True,
                named_graph=named_graph_iri,
            )
            print(f"Created/updated transformercell instance: {instance_iri}")
        except Exception as e:
            print(
                f"Transformercell instance {instance_iri} might already exist or error: {e}"
            )
