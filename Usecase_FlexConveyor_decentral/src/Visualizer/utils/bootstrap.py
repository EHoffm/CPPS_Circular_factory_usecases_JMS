"""Bootstrap utilities for instantiating FlexConveyor modules into the knowledge base."""

import json
import sys
import os
import importlib
import time
import atexit
import signal
import threading
from typing import Any, List, Optional

from graph_db_interface.utils.iri import IRI
from kapps_ogm import OGM
from kapps_ogm import ClassScope
import aas_middleware as aas


_running_modules: list[Any] = []
_running_modules_lock = threading.Lock()
_shutdown_hooks_registered = False


def register_shutdown_handlers() -> None:
    """Register process-level shutdown handlers to stop all running modules."""
    global _shutdown_hooks_registered
    if _shutdown_hooks_registered:
        return

    atexit.register(stop_all_modules)

    def _signal_handler(signum: int, _frame: Optional[Any]) -> None:
        print(f"\n🛑 Received signal {signum}. Stopping all FlexConveyor modules...")
        stop_all_modules()
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except ValueError:
        pass

    _shutdown_hooks_registered = True


def stop_all_modules() -> int:
    """Stop all running FlexConveyor modules tracked by the bootstrap utility."""
    with _running_modules_lock:
        modules_to_stop = list(_running_modules)
        _running_modules.clear()

    if not modules_to_stop:
        return 0

    print("\n" + "=" * 70)
    print("🧹 Stopping FlexConveyor modules")
    print("=" * 70)

    stopped_count = 0
    for module in reversed(modules_to_stop):
        module_id = getattr(module, "module_id", "unknown")
        try:
            module.stop()
            stopped_count += 1
        except Exception as stop_error:
            print(f"✗ Error stopping module {module_id}: {stop_error}")

    print(f"Stopped modules: {stopped_count}/{len(modules_to_stop)}")
    print("=" * 70 + "\n")
    return stopped_count


# Object properties whose values must be {"id": "..."} dicts, not plain strings.
# OGM's Node expects object-property values to be dicts so it can convert them
# into Node references.  The JSON exported by the GUI stores them as bare IRI
# strings, so we wrap them here before handing data to ogm.create().
_OBJECT_PROPERTY_FRAGMENTS = {"connectsTo", "hasDirection", "hasPossession", "hasService"}


def _is_object_property_key(key: str) -> bool:
    """Check if a JSON key corresponds to an OWL object property."""
    for fragment in _OBJECT_PROPERTY_FRAGMENTS:
        if fragment.lower() in key.lower():
            return True
    return False


