"""Bootstrap utilities for instantiating FlexConveyor modules into the knowledge base."""

import json
import sys
import os
import importlib
import atexit
import signal
import threading
from typing import Any, List, Optional

from graph_db_interface.utils.iri import IRI
from circular_factory_ogm import OGM
from circular_factory_ogm import ClassScope
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
                # Create the module node in the knowledge graph
                print(f"  → Creating in knowledge graph...")
                node = ogm.create(
                    class_iri=IRI(
                        "http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"
                    ),
                    class_scope=class_scope,
                    instance_iri=module_iri,
                    data=module_data,
                    persist=True,
                    named_graph=IRI(
                        "http://w3id.org/circularfactory/FlexConveyorInstances"
                    ),
                )
                print(f"  ✓ Created successfully")

                # Initialize FlexConveyor module with the created node's IRI
                print(f"  → Initializing middleware...")
                flex_module = FlexConveyor(node.id, ogm=ogm, host=host)
                print(f"  ✓ Middleware initialized")

                # Start the REST API server
                print(f"  → Starting REST API server...")
                flex_module.start()
                running_modules.append(flex_module)
                with _running_modules_lock:
                    _running_modules.append(flex_module)

                # Record result
                result = {
                    "module_id": str(node.iri),
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
