import random
import threading
from urllib.parse import quote
from flask import Flask, request, jsonify, Response
import uuid

import pandas as pd

JMS_Usecase_Demo = "https://sfb1574.kit.edu/ontologies/JMS_Usecase_Demo#"

_MOCK_TIME_FRAMES = [
    "success",
    "missing_screw",
]

_TRACKED_REFERENCES = {}

app = Flask(__name__)


def get_pd_series(frame: str, series: str) -> pd.Series:
    pdData = pd.read_csv(
        f"Usecase_Vertical_integration/unscrewing_timeseries/{frame}.csv"
    )
    return pdData[series]


@app.route("/get_reference_to_time_frame", methods=["GET"])
def get_reference_to_time_frame() -> Response:
    # create, track and return a reference to a time frame
    # mock only chooses from a set of prerecorded time frames
    frame = random.choice(_MOCK_TIME_FRAMES)
    reference = f"time_frame_{uuid.uuid4()}"
    _TRACKED_REFERENCES[reference] = frame
    base_url = (
        f"{request.host_url.rstrip('/')}/get_time_series?reference={reference}&series="
    )
    url_to_torque = base_url + "UnscrewingTorque"
    url_to_force = base_url + "AxialForce"
    url_to_position = base_url + "RobotPosition"

    return jsonify((url_to_torque, url_to_force, url_to_position))


@app.route("/get_time_series", methods=["GET"])
def get_time_series() -> Response:
    reference = request.args.get("reference", "")
    series = request.args.get("series", "")
    if reference not in _TRACKED_REFERENCES:
        return jsonify({"error": f"Unknown reference: {reference}"}), 404
    frame = _TRACKED_REFERENCES[reference]
    data = get_pd_series(frame, series)
    return jsonify(data.to_list())


def start(host: str = "127.0.0.1", port: int = 5050) -> None:
    """Start the mock InfluxDB server in a background daemon thread."""
    thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, use_reloader=False),
        daemon=True,
    )
    thread.start()
