import json
import time
from dotenv import load_dotenv
from graph_db_interface import IRI

from . import db
from .anomaly_detector import AnomalyDetector
from .learner import Learner
from .screwing_resource import ScrewingResource

DB_HOST = "127.0.0.1"
DB_PORT = 5050
DB_BASE_URL = f"http://{DB_HOST}:{DB_PORT}"
JMS_Usecase_Demo = "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#"


def main():
    print(load_dotenv())  # Call this at the start of your script

    db.start(host=DB_HOST, port=DB_PORT)
    time.sleep(0.5)  # give the server a moment to bind

    screwing_resource = ScrewingResource()
    anomaly_detector = AnomalyDetector(threshold=0.1)
    learner = Learner()

    # # --- Demo calls to mock InfluxDB endpoints ---

    # url_to_torque, url_to_force, url_to_position = requests.get(
    #     f"{DB_BASE_URL}/get_reference_to_time_series"
    # ).json()
    # print(f"torque -> {url_to_torque!r}")
    # print(f"force -> {url_to_force!r}")
    # print(f"position -> {url_to_position!r}")

    # series = requests.get(url_to_torque).json()
    # print(f"get({url_to_torque!r}) -> {series}")

    # series = requests.get(url_to_force).json()
    # print(f"get({url_to_force!r}) -> {series}")

    # series = requests.get(url_to_position).json()
    # print(f"get({url_to_position!r}) -> {series}")

    # Example usage:
    screw_type = IRI("https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#M4_Screw")

    operation_instance_iri = (
        screwing_resource.write_time_series_data_to_knowledge_graph(screw_type)
    )
    print(f"Persisted process instance: {operation_instance_iri}")

    fetched_data = anomaly_detector.fetch_process_model(operation_instance_iri)
    print(
        f"Fetched data for process instance {operation_instance_iri}:\n{json.dumps(fetched_data, indent=2)}"
    )

    annotated_data = anomaly_detector.detect_anomaly(fetched_data)
    anomaly_detector.update_instance(operation_instance_iri, annotated_data)
    # late at night, the learner awakes. he picks one specific screw type and learns from all process descriptions
    learner.get_all_process_descriptions()
    learner.learn_from_process_descriptions()
    for screw_type, params in learner.learned_parameters.items():
        learner.update_screwing_process_parameters(screw_type, params)


if __name__ == "__main__":
    main()
