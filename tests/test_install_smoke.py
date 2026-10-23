import importlib
from importlib.resources import files

import pytest

from Usecase_Vertical_integration import db


def test_vertical_integration_time_series_is_packaged() -> None:
    asset = files("Usecase_Vertical_integration").joinpath(
        "unscrewing_timeseries", "success.csv"
    )

    assert asset.is_file()
    assert not db.get_pd_series("success", "UnscrewingTorque").empty


@pytest.mark.parametrize(
    "module_name",
    [
        "Usecase_Vertical_integration.demo",
        "Usecase_FlexConveyor_decentral.src.FlexConveyor_Module.FlexConveyorModule",
        "Usecase_FlexConveyor_decentral.src.Mock_WMS.MockWMS",
        "Usecase_FlexConveyor_decentral.src.Visualizer.utils.bootstrap",
        "Usecase_FlexConveyor_decentral.src.Visualizer.utils.control",
        "Usecase_FlexConveyor_decentral.src.Visualizer.utils.live_monitor",
    ],
)
def test_supported_modules_import(module_name: str) -> None:
    importlib.import_module(module_name)