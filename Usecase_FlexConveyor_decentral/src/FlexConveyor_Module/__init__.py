import importlib


def __getattr__(name: str):
	if name == "FlexConveyor":
		return importlib.import_module(
			"FlexConveyor_Module.FlexConveyorModule"
		).FlexConveyor
	if name == "build_adjacency_matrix":
		return importlib.import_module(
			"FlexConveyor_Module.adjacency_matrix"
		).build_adjacency_matrix
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
