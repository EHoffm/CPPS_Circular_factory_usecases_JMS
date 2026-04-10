import importlib


def __getattr__(name: str):
    if name == "MockWMS":
        return importlib.import_module("mock_wms.MockWMS").MockWMS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
