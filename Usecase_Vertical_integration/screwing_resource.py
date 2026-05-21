from graph_db_interface import IRI, GraphDB
from kapps_ogm.ogm import OGM, ClassScope
import requests

# GraphdbCredentials.from_env()

DB_HOST = "127.0.0.1"
DB_PORT = 5050
DB_BASE_URL = f"http://{DB_HOST}:{DB_PORT}"
JMS_Usecase_Demo = "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#"


class ScrewingResource:
    def __init__(self):
        self.ogm = OGM(db=GraphDB.from_env())

    def write_time_series_data_to_knowledge_graph(self, screw_type: IRI) -> IRI:
        url_to_torque, url_to_force, url_to_position = requests.get(
            f"{DB_BASE_URL}/get_reference_to_time_frame"
        ).json()

        data = {
            f"{JMS_Usecase_Demo}hasScrew": [{"id": screw_type}],
            f"{JMS_Usecase_Demo}hasUnscrewingTorqueTimeSeriesData": [
                {f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData": [url_to_torque]}
            ],
            f"{JMS_Usecase_Demo}hasAxialForceTimeSeriesData": [
                {f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData": [url_to_force]}
            ],
            f"{JMS_Usecase_Demo}hasRobotPositionTimeSeriesData": [
                {f"{JMS_Usecase_Demo}hasJSONEncodedTimeSeriesData": [url_to_position]}
            ],
        }
        process_instance = self.ogm.create(
            class_iri=IRI(f"{JMS_Usecase_Demo}unscrewingOperation"),
            class_scope=ClassScope.from_data_dict(data),
            data=data,
            persist=True,
        )
        process_instance_iri = process_instance.id
        return process_instance_iri
