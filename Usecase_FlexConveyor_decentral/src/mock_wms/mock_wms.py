"""Mock Warehouse Management System (WMS) for FlexConveyor simulation.

The WMS is responsible for:
- Spawning boxes into the system from a random free module to a random destination
- Accepting delivered boxes from the system
- Automatically spawning new boxes after initialization and after each delivery
"""

import threading
import time
from typing import Optional, Dict, Any, List
import random
import uvicorn
import aas_middleware as aas
from graph_db_interface.utils.iri import IRI
from pydantic import BaseModel

from kapps_ogm import OGM, ClassScope

# Absolute import - src directory is added to sys.path by bootstrap
from FlexConveyor_Module.Service import Service


class SpawnBoxPayload(BaseModel):
    box_iri: str
    origin_iri: str
    destination_iri: str


class AcceptBoxPayload(BaseModel):
    box_iri: str


class MockWMS:
    """
    Mock Warehouse Management System entity.

    Runs its own middleware instance with REST API to expose:
    - spawn_box workflow: Creates and injects a box into the system
    - accept_box workflow: Accepts a delivered box from the system

    Automatically spawns boxes:
    - Once after initialization
    - Every time a box is accepted
    """

    # Class-level port counter (share with FlexConveyor)
    _port_counter = 9000
    _port_lock = threading.Lock()

    @classmethod
    def _get_next_port(cls) -> int:
        """Thread-safe port assignment."""
        with cls._port_lock:
            cls._port_counter += 1
            return cls._port_counter

    def __init__(self, ogm: Optional[OGM] = None, host: str = "0.0.0.0"):
        """Initialize the WMS service."""
        if ogm is None:
            raise ValueError("OGM instance is required to initialize MockWMS")

        self.wms_id = IRI("http://w3id.org/circularfactory/FlexConveyorInstances#WMS")
        self.ogm = ogm
        self.mw = aas.Middleware()
        self.host = host
        self.port = self._get_next_port()
        self.url: Optional[str] = None
        self.server_thread: Optional[threading.Thread] = None
        self.server: Optional[uvicorn.Server] = None
        self.running = False
        self.services: set[Service] = set()
        self.box_counter = 0
        self.box_counter_lock = threading.Lock()
        self.spawn_after_accept = True  # Auto-spawn boxes after acceptance
        self.initialized = False

        # Setup middleware data model (minimal, just for service registration)
        data_model = aas.DataModel()
        self.mw.load_data_model(
            name=str(self.wms_id),
            data_model=data_model,
            persist_instances=False,
        )

        # Register workflows
        def spawn_box(payload: SpawnBoxPayload) -> dict:
            """Spawn a box into the system."""
            return self._spawn_box_workflow(
                box_iri=payload.box_iri,
                origin_iri=payload.origin_iri,
                destination_iri=payload.destination_iri,
            )

        def accept_box(payload: AcceptBoxPayload) -> dict:
            """Accept a delivered box."""
            return self._accept_box_workflow(box_iri=payload.box_iri)

        # Create and register services
        self.services.add(
            Service(
                spawn_box,
                IRI("http://w3id.org/circularfactory/FlexConveyor#SpawnBoxService"),
                self.wms_id,
                SpawnBoxPayload,
            )
        )

        self.services.add(
            Service(
                accept_box,
                IRI("http://w3id.org/circularfactory/FlexConveyor#AcceptBoxService"),
                self.wms_id,
                AcceptBoxPayload,
            )
        )

        # Register services in middleware
        for service in self.services:
            service.register_in_middleware(self.mw)

        print(f"✓ MockWMS initialized")
        print(f"  Assigned port: {self.port}")
        print(f"  Host: {self.host}")

    def start(self):
        """Start the REST API server in a background thread."""
        if self.running:
            print(f"⚠ WMS is already running at {self.url}")
            return

        self.running = True
        self.server_thread = threading.Thread(
            target=self._run_server, daemon=False, name="MockWMS"
        )
        self.server_thread.start()

        # Give server time to start
        time.sleep(1)

        # Construct accessible URL
        if self.host == "0.0.0.0":
            import socket

            hostname = socket.gethostname()
            self.url = f"http://{hostname}:{self.port}"
        else:
            self.url = f"http://{self.host}:{self.port}"

        # Register services in knowledge graph
        for service in self.services:
            service.register_in_graph_db(
                host_url=self.url,
                ogm=self.ogm,
                named_graph=IRI(
                    "http://w3id.org/circularfactory/FlexConveyorInstances"
                ),
            )

        print(f"\n{'='*70}")
        print(f"✓ MockWMS REST API Started")
        print(f"  WMS ID: {self.wms_id}")
        print(f"  Accessible at: {self.url}")
        print(f"  GUI access: http://localhost:{self.port}/docs")
        print(f"{'='*70}\n")

        # Spawn initial box after a short delay (let modules stabilize)
        if self.spawn_after_accept:
            threading.Thread(
                target=self._auto_spawn_initial_box, daemon=True, name="InitialBoxSpawn"
            ).start()

        self.initialized = True

    def _run_server(self):
        """Run the uvicorn server for this middleware instance."""
        config = uvicorn.Config(
            app=self.mw.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        try:
            self.server.run()
        except Exception as e:
            print(f"✗ WMS server error: {e}")
        finally:
            self.running = False

    def stop(self):
        """Stop the REST API server."""
        if not self.running:
            print(f"⚠ WMS is not running")
            self._cleanup_services_in_knowledge_graph()
            return

        self.running = False
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=10)
            if self.server_thread.is_alive() and self.server is not None:
                self.server.force_exit = True
                self.server_thread.join(timeout=2)

        self._cleanup_services_in_knowledge_graph()
        print(f"✓ MockWMS stopped")

    def _cleanup_services_in_knowledge_graph(self):
        """Remove service registrations from the knowledge graph."""
        for service in self.services:
            try:
                service.cleanup_from_graph_db(
                    ogm=self.ogm,
                    named_graph=IRI(
                        "http://w3id.org/circularfactory/FlexConveyorInstances"
                    ),
                )
            except Exception as e:
                print(f"  ⚠️  Error cleaning service {service.workflow_name}: {e}")

    def _get_next_box_iri(self) -> str:
        """Generate a unique box IRI."""
        with self.box_counter_lock:
            self.box_counter += 1
            return f"http://w3id.org/circularfactory/BoxInstances#Box{self.box_counter:03d}"

    def _get_free_modules(self) -> List[str]:
        """Query the knowledge graph for modules without boxes."""
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        module_class = IRI(f"{FC}FlexConveyorModule")
        has_possession = IRI(f"{FC}hasPossession")
        rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

        # Find all modules
        triples = self.ogm.db.triples_get(pred=rdf_type, obj=module_class)
        all_modules = [str(triple[0]) for triple in triples]

        # Find free modules (without hasPossession)
        free_modules = []
        for module_iri in all_modules:
            possessions = self.ogm.db.triples_get(
                sub=IRI(module_iri), pred=has_possession
            )
            if not possessions:
                free_modules.append(module_iri)

        return free_modules

    def _get_all_modules(self) -> List[str]:
        """Query the knowledge graph for all modules."""
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        module_class = IRI(f"{FC}FlexConveyorModule")
        rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")

        triples = self.ogm.db.triples_get(pred=rdf_type, obj=module_class)
        return [str(triple[0]) for triple in triples]

    def _auto_spawn_initial_box(self):
        """Spawn the first box after initialization (with delay)."""
        time.sleep(3)  # Wait for system to stabilize
        print("\n🎯 WMS: Spawning initial box...")
        try:
            self._auto_spawn_box()
        except Exception as e:
            print(f"  ✗ Error spawning initial box: {e}")

    def _auto_spawn_box(self):
        """Automatically spawn a box on a random free module."""
        free_modules = self._get_free_modules()
        all_modules = self._get_all_modules()

        if len(all_modules) < 2:
            print("  ⚠️  Need at least 2 modules to spawn a box (skipping)")
            return

        if not free_modules:
            print("  ⚠️  No free modules available (skipping)")
            return

        # Pick random origin from free modules
        origin_iri = random.choice(free_modules)

        # Pick random destination (not origin)
        destination_candidates = [m for m in all_modules if m != origin_iri]
        destination_iri = random.choice(destination_candidates)

        # Generate box IRI
        box_iri = self._get_next_box_iri()

        print(f"  📦 Spawning: {box_iri}")
        print(f"     Origin: {IRI(origin_iri)}")
        print(f"     Destination: {IRI(destination_iri)}")

        # Execute spawn workflow
        result = self._spawn_box_workflow(box_iri, origin_iri, destination_iri)

        if result.get("status") == "spawned":
            print(f"  ✓ Box spawned successfully")
        else:
            print(f"  ✗ Spawn failed: {result.get('error')}")

    def _spawn_box_workflow(
        self, box_iri: str, origin_iri: str, destination_iri: str
    ) -> dict:
        """
        Spawn box workflow: Create box and inject into origin module.

        Steps:
        1. Create box in knowledge graph
        2. Set hasState = InTransit
        3. Set hasOrigin = origin_iri
        4. Set hasDestination = destination_iri
        5. Transfer ownership to origin module (set hasPossession/isPossessedBy)
        6. Call origin module's receive workflow
        """
        from FlexConveyor_Module.FlexConveyorModule import ReceivePayload

        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        try:
            box = IRI(box_iri)
            origin = IRI(origin_iri)
            destination = IRI(destination_iri)

            box_scope = ClassScope.from_property_chains(
                [
                    [IRI(f"{FC}hasState")],
                    [IRI(f"{FC}hasOrigin")],
                    [IRI(f"{FC}hasDestination")],
                ]
            )
            box_data = {
                "id": box,
                IRI(f"{FC}hasState"): [{"id": IRI(f"{FC}InTransit")}],
                IRI(f"{FC}hasOrigin"): [{"id": origin}],
                IRI(f"{FC}hasDestination"): [{"id": destination}],
            }
            box_node = self.ogm.create(
                class_iri=IRI(f"{FC}Box"),
                class_scope=box_scope,
                data=box_data,
                named_graph=named_graph,
                persist=True,
            )

            # Set ownership to origin module
            self.ogm.db.triples_add(
                [
                    (origin, IRI(f"{FC}hasPossession"), box),
                    (box, IRI(f"{FC}isPossessedBy"), origin),
                ],
                check_exist=False,
                named_graph=named_graph,
            )

            # Call origin module's receive workflow
            receive_service = Service.fetch_remote_service(
                resource_instance=origin,
                service_class=f"{FC}ReceiveService",
                payload_model=ReceivePayload,
                ogm=self.ogm,
            )

            response = receive_service(ReceivePayload(box_iri=box_iri))

            return {
                "status": "spawned",
                "box": box_iri,
                "origin": origin_iri,
                "destination": destination_iri,
                "receive_response": response.json() if response.text else {},
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _accept_box_workflow(self, box_iri: str) -> dict:
        """
        Accept box workflow: Mark box as delivered and remove from system.

        Steps:
        1. Verify box is possessed by WMS
        2. Update hasState = Delivered
        3. Remove ownership triples (hasPossession/isPossessedBy)
        4. Trigger auto-spawn if enabled
        """
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        try:
            box = IRI(box_iri)
            wms = self.wms_id

            has_state = IRI(f"{FC}hasState")
            delivered = IRI(f"{FC}Delivered")
            has_possession = IRI(f"{FC}hasPossession")
            is_possessed_by = IRI(f"{FC}isPossessedBy")
            in_transit = IRI(f"{FC}InTransit")

            # Verify ownership
            possession_check = self.ogm.db.triples_get(sub=box, pred=is_possessed_by)
            if not possession_check or str(possession_check[0][2]) != str(wms):
                return {
                    "status": "error",
                    "error": f"Box {box_iri} is not possessed by WMS",
                }

            # Update state to Delivered
            state_updated = self.ogm.db.triple_update(
                old_triple=(box, has_state, in_transit),
                new_triple=(box, has_state, delivered),
                named_graph=named_graph,
            )

            # Remove ownership
            self.ogm.db.triples_delete(
                [(wms, has_possession, box), (box, is_possessed_by, wms)],
                check_exist=False,
                named_graph=named_graph,
            )

            print(f"\n✅ WMS: Box {IRI(box_iri).fragment} accepted and delivered!")

            # Auto-spawn next box
            if self.spawn_after_accept:
                threading.Thread(
                    target=self._auto_spawn_box, daemon=True, name="AutoSpawn"
                ).start()

            return {"status": "accepted", "box": box_iri}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_api_url(self) -> Optional[str]:
        """Get the API URL for this WMS instance."""
        return self.url
