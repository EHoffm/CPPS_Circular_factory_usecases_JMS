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
import semantic_middleware as smw


_running_modules: list[Any] = []
_running_modules_lock = threading.Lock()
_running_wms: Optional[Any] = None
_running_wms_lock = threading.Lock()
_shutdown_hooks_registered = False


# Direction mappings for reverse connections
_DIRECTION_OPPOSITES = {
    "http://w3id.org/circularfactory/FlexConveyor#North": "http://w3id.org/circularfactory/FlexConveyor#South",
    "http://w3id.org/circularfactory/FlexConveyor#South": "http://w3id.org/circularfactory/FlexConveyor#North",
    "http://w3id.org/circularfactory/FlexConveyor#East": "http://w3id.org/circularfactory/FlexConveyor#West",
    "http://w3id.org/circularfactory/FlexConveyor#West": "http://w3id.org/circularfactory/FlexConveyor#East",
}


def _create_bidirectional_connections(ogm: OGM, named_graph: IRI) -> None:
    """Create reverse (bidirectional) connections for all module pairs.

    After all modules are instantiated with their connections, this function
    ensures that if Module A connects to Module B in direction D, then Module B
    also has a connection back to Module A in the opposite direction (e.g., if
    A connects to B to the East, B gets a connection to A to the West).
    """

    rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    module_class = IRI(
        "http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"
    )
    has_connection = IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection")
    connects_to = IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo")
    has_direction = IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection")
    on_port = IRI("http://w3id.org/circularfactory/FlexConveyor#onPort")
    base_namespace = "http://w3id.org/circularfactory/FlexConveyorInstances"

    print("\n🔄 Creating bidirectional connections...")

    triples = ogm.db.triples_get(pred=rdf_type, obj=module_class)
    modules = [triple[0] for triple in triples]

    if not modules:
        print("  ⚠️  No modules found")
        return

    # Collect all existing connections
    existing_connections: dict[tuple[str, str, str], set[tuple[str, str]]] = {}

    for module_iri in modules:
        connections = ogm.db.triples_get(sub=module_iri, pred=has_connection)
        if not connections:
            continue

        for _s, _p, conn_node_iri in connections:
            target_triples = ogm.db.triples_get(sub=conn_node_iri, pred=connects_to)
            direction_triples = ogm.db.triples_get(
                sub=conn_node_iri, pred=has_direction
            )

            for _s, _p, target_iri in target_triples:
                for _s, _p, direction_iri in direction_triples:
                    key = (str(module_iri), str(target_iri), str(direction_iri))
                    existing_connections.setdefault(key, set()).add(
                        (str(module_iri), str(conn_node_iri))
                    )

    # Now add reverse connections where missing
    reverse_triples_to_add = []

    for (
        src_module,
        dst_module,
        direction_str,
    ), _conn_data in existing_connections.items():
        opposite_direction = _DIRECTION_OPPOSITES.get(direction_str)
        if not opposite_direction:
            continue

        reverse_key = (dst_module, src_module, opposite_direction)

        # Check if reverse connection already exists
        if reverse_key not in existing_connections:
            # Need to create reverse connection
            src_iri = IRI(src_module)
            dst_iri = IRI(dst_module)
            opp_dir_iri = IRI(opposite_direction)

            # Extract fragment parts to create a unique connection node ID
            src_fragment = src_iri.fragment or str(src_iri).split("#")[-1]
            dst_fragment = dst_iri.fragment or str(dst_iri).split("#")[-1]

            # Create a new connection node IRI with a valid format
            conn_node_id = (
                f"{base_namespace}#connection_{dst_fragment}_to_{src_fragment}"
            )
            conn_node_iri = IRI(conn_node_id)

            reverse_triples_to_add.append((dst_iri, has_connection, conn_node_iri))
            reverse_triples_to_add.append((conn_node_iri, connects_to, src_iri))
            reverse_triples_to_add.append((conn_node_iri, has_direction, opp_dir_iri))
            reverse_triples_to_add.append((conn_node_iri, on_port, 0))

            print(f"  → Adding: {dst_module} ←→ {src_module} ({opposite_direction})")

    if reverse_triples_to_add:
        try:
            ogm.db.triples_add(
                reverse_triples_to_add,
                check_exist=False,
                named_graph=named_graph,
            )
            print(f"  ✓ Added {len(reverse_triples_to_add) // 3} reverse connection(s)")
        except Exception as e:
            print(f"  ⚠️  Error adding reverse connections: {e}")
    else:
        print("  ✓ All connections are already bidirectional")


def register_shutdown_handlers() -> None:
    """Register process-level shutdown handlers to stop all running modules."""
    global _shutdown_hooks_registered
    if _shutdown_hooks_registered:
        return

    atexit.register(stop_all_modules)
    atexit.register(stop_wms)

    def _signal_handler(signum: int, _frame: Optional[Any]) -> None:
        print(f"\n🛑 Received signal {signum}. Stopping all FlexConveyor modules...")
        stop_all_modules()
        stop_wms()
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


def stop_wms() -> bool:
    """Stop the running WMS instance."""
    global _running_wms

    with _running_wms_lock:
        wms = _running_wms
        _running_wms = None

    if wms is None:
        return False

    print("\n" + "=" * 70)
    print("🧹 Stopping MockWMS")
    print("=" * 70)

    try:
        wms.stop()
        print("✓ WMS stopped")
        print("=" * 70 + "\n")
        return True
    except Exception as e:
        print(f"✗ Error stopping WMS: {e}")
        print("=" * 70 + "\n")
        return False


