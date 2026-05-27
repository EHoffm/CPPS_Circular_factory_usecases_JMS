import threading
import atexit
import signal
from typing import List, Any, Optional, Dict
from graph_db_interface import IRI
from kapps_ogm import OGM, ClassScope
from pydantic import BaseModel

# Define property chains for boxes
BOX_PROPERTY_CHAINS = [
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasOrigin"),
    ],
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasDestination"),
    ],
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasState"),
    ],
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#isPossessedBy"),
    ],
]
BOX_CLASS_SCOPE = ClassScope.from_property_chains(BOX_PROPERTY_CHAINS)
BOX_CLASS_IRI = IRI("http://w3id.org/circularfactory/FlexConveyor#Box")
BOX_DEFAULT_INSTANCE_IRI = IRI(
    "http://w3id.org/circularfactory/FlexConveyor#TemporaryBox"
)
BOX_INSTANCES_GRAPH_IRI = IRI("http://w3id.org/circularfactory/BoxInstances")

# --- Global tracking for instantiated boxes ---
_running_boxes: list[Any] = []
_running_boxes_lock = threading.Lock()
_shutdown_hooks_registered_boxes = False


def register_box_shutdown_handlers() -> None:
    """
    Register shutdown handlers for boxes.
    Ensures that all instantiated boxes are properly cleaned up on exit.
    """
    global _shutdown_hooks_registered_boxes
    if _shutdown_hooks_registered_boxes:
        return

    atexit.register(stop_all_boxes)

    def _signal_handler(signum: int, _frame: Optional[Any]) -> None:
        print(f"\n🛑 Received signal {signum}. Cleaning up all boxes...")
        stop_all_boxes()
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except ValueError:
        # Happens in non-main threads → safe to ignore
        pass

    _shutdown_hooks_registered_boxes = True


def stop_all_boxes() -> int:
    """
    Cleanup all tracked boxes.
    Since boxes have no active processes, this mainly clears state.
    """
    with _running_boxes_lock:
        boxes_to_clear = list(_running_boxes)
        _running_boxes.clear()

    if not boxes_to_clear:
        return 0

    print("\n" + "=" * 70)
    print("🧹 Cleaning up Box instances")
    print("=" * 70)

    cleared_count = 0
    for box in reversed(boxes_to_clear):
        box_id = getattr(box, "id", "unknown")
        try:
            # TODO: logik zu box löschen wenn an destination angekommen
            # If boxes later get lifecycle logic, it can be added here
            cleared_count += 1
        except Exception as e:
            print(f"✗ Error cleaning box {box_id}: {e}")

    print(f"Cleared boxes: {cleared_count}/{len(boxes_to_clear)}")
    print("=" * 70 + "\n")
    return cleared_count


def instantiate_boxes(boxes: List[Dict[str, Any]], ogm: OGM) -> List[Dict[str, Any]]:
    # TODO: inhalt boxes je dict definieren, voraussichtlich wie result unten
    """
    Instantiate boxes into the knowledge graph.

    Unlike modules:
    - No middleware is started
    - No REST API is exposed
    - Boxes are treated as passive data objects

    Args:
        boxes: List of box JSON objects
        ogm: OGM instance connected to GraphDB

    Returns:
        List of instantiation results
    """
    print("entered instantiate_boxes")
    register_box_shutdown_handlers()

    print("\n" + "=" * 70)
    print("📦 Instantiating Boxes")
    print("=" * 70)
    print(f"Total boxes to instantiate: {len(boxes)}")

    results = []

    try:
        for idx, box_data in enumerate(boxes, 1):
            box_iri_str = box_data.get("id")
            if not box_iri_str:
                print(f"⚠️  Box {idx}: Skipped (no 'id' field)")
                continue

            box_iri = IRI(box_iri_str)
            print(f"\n📦 Box {idx}: {box_iri}")

            try:
                # Create box node in the knowledge graph
                # TODO: sicher stellen, dass hier die richtigen Werte ankommen
                print("  → Creating in knowledge graph...")
                node = ogm.create(
                    class_iri=BOX_CLASS_IRI,
                    class_scope=BOX_CLASS_SCOPE,
                    instance_iri=box_iri,
                    data=box_data,
                    persist=True,
                    named_graph=BOX_INSTANCES_GRAPH_IRI,
                )
                print("  ✓ Created successfully")

                # Track box instance (for cleanup / bookkeeping)
                with _running_boxes_lock:
                    _running_boxes.append(node)

                # Store result
                # TODO hier Werte noch anpassen in result
                origin = str(node.hasOrigin)
                # boxstate_created =
                #
                result = {
                    "box_id": str(node.id),
                    "hasOrigin": "ModulIRITemp",  # TODO: hier origin und destination die module_iris
                    "hasDestination": "ModulIRITemp2",
                    "status": "created",
                    "isPossessedBy": "ModulIRITemp",
                }
                results.append(result)

            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
                result = {
                    "box_id": str(box_iri),
                    "status": "failed",
                    "error": str(e),
                }
                results.append(result)

        # Summary
        print("\n" + "=" * 70)
        print("📋 Box Instantiation Summary")
        print("=" * 70)

        for result in results:
            if result["status"] == "created":
                print(f"✓ {result['box_id']}")
            else:
                print(f"✗ {result['box_id']}: {result.get('error')}")

        print(
            f"\nTotal created: {len([r for r in results if r['status']=='created'])}/{len(boxes)}"
        )
        print("=" * 70 + "\n")

        return results

    except Exception as e:
        print(f"\n✗ Fatal error during box instantiation: {str(e)}")
        stop_all_boxes()
        raise


def create_blank_box_instance(
    ogm: OGM, instance_iri: Optional[IRI] = None
) -> BaseModel:
    """
    Create a blank FlexConveyor module instance from the ontology.

    Args:
        ogm: The OGM instance connected to GraphDB
        instance_iri: Optional custom instance IRI (uses default if not provided)

    Returns:
        BaseModel: A pydantic model instance with blank values conforming to the ontology
    """
    if instance_iri is None:
        instance_iri = BOX_DEFAULT_INSTANCE_IRI

    # Create blank instance
    blank_instance = ogm.create_blank_instance(
        instance_iri=instance_iri,
        class_iri=BOX_CLASS_IRI,
        class_scope=BOX_CLASS_SCOPE,
    )

    return blank_instance
