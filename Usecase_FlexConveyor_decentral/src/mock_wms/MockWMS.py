"""Mock Warehouse Management System (WMS) for FlexConveyor simulation.

The WMS is responsible for:
- Spawning boxes into the system from a random free module to a random destination
- Accepting delivered boxes from the system
- Automatically spawning new boxes after initialization and after each delivery
"""

import logging
import threading
import time
from typing import Optional, Dict, Any, List
import random
import uvicorn
import semantic_middleware as smw
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

    def __init__(
        self, ogm: OGM, number_of_boxes: Optional[int] = 1, host: str = "0.0.0.0"
    ):
        """Initialize the WMS service."""
        if ogm is None:
            raise ValueError("OGM instance is required to initialize MockWMS")

        self.wms_id = IRI("http://w3id.org/circularfactory/FlexConveyorInstances#WMS")
        self.ogm = ogm
        self.mw = smw.Middleware()
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

        self.number_of_boxes: int = number_of_boxes

        self.logger_parent = logging.getLogger("MockWMS")
        self.logger = self.logger_parent.getChild("SubProjectLogic")

        # Setup middleware data model (minimal, just for service registration)
        data_model = smw.DataModel()
        self.mw.load_data_model(
            name=str(self.wms_id),
            data_model=data_model,
            persist_instances=False,
        )

        # Register workflows
        def spawn_box(payload: SpawnBoxPayload) -> dict:
            """Spawn a box into the system."""
            logger = self.logger_parent.getChild("SpawnBoxService")
            logger.info(f"Invoked with payload: {payload}")
            response = self._spawn_box_workflow(
                box_iri=payload.box_iri,
                origin_iri=payload.origin_iri,
                destination_iri=payload.destination_iri,
            )
            logger.info(f"Completed with response: {response}")
            return response

        def accept_box(payload: AcceptBoxPayload) -> dict:
            """Accept a delivered box."""
            logger = self.logger_parent.getChild("AcceptBoxService")
            logger.info(f"Invoked with payload: {payload}")
            response = self._accept_box_workflow(box_iri=payload.box_iri)
            logger.info(f"Completed with response: {response}")
            return response

        # Create and register services
        self.services.add(
            Service(
                service_method=spawn_box,
                service_class=IRI(
                    "http://w3id.org/circularfactory/FlexConveyor#SpawnBoxService"
                ),
                resource_instance=self.wms_id,
                payload_model=SpawnBoxPayload,
                logger=self.logger_parent.getChild("SpawnBoxService"),
            )
        )

        self.services.add(
            Service(
                service_method=accept_box,
                service_class=IRI(
                    "http://w3id.org/circularfactory/FlexConveyor#AcceptBoxService"
                ),
                resource_instance=self.wms_id,
                payload_model=AcceptBoxPayload,
                logger=self.logger_parent.getChild("AcceptBoxService"),
            )
        )

        # Register services in middleware
        for service in self.services:
            service.register_in_middleware(self.mw)

        self.logger.info(f"Initialization complete")

    def start(self):
        """Start the REST API server in a background thread."""
        if self.running:
            self.logger.warning(f"WMS is already running at {self.url}")
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

        self.logger.info(
            f"\n{'='*70}\n"
            f"  MockWMS REST API Started\n"
            f"  Module ID:     {self.wms_id}\n"
            f"  Accessible at: {self.url}\n"
            f"  GUI access:    http://localhost:{self.port}/docs\n"
            f"  Services:      {', '.join(s.name for s in self.services)}\n"
            f"{'='*70}"
        )

        # Spawn initial box after a short delay (let modules stabilize)
        if self.spawn_after_accept:
            threading.Thread(
                target=self._spawn_initial_boxes, daemon=True, name="InitialBoxSpawn"
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
            self.logger.error(f"WMS server error: {e}")
        finally:
            self.running = False

    def stop(self):
        """Stop the REST API server."""
        if not self.running:
            self.logger.warning(f"WMS is not running")
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
        self.logger.info(f"MockWMS stopped")

    def _cleanup_services_in_knowledge_graph(self):
        """Remove service registrations from the knowledge graph."""
        for service in self.services:
            try:
                service.deregister_in_graph_db(
                    ogm=self.ogm,
                    named_graph=IRI(
                        "http://w3id.org/circularfactory/FlexConveyorInstances"
                    ),
                )
            except Exception as e:
                self.logger.warning(f"Error cleaning service {service.name}: {e}")

    def _get_next_box_iri(self) -> str:
        """Generate a unique box IRI."""
        with self.box_counter_lock:
            self.box_counter += 1
            return f"http://w3id.org/circularfactory/BoxInstances#Box{self.box_counter:03d}"

    def _get_module_info(self) -> Dict[str, List[str]]:
        """
        Query the knowledge graph for module information in a single query.

        Returns:
            Dict containing:
            - 'all_modules': All FlexConveyorModule instances
            - 'entry_modules': EntryModule instances
            - 'exit_modules': ExitModule instances
            - 'free_modules': Modules without hasPossession
        """
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"

        query = f"""
        PREFIX fc: <{FC}>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        
        SELECT DISTINCT ?module ?isEntry ?isExit ?hasPossession
        WHERE {{
            GRAPH <{INST}> {{
                ?module rdf:type ?moduleType .
                
                OPTIONAL {{
                    ?module fc:hasPossession ?box .
                    BIND(true AS ?hasPossession)
                }}
            }}
            
            {{
                FILTER(?moduleType = fc:FlexConveyorModule)
            }} UNION {{
                ?moduleType rdfs:subClassOf* fc:FlexConveyorModule .
            }}
            
            OPTIONAL {{
                GRAPH <{INST}> {{
                    ?module rdf:type fc:EntryModule .
                }}
                BIND(true AS ?isEntry)
            }}
            
            OPTIONAL {{
                GRAPH <{INST}> {{
                    ?module rdf:type fc:ExitModule .
                }}
                BIND(true AS ?isExit)
            }}
        }}
        """

        result = self.ogm.db.query(query=query, convert_bindings=True)
        bindings = result.get("results", {}).get("bindings", [])

        all_modules = set()
        entry_modules = set()
        exit_modules = set()
        modules_with_possession = set()

        for binding in bindings:
            module_iri = str(binding["module"])
            all_modules.add(module_iri)

            if "isEntry" in binding and binding["isEntry"]:
                entry_modules.add(module_iri)

            if "isExit" in binding and binding["isExit"]:
                exit_modules.add(module_iri)

            if "hasPossession" in binding and binding["hasPossession"]:
                modules_with_possession.add(module_iri)

        free_modules = all_modules - modules_with_possession

        return {
            "all_modules": list(all_modules),
            "entry_modules": list(entry_modules),
            "exit_modules": list(exit_modules),
            "free_modules": list(free_modules),
        }

    def _spawn_initial_boxes(self):
        """Spawn the first box after initialization (with delay)."""
        time.sleep(3)  # Wait for system to stabilize
        self.logger.info(f"Spawning {self.number_of_boxes} initial box(es)...")
        for _ in range(self.number_of_boxes):
            try:
                self._spawn_random_box()
            except Exception as e:
                self.logger.error(f"Error spawning initial box: {e}")

    def _spawn_random_box(self):
        """
        Spawn a box on a random free module.

        Logic:
        - If EntryModules exist: origins = free EntryModules
        - If no EntryModules: origins = free non-ExitModules
        - If ExitModules exist: destinations = all ExitModules
        - If no ExitModules: destinations = all non-EntryModules (excluding chosen origin)
        """
        module_info = self._get_module_info()

        all_modules = module_info["all_modules"]
        entry_modules = module_info["entry_modules"]
        exit_modules = module_info["exit_modules"]
        free_modules = module_info["free_modules"]

        if len(all_modules) < 2:
            self.logger.warning(f"Need at least 2 modules to spawn a box (skipping)")
            return

        # Determine origin candidates (must be free)
        if entry_modules:
            # Use only EntryModules as origins
            origin_candidates = [m for m in entry_modules if m in free_modules]
        else:
            # Use all non-ExitModules as origins
            origin_candidates = [m for m in free_modules if m not in exit_modules]

        if not origin_candidates:
            self.logger.warning(f"No free origin modules available (skipping)")
            return

        # Pick random origin from candidates
        origin_iri = random.choice(origin_candidates)

        # Determine destination candidates (can be occupied or free)
        if exit_modules:
            # Use only ExitModules as destinations
            destination_candidates = exit_modules
        else:
            # Use all non-EntryModules as destinations (excluding chosen origin)
            destination_candidates = [
                m for m in all_modules if m not in entry_modules and m != origin_iri
            ]

        if not destination_candidates:
            self.logger.warning(f"No valid destination modules available (skipping)")
            return

        # Pick random destination from candidates
        destination_iri = random.choice(destination_candidates)

        # Generate box IRI
        box_iri = self._get_next_box_iri()

        self.logger.info(
            f"\n{'='*70}\n"
            f"  Spawning new box into system\n"
            f"  Box ID:      {box_iri}\n"
            f"  Origin:      {origin_iri}\n"
            f"  Destination: {destination_iri}\n"
            f"{'='*70}\n"
        )

        # Execute spawn workflow
        result = self._spawn_box_workflow(box_iri, origin_iri, destination_iri)

        if result.get("status") == "spawned":
            self.logger.info(f"Box spawned successfully")
        else:
            self.logger.error(f"Spawn failed: {result.get('error')}")

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
                service_class=IRI(f"{FC}ReceiveService"),
                payload_model=ReceivePayload,
                ogm=self.ogm,
                logger=self.logger_parent.getChild(
                    f"RemoteService@{origin.fragment}-ReceiveService"
                ),
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

            self.logger.info(f"Box {IRI(box_iri).fragment} accepted and delivered!")

            # Auto-spawn next box
            if self.spawn_after_accept:
                threading.Thread(
                    target=self._spawn_random_box, daemon=True, name="AutoSpawn"
                ).start()

            return {"status": "accepted", "box": box_iri}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_api_url(self) -> Optional[str]:
        """Get the API URL for this WMS instance."""
        return self.url
