import threading
import time
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
        service_node = self.ogm.create(
            class_iri=service_iri,
            class_scope=service_class_scope,
            data=service_data,
            named_graph=IRI("http://w3id.org/circularfactory/FlexConveyorInstances"),
        )
        print(f"✓ Registered service in knowledge graph with IRI: {service_node.id}")
        


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
            return

        self.running = False
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=10)
            if self.server_thread.is_alive() and self.server is not None:
                self.server.force_exit = True
                self.server_thread.join(timeout=2)
        print(f"✓ FlexConveyor {self.module_id} stopped")

    def _handle_receive(self, box_iri: IRI) -> None:
        """
        Receive a box on the conveyor.

        This is a workflow that can be triggered via the REST API.
        """

    def build_adjacency_matrix(self):
        """Build an adjacency matrix of connected modules based on the knowledge graph."""
        # This method can be implemented to query the knowledge graph for connections
        # and build an adjacency matrix for pathfinding or visualization purposes.
        pass


    def receive(
        self,
        box_iri: IRI,
    ) -> None:
        print(f"📦 [{self.module_id}] Received box: {box_iri}")

    def get_api_url(self) -> Optional[str]:
        """Get the URL where this module's REST API is accessible."""
        return self.url
