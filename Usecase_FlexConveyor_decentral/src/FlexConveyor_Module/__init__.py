import importlib


def __getattr__(name: str):
	if name == "FlexConveyor":
		return importlib.import_module(
			"FlexConveyor_Module.FlexConveyorModule"
		).FlexConveyor
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
