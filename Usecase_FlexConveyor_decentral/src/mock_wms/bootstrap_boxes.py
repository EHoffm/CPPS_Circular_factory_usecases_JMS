import threading
import atexit
import signal
from typing import List, Any, Optional, Dict
from graph_db_interface import IRI
from kapps_ogm import OGM

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
                # TODO: hier Werte anpassen
                print("  → Creating in knowledge graph...")
                node = ogm.create(
                    class_iri=IRI("http://example.org/Box"),  # adjust to your ontology
                    instance_iri=box_iri,
                    data=box_data,
                    persist=True,
                )
                print("  ✓ Created successfully")

                # Track box instance (for cleanup / bookkeeping)
                with _running_boxes_lock:
                    _running_boxes.append(node)

                # Store result
                result = {
                    "box_id": str(node.id),
                    "hasOrigin": origin,  # TODO: hier origin und destination die module_iris
                    "hasDestination": destination,
                    "status": "created",
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