# Object properties whose values must be {"id": "..."} dicts, not plain strings.
# OGM's Node expects object-property values to be dicts so it can convert them
# into Node references.  The JSON exported by the GUI stores them as bare IRI
# strings, so we wrap them here before handing data to ogm.create().
_OBJECT_PROPERTY_FRAGMENTS = {
    "connectsTo",
    "hasDirection",
    "hasPossession",
    "hasWorkflow",
}


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
    modules: List[dict[str, Any]],
    ogm: OGM,
    host: str = "localhost",
    concurrent_guard_override: bool = False,
) -> List[dict[str, Any]]:
    """
    Instantiate FlexConveyor modules into the knowledge base and start their middleware servers.

    Args:
        modules: List of module JSON objects to instantiate
        ogm: The OGM instance connected to GraphDB
        host: Host to bind REST API servers to (default: "localhost", use "0.0.0.0" for distributed)
        concurrent_guard_override: If True, modules can accept boxes even when busy (default: False)

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
        [
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
            IRI("http://w3id.org/circularfactory/FlexConveyor#onPort"),
        ],
    ]
    class_scope = ClassScope.from_property_chains(property_chains)

    named_graph_iri = IRI("http://w3id.org/circularfactory/FlexConveyorInstances")
    default_class_iri = IRI(
        "http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"
    )
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
    class_iris = {}
    for module_data in modules:
        module_iri = module_data.get("id")
        class_iris[module_iri] = IRI(
            module_data.get(
                "http_c__s__s_www_d_w3_d_org_s_1999_s_02_s_22-rdf-syntax-ns_h_type",
                [default_class_iri],
            )[0]
        )
        if module_iri:
            type_triples.append((IRI(module_iri), rdf_type, class_iris[module_iri]))
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
            print(f"\n⚙️ Module {idx}: {module_iri}")

            try:
                # Ensure object-property values are dicts, not bare strings
                sanitized_data = _wrap_literal_iris_as_nodes(module_data)

                # Create the node without persisting, then force-add triples.
                # We use persist=False + manual triples_add(check_exist=False)
                # because the pre-registered rdf:type triples already exist and
                # ogm.create(persist=True) would reject ALL triples if any exist.
                print(f"  → Creating in knowledge graph...")
                node = ogm.create(
                    class_iri=class_iris[module_iri],
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
                flex_module = FlexConveyor(
                    node.id,
                    ogm=ogm,
                    host=host,
                    concurrent_guard_override=concurrent_guard_override,
                )
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

        # After all modules are instantiated, ensure bidirectional connections
        _create_bidirectional_connections(ogm, named_graph_iri)

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


def instantiate_wms(
    ogm: OGM, host: str = "localhost", number_of_boxes: int = 1
) -> dict[str, Any]:
    """
    Instantiate the Mock WMS into the system.

    Must be called AFTER modules are instantiated since WMS needs modules to exist.

    Args:
        ogm: The OGM instance connected to GraphDB
        host: Host to bind REST API server to (default: "localhost", use "0.0.0.0" for distributed)
        number_of_boxes: Number of boxes the WMS will spawn into the system (default: 1)

    Returns:
        Dictionary with WMS instantiation result
    """
    global _running_wms

    register_shutdown_handlers()

    # Add src directory to Python path
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    try:
        # Import MockWMS class
        wms_module = importlib.import_module("mock_wms.MockWMS")
        wms_module = importlib.reload(wms_module)
        MockWMS = wms_module.MockWMS

        print("\n" + "=" * 70)
        print("🏭 Instantiating Mock WMS")
        print("=" * 70)

        # Define WMS instance IRI and class
        wms_iri = IRI("http://w3id.org/circularfactory/FlexConveyorInstances#WMS")
        wms_class_iri = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#WarehouseManagementSystem"
        )
        named_graph_iri = IRI("http://w3id.org/circularfactory/FlexConveyorInstances")
        rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

        # Register WMS instance in knowledge graph
        print("  → Registering WMS in knowledge graph...")
        try:
            ogm.db.triples_add(
                [(wms_iri, rdf_type, wms_class_iri)],
                check_exist=False,
                named_graph=named_graph_iri,
            )
            print("  ✓ WMS registered in knowledge graph")
        except Exception as e:
            print(f"  ⚠️  Could not register WMS: {e}")

        # Initialize WMS
        print("  → Initializing WMS...")
        wms = MockWMS(ogm=ogm, host=host, number_of_boxes=number_of_boxes)
        print("  ✓ WMS initialized")
        time.sleep(1)

        # Start the REST API server
        print("  → Starting REST API server...")
        wms.start()

        with _running_wms_lock:
            _running_wms = wms

        result = {
            "wms_id": str(wms.wms_id),
            "status": "running",
            "api_url": wms.get_api_url(),
            "port": wms.port,
        }

        print(f"  ✓ Started at {result['api_url']}")
        print("=" * 70 + "\n")

        return result

    except Exception as e:
        print(f"\n✗ Fatal error during WMS instantiation: {str(e)}")
        print("=" * 70 + "\n")
        return {
            "wms_id": "WMS",
            "status": "failed",
            "error": str(e),
        }
