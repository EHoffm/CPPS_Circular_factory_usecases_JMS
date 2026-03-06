import threading
import time
from pprint import pformat
from typing import Optional
import uvicorn
import aas_middleware as aas
from graph_db_interface.utils.iri import IRI

from circular_factory_ogm.ogm import OGM
from circular_factory_ogm.utils.class_scope import ClassScope


class FlexConveyor:
    """Represents a FlexConveyor module in the system.

    Each instance runs a separate middleware instance with its own REST API server
    on a unique port. Modules can communicate with each other via HTTP calls to
    their REST endpoints.

    Designed to support distributed systems - modules can run on different hosts
    and machines.
    """

    # Class-level port counter for thread-safe port assignment
    _port_counter = 8000
    _port_lock = threading.Lock()

    @classmethod
    def _get_next_port(cls) -> int:
        """Thread-safe port assignment across all instances."""
        with cls._port_lock:
            cls._port_counter += 1
            return cls._port_counter

    def __init__(
        self, module_id: IRI, ogm: Optional[OGM] = None, host: str = "0.0.0.0"
    ):
        """
        Initialize a FlexConveyor module.

        Args:
            module_id: IRI identifier for this module
            ogm: OGM instance for accessing the knowledge graph (required for fetching module data)
            host: Host to bind the REST API server to (default: 0.0.0.0 for all interfaces)
                  Use "localhost" for local-only access
        """
        if ogm is None:
            raise ValueError(
                "OGM instance is required to initialize FlexConveyor module"
            )

        self.module_id = module_id
        self.ogm = ogm
        self.mw = aas.Middleware()
        self.host = host
        self.port = self._get_next_port()
        self.url: Optional[str] = None  # Will be set when server starts
        self.server_thread: Optional[threading.Thread] = None
        self.server: Optional[uvicorn.Server] = None
        self.running = False
        self.adj: list[list[IRI | int]] = []
        self.accessible_at_by_module: dict[IRI, str | None] = {}
        self.service_instance_iri: Optional[IRI] = None

        # Setup middleware
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
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasService"),
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
        ]
        class_scope = ClassScope.from_property_chains(property_chains)
        data_node = self.ogm.fetch(
            instance_iri=self.module_id, class_scope=class_scope, materialize=True
        )

        self.mw.load_data_model(
            name=str(self.module_id),
            data_model=aas.DataModel.from_models(data_node.instance),
            persist_instances=True,
        )
        self.mw.generate_rest_api_for_data_model(str(self.module_id))

        def receive(box_iri: str) -> None:
            self.receive(box_iri)

        self.mw.workflow()(receive)

        print(f"✓ FlexConveyor module initialized: {self.module_id}")
        print(f"  Assigned port: {self.port}")
        print(f"  Host: {self.host}")

    def start(self):
        """
        Start the REST API server in a background thread.

        The server will be accessible at the URL printed to stdout.
        Call stop() to shut down the server.
        """
        if self.running:
            print(f"⚠ Module {self.module_id} is already running at {self.url}")
            return

        self.running = True
        self.server_thread = threading.Thread(
            target=self._run_server, daemon=False, name=f"FlexConveyor-{self.module_id}"
        )
        self.server_thread.start()

        # Give server time to start and bind to port
        time.sleep(1)

        # Construct the accessible URL
        # If host is 0.0.0.0, use localhost for local access or the actual hostname for remote
        if self.host == "0.0.0.0":
            import socket

            hostname = socket.gethostname()
            self.url = f"http://{hostname}:{self.port}"
        else:
            self.url = f"http://{self.host}:{self.port}"

        print(f"\n{'='*70}")
        print(f"✓ FlexConveyor REST API Started")
        print(f"  Module ID: {self.module_id}")
        print(f"  Accessible at: {self.url}")
        print(f"  GUI access: http://localhost:{self.port}/docs")
        print(f"{'='*70}\n")
        
        self._register_service_in_knowledge_graph()
        adjacency_matrix = self.discover_connections_and_services()
        print("Adjacency matrix:")
        print(pformat(adjacency_matrix))
        


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
            print(f"✗ Server error on {self.module_id}: {e}")
        finally:
            self.running = False

    def stop(self):
        """Stop the REST API server."""
        if not self.running:
            print(f"⚠ Module {self.module_id} is not running")
            self._cleanup_service_in_knowledge_graph()
            return

        self.running = False
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=10)
            if self.server_thread.is_alive() and self.server is not None:
                self.server.force_exit = True
                self.server_thread.join(timeout=2)
        self._cleanup_service_in_knowledge_graph()
        print(f"✓ FlexConveyor {self.module_id} stopped")

    def _register_service_in_knowledge_graph(self) -> None:
        """Create or update runtime service information in the knowledge graph."""
        service_property_chains = [
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf"),
            ],
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
        ]
        service_iri = IRI("http://w3id.org/circularfactory/FlexConveyor#Service")
        service_class_scope = ClassScope.from_property_chains(service_property_chains)
        service_data = {
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt").lined: [
                str(self.url)
            ],
            IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf").lined: [
                {"id": str(self.module_id)}
            ],
        }

        # TODO: Upsert/delete old runtime service triples for this module before creating a new service node.
        service_node = self.ogm.create(
            class_iri=service_iri,
            class_scope=service_class_scope,
            data=service_data,
            named_graph=IRI("http://w3id.org/circularfactory/FlexConveyorInstances"),
        )
        self.service_instance_iri = service_node.id
        print(f"✓ Registered service in knowledge graph with IRI: {service_node.id}")

    def _cleanup_service_in_knowledge_graph(self) -> None:
        """Cleanup runtime service information for this module from the knowledge graph."""
        if self.service_instance_iri is None:
            return

        # TODO: Remove hasService, accessibleAt, isServiceOf, and related service-node triples for this module.
        print(
            f"TODO cleanup required for runtime service triples of module {self.module_id} (service node: {self.service_instance_iri})"
        )

    def _handle_receive(self, box_iri: IRI) -> None:
        """
        Receive a box on the conveyor.

        This is a workflow that can be triggered via the REST API.
        """

    @staticmethod
    def _direction_to_index(direction: str | None) -> int | None:
        if not direction:
            return None
        direction_map = {
            "http://w3id.org/circularfactory/FlexConveyor#North": 1,
            "http://w3id.org/circularfactory/FlexConveyor#East": 2,
            "http://w3id.org/circularfactory/FlexConveyor#South": 3,
            "http://w3id.org/circularfactory/FlexConveyor#West": 4,
        }
        return direction_map.get(str(direction))

    def discover_connections_and_services(self):
        """Build directional rows: [module, North, East, South, West]."""
        adj_map: dict[IRI, list[tuple[IRI | None, str | None]]] = {}
        accessible_at_map: dict[IRI, str | None] = {}

        rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        module_class = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"
        )

        has_connection = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#hasConnection"
        )
        connects_to = IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo")
        has_direction = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#hasDirection"
        )
        has_service = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#hasService"
        )
        accessible_at = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#accessibleAt"
        )
        

        triples = self.ogm.db.triples_get(pred=rdf_type, obj=module_class)
        modules = [triple[0] for triple in triples]

        property_chains = [
            [has_connection, connects_to],
            [has_connection, has_direction],
            [has_service, accessible_at],
        ]
        class_scope = ClassScope.from_property_chains(property_chains)

        has_connection_key = has_connection.lined
        connects_to_key = connects_to.lined
        has_direction_key = has_direction.lined
        has_service_key = has_service.lined
        accessible_at_key = accessible_at.lined

        for module_iri in modules:
            module_instance = self.ogm.fetch(
                instance_iri=module_iri,
                class_scope=class_scope,
                materialize=True,
            ).instance

            if isinstance(module_instance, dict):
                module_data = module_instance
            elif hasattr(module_instance, "model_dump"):
                module_data = module_instance.model_dump(by_alias=True)
            elif hasattr(module_instance, "dict"):
                module_data = module_instance.dict()
            else:
                module_data = {}

            connections = module_data.get(has_connection_key, [])
            adjacency_entries: list[tuple[IRI | None, str | None]] = []

            for connection in connections:
                if not isinstance(connection, dict):
                    continue

                connects_to_list = connection.get(connects_to_key, [])
                direction_list = connection.get(has_direction_key, [])

                target: IRI | None = None
                if connects_to_list:
                    first_target = connects_to_list[0]
                    if isinstance(first_target, dict):
                        target_id = first_target.get("id")
                        target = IRI(str(target_id)) if target_id else None
                    else:
                        target = IRI(str(first_target))

                direction: str | None = None
                if direction_list:
                    first_direction = direction_list[0]
                    if isinstance(first_direction, dict):
                        direction = first_direction.get("id")
                    else:
                        direction = str(first_direction)

                adjacency_entries.append((target, direction))

            module_key = module_iri if isinstance(module_iri, IRI) else IRI(str(module_iri))
            adj_map[module_key] = adjacency_entries

            services = module_data.get(has_service_key, [])
            module_accessible_at: str | None = None
            if isinstance(services, list):
                for service in services:
                    if not isinstance(service, dict):
                        continue
                    locations = service.get(accessible_at_key, [])
                    if not locations:
                        continue
                    first_location = locations[0]
                    if isinstance(first_location, dict):
                        location_id = first_location.get("id")
                        module_accessible_at = str(location_id) if location_id else None
                    else:
                        module_accessible_at = str(first_location)
                    if module_accessible_at:
                        break

            accessible_at_map[module_key] = module_accessible_at

        directional_rows: list[list[IRI | int]] = []
        for module_iri in sorted(adj_map.keys(), key=str):
            row: list[IRI | int] = [module_iri, 0, 0, 0, 0]
            for target, direction in adj_map[module_iri]:
                if not target:
                    continue
                index = self._direction_to_index(direction)
                if index is None:
                    continue
                if row[index] == 0:
                    row[index] = target
            directional_rows.append(row)

        self.adj = directional_rows
        self.accessible_at_by_module = accessible_at_map
        return self.adj


    def receive(
        self,
        box_iri: IRI,
    ) -> None:
        print(f"📦 [{self.module_id}] Received box: {box_iri}")

    def get_api_url(self) -> Optional[str]:
        """Get the URL where this module's REST API is accessible."""
        return self.url

    def get_ogm(self) -> OGM:
        """Get the OGM instance used by this module."""
        return self.ogm