def _wrap_literal_iris_as_nodes(data: Any) -> Any:
    """Recursively convert plain IRI strings in object-property lists to {"id": iri} dicts.

    Handles both the mangled key format (http_c__s__s_…_h_connectsTo) and
    the clean key format (connectsTo).
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if _is_object_property_key(key) and isinstance(value, list):
                # Wrap each bare string in the list as {"id": string}
                wrapped = []
                for item in value:
                    if isinstance(item, str):
                        wrapped.append({"id": item})
                    elif isinstance(item, dict):
                        # Recurse into nested connection dicts
                        wrapped.append(_wrap_literal_iris_as_nodes(item))
                    else:
                        wrapped.append(item)
                result[key] = wrapped
            elif isinstance(value, (dict, list)):
                result[key] = _wrap_literal_iris_as_nodes(value)
            else:
                result[key] = value
        return result
    elif isinstance(data, list):
        return [_wrap_literal_iris_as_nodes(item) for item in data]
    return data


def instantiate_modules(
    modules: List[dict[str, Any]], ogm: OGM, host: str = "localhost"
) -> List[dict[str, Any]]:
    """
    Instantiate FlexConveyor modules into the knowledge base and start their middleware servers.

    Args:
        modules: List of module JSON objects to instantiate
        ogm: The OGM instance connected to GraphDB
        host: Host to bind REST API servers to (default: "localhost", use "0.0.0.0" for distributed)

    Returns:
        List of instantiation results with module IDs and API URLs
    """
    register_shutdown_handlers()

    # Add src directory to Python path to import FlexConveyor_Module
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    flex_module_module = importlib.import_module(
        "FlexConveyor_Module.FlexConveyorModule"
    )
    flex_module_module = importlib.reload(flex_module_module)
    FlexConveyor = flex_module_module.FlexConveyor

    # Define property chains for FlexConveyor modules
    property_chains = [
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
        ],
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection"),
        ],
    ]
    class_scope = ClassScope.from_property_chains(property_chains)

    named_graph_iri = IRI("http://w3id.org/circularfactory/FlexConveyorInstances")
    class_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule")
    rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

    # Clear the named graph before instantiation to avoid stale triples
    print("🧹 Clearing existing instances graph...")
    try:
        ogm.db.clear_graph(named_graph_iri)
        print("  ✓ Graph cleared")
    except Exception as clear_err:
        print(f"  ⚠️  Could not clear graph: {clear_err} (continuing anyway)")

    # Pre-register rdf:type for every module so cross-references can be resolved
    # during sequential creation (Module1 references Module2 before Module2 is
    # fully created — OGM needs the rdf:type triple to determine the class).
    print("📝 Pre-registering module types...")
    type_triples = []
    for module_data in modules:
        mid = module_data.get("id")
        if mid:
            type_triples.append((IRI(mid), rdf_type, class_iri))
    if type_triples:
        try:
            ogm.db.triples_add(
                type_triples, check_exist=False, named_graph=named_graph_iri
            )
            print(f"  ✓ Registered {len(type_triples)} module type(s)")
        except Exception as e:
            print(f"  ⚠️  Could not pre-register types: {e}")

    print("\n" + "=" * 70)
    print("⚙️  Instantiating FlexConveyor Modules")
    print("=" * 70)
    print(f"Total modules to instantiate: {len(modules)}")

    results = []
    running_modules = []

    try:
        for idx, module_data in enumerate(modules, 1):
            module_iri_str = module_data.get("id")
            if not module_iri_str:
                print(f"⚠️  Module {idx}: Skipped (no 'id' field)")
                continue

            module_iri = IRI(module_iri_str)
            print(f"\n📦 Module {idx}: {module_iri}")

            try:
                # Ensure object-property values are dicts, not bare strings
                sanitized_data = _wrap_literal_iris_as_nodes(module_data)

                # Create the node without persisting, then force-add triples.
                # We use persist=False + manual triples_add(check_exist=False)
                # because the pre-registered rdf:type triples already exist and
                # ogm.create(persist=True) would reject ALL triples if any exist.
                print(f"  → Creating in knowledge graph...")
                node = ogm.create(
                    class_iri=class_iri,
                    class_scope=class_scope,
                    instance_iri=module_iri,
                    data=sanitized_data,
                    persist=False,
                )
                triples = node.to_triples()
                ogm.db.triples_add(
                    triples,
                    check_exist=False,
                    named_graph=named_graph_iri,
                )
                print(f"  ✓ Created successfully")

                # Initialize FlexConveyor module with the created node's IRI
                print(f"  → Initializing middleware...")
                flex_module = FlexConveyor(node.id, ogm=ogm, host=host)
                print(f"  ✓ Middleware initialized")
                time.sleep(1)

                # Start the REST API server
                print(f"  → Starting REST API server...")
                flex_module.start()
                running_modules.append(flex_module)
                with _running_modules_lock:
                    _running_modules.append(flex_module)

                # Record result
                result = {
                    "module_id": str(node.id),
                    "status": "running",
                    "api_url": flex_module.get_api_url(),
                    "port": flex_module.port,
                }
                results.append(result)
                print(f"  ✓ Started at {result['api_url']}")

            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
                result = {
                    "module_id": str(module_iri),
                    "status": "failed",
                    "error": str(e),
                }
                results.append(result)

        # Print summary
        print("\n" + "=" * 70)
        print("📋 Instantiation Summary")
        print("=" * 70)
        for result in results:
            if result["status"] == "running":
                print(f"✓ {result['module_id']}")
                print(f"  API: {result['api_url']}")
            else:
                print(
                    f"✗ {result['module_id']}: {result.get('error', 'Unknown error')}"
                )

        print(f"\nTotal running: {len(running_modules)}/{len(modules)}")
        print("=" * 70 + "\n")

        return results

    except Exception as e:
        print(f"\n✗ Fatal error during instantiation: {str(e)}")
        # Stop any modules that were started
        for module in running_modules:
            try:
                module.stop()
            except Exception as stop_error:
                print(f"Error stopping module {module.module_id}: {stop_error}")
        raise

    # Placeholder to show OGM state after instantiation
