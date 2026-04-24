import heapq
import json
import threading
import time
from collections import deque
from typing import Optional, Any, Dict
import requests
import uvicorn
import semantic_middleware as smw
from graph_db_interface.utils.iri import IRI
from pydantic import BaseModel

from kapps_ogm import OGM, ClassScope
from semantic_middleware.model.util import (
    convert_camel_case_to_underscrore_str,
    get_id_with_patch,
)

from .Workflow import Workflow

import logging


class ReceivePayload(BaseModel):
    box_iri: str


class ReservePayload(BaseModel):
    box_iri: str
    source_module_iri: str


class ConveyPayload(BaseModel):
    box_iri: str
    destination_module_iri: str


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
        self,
        module_id: IRI,
        ogm: OGM,
        host: str = "0.0.0.0",
        concurrent_guard_override: bool = True,
    ):
        """Initialize one module workflow."""
        if ogm is None:
            raise ValueError(
                "OGM instance is required to initialize FlexConveyor module"
            )

        self.module_id = module_id
        self.ogm = ogm
        self.concurrent_guard_override = concurrent_guard_override
        self.mw = smw.Middleware()
        self.host = host
        self.port = self._get_next_port()
        self.url: Optional[str] = None  # Will be set when server starts
        self.server_thread: Optional[threading.Thread] = None
        self.server: Optional[uvicorn.Server] = None
        self.running = False
        self.topology_graph: Dict[str, list] = {}
        self.accessible_at_by_module: dict[IRI, str | None] = {}
        self.workflow_instance_iri: Optional[IRI] = None
        self._reserve_queue: deque[dict[str, Any]] = deque()
        self._reserve_queue_lock = threading.Lock()
        self._reserve_worker_running = False
        self.workflows: set[Workflow] = set()
        self.remote_workflows: dict[IRI, dict[str, Workflow]] = {}
        self.routing_table: Dict[str, str] = {}

        self.logger_parent = logging.getLogger(
            f"FlexConveyor-{self.module_id.fragment}"
        )
        self.logger = self.logger_parent.getChild(f"SubProjectLogic")

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
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
                IRI("http://w3id.org/circularfactory/FlexConveyor#onPort"),
            ],
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasWorkflow"),
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
        ]
        class_scope = ClassScope.from_property_chains(property_chains)
        data_node = self.ogm.fetch(
            instance_iri=self.module_id, class_scope=class_scope, materialize=True
        )

        # OGM-generated dynamic Pydantic models can have field annotations
        # that are incompatible with semantic_middleware's schema introspection
        # (issubclass checks). Fall back to manual DataModel population.
        try:
            self.mw.load_data_model(
                name=str(self.module_id),
                data_model=smw.DataModel.from_models(data_node.instance),
                persist_instances=True,
            )
        except TypeError as e:
            if "issubclass" in str(e):
                self.logger.warning(
                    f"Schema introspection failed, using simplified fallback"
                )
                data_model = smw.DataModel()
                model_id = get_id_with_patch(data_node.instance)
                data_model._key_ids_models[model_id] = data_node.instance
                type_name = type(data_node.instance).__name__.split(".")[-1]
                data_model._models_key_type.setdefault(type_name, []).append(model_id)
                data_model._schemas[type_name] = type(data_node.instance)
                underscore_name = convert_camel_case_to_underscrore_str(type_name)
                data_model._top_level_models.setdefault(underscore_name, []).append(
                    model_id
                )
                data_model._top_level_schemas.add(type_name)
                self.mw.load_data_model(
                    name=str(self.module_id),
                    data_model=data_model,
                    persist_instances=True,
                )
            else:
                raise

        try:
            self.mw.generate_rest_api_for_data_model(str(self.module_id))
        except TypeError as e:
            if "issubclass" in str(e):
                self.logger.warning(
                    f"REST API generation limited (schema introspection issue)"
                )
            else:
                raise

        def reserve(payload: ReservePayload) -> dict:
            """Step 1: Reserve workflow - check if this module is ready to receive.

            Called by the source module before attempting to transfer a parcel.
            This module checks if it currently has a parcel; if so, it waits
            until the parcel is moved from it before returning ready status.
            """
            logger = self.logger_parent.getChild("ReserveWorkflow")
            logger.info(f"Invoked with payload: {payload}")
            response = self.reserve(
                payload.box_iri,
                payload.source_module_iri,
            )
            logger.info(f"Completed with response: {response}")
            return response

        def convey(payload: ConveyPayload) -> dict:
            """Step 2: Convey workflow - transfer parcel ownership.

            Called on the source module by the destination module.
            Source removes ownership, then triggers destination receive.
            """
            logger = self.logger_parent.getChild("ConveyWorkflow")
            logger.info(f"Invoked with payload: {payload}")
            response = self.convey(
                payload.box_iri,
                payload.destination_module_iri,
            )
            logger.info(f"Completed with response: {response}")
            return response

        def receive(payload: ReceivePayload) -> dict:
            """Step 3: Receive workflow - finalize reception and route.

            Called by the source module after convey completes.
            Updates the parcel state and runs Dijkstra to route to the
            next hop or destination.
            """
            logger = self.logger_parent.getChild("ReceiveWorkflow")
            logger.info(f"Invoked with payload: {payload}")
            response = self.receive(
                payload.box_iri,
            )
            logger.info(f"Completed with response: {response}")
            return response

        self.workflows = {
            Workflow(
                workflow_method=reserve,
                workflow_class=IRI(
                    "http://w3id.org/circularfactory/FlexConveyor#ReserveWorkflow"
                ),
                resource_instance=self.module_id,
                payload_model=ReservePayload,
                logger=self.logger_parent.getChild("ReserveWorkflow"),
            ),
            Workflow(
                workflow_method=convey,
                workflow_class=IRI(
                    "http://w3id.org/circularfactory/FlexConveyor#ConveyWorkflow"
                ),
                resource_instance=self.module_id,
                payload_model=ConveyPayload,
                logger=self.logger_parent.getChild("ConveyWorkflow"),
            ),
            Workflow(
                workflow_method=receive,
                workflow_class=IRI(
                    "http://w3id.org/circularfactory/FlexConveyor#ReceiveWorkflow"
                ),
                resource_instance=self.module_id,
                payload_model=ReceivePayload,
                logger=self.logger_parent.getChild("ReceiveWorkflow"),
            ),
        }

        for workflow in self.workflows:
            workflow.register_in_middleware(self.mw)

        self.logger.info(f"Initialization complete")

    def start(self):
        """Start the REST API server in a background thread."""
        if self.running:
            self.logger.warning(
                f"Module {self.module_id} is already running at {self.url}"
            )
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

        for workflow in self.workflows:
            workflow.register_in_graph_db(
                host_url=self.url,
                ogm=self.ogm,
                named_graph=IRI(
                    "http://w3id.org/circularfactory/FlexConveyorInstances"
                ),
            )

        self.logger.info(
            f"\n{'='*70}\n"
            f"  FlexConveyor REST API Started\n"
            f"  Module ID:     {self.module_id}\n"
            f"  Accessible at: {self.url}\n"
            f"  GUI access:    http://localhost:{self.port}/docs\n"
            f"  Workflows:      {', '.join(s.name for s in self.workflows)}\n"
            f"{'='*70}"
        )

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
            self.logger.error(f"Server error on {self.module_id}: {e}")
        finally:
            self.running = False

    def stop(self):
        """Stop the REST API server."""
        if not self.running:
            self.logger.warning(f"Module {self.module_id} is not running")
            self._cleanup_workflows_in_knowledge_graph()
            return

        self.running = False
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread:
            self.server_thread.join(timeout=10)
            if self.server_thread.is_alive() and self.server is not None:
                self.server.force_exit = True
                self.server_thread.join(timeout=2)
        self._cleanup_workflows_in_knowledge_graph()
        self.logger.info(f"FlexConveyor {self.module_id} stopped")

    def _cleanup_workflows_in_knowledge_graph(self):
        """Remove workflow registrations from the knowledge graph."""
        for workflow in self.workflows:
            try:
                workflow.deregister_in_graph_db(
                    ogm=self.ogm,
                    named_graph=IRI(
                        "http://w3id.org/circularfactory/FlexConveyorInstances"
                    ),
                )
            except Exception as e:
                self.logger.warning(f"Error cleaning workflow {workflow.name}: {e}")

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

    def _discover_remote_workflows(self):
        property_chains = [
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
                IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
            ]
        ]
        class_scope = ClassScope.from_property_chains(property_chains)
        data_node = self.ogm.fetch(
            instance_iri=self.module_id, class_scope=class_scope, materialize=True
        )
        # Find all modules by rdf:type
        neighbor_module_iris: set[IRI] = set()
        for connection in getattr(
            data_node.instance,
            IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection").lined,
        ):
            neighbor_module_iris.add(
                getattr(
                    connection,
                    IRI(
                        "http://w3id.org/circularfactory/FlexConveyor#connectsTo"
                    ).lined,
                )[0].id
            )

        for module_iri in neighbor_module_iris:
            self.remote_workflows[module_iri] = {
                "receive": Workflow.fetch_remote_workflow(
                    resource_instance=module_iri,
                    workflow_class=IRI(
                        "http://w3id.org/circularfactory/FlexConveyor#ReceiveWorkflow"
                    ),
                    payload_model=ReceivePayload,
                    ogm=self.ogm,
                    logger=self.logger_parent.getChild(
                        f"RemoteWorkflow@{module_iri.fragment}-ReceiveWorkflow"
                    ),
                ),
                "reserve": Workflow.fetch_remote_workflow(
                    resource_instance=module_iri,
                    workflow_class=IRI(
                        "http://w3id.org/circularfactory/FlexConveyor#ReserveWorkflow"
                    ),
                    payload_model=ReservePayload,
                    ogm=self.ogm,
                    logger=self.logger_parent.getChild(
                        f"RemoteWorkflow@{module_iri.fragment}-ReserveWorkflow"
                    ),
                ),
                "convey": Workflow.fetch_remote_workflow(
                    resource_instance=module_iri,
                    workflow_class=IRI(
                        "http://w3id.org/circularfactory/FlexConveyor#ConveyWorkflow"
                    ),
                    payload_model=ConveyPayload,
                    ogm=self.ogm,
                    logger=self.logger_parent.getChild(
                        f"RemoteWorkflow@{module_iri.fragment}-ConveyWorkflow"
                    ),
                ),
            }

    def _populate_routing_table(self):
        """Precompute routing table for all modules using Dijkstra's algorithm."""
        if not self.topology_graph:
            self._build_topology_graph()

        for target in self.topology_graph.keys():
            if target == self.module_id:
                continue

            path = self._dijkstra_shortest_path(self.module_id, target)

            if not path:
                self.logger.error(f"No route found to {target}")
                continue

            next_hop = path[1]
            self.routing_table[target] = next_hop

    # ------------------------------------------------------------------
    #  Topology helpers
    # ------------------------------------------------------------------

    def _build_topology_graph(self) -> Dict[str, list]:
        """Build an undirected adjacency list from directional rows."""
        """Build directional rows: [module, North, East, South, West]."""
        adj_map: dict[IRI, list[tuple[IRI | None, str | None]]] = {}
        accessible_at_map: dict[IRI, str | None] = {}

        # IMPORTANT: `triples_get` cannot retrieve *all* triples (it requires a filter).
        # We therefore query the named graph once via SPARQL and then resolve BNodes
        # offline by indexing results by subject-string.
        instances_graph = "http://w3id.org/circularfactory/FlexConveyorInstances"
        query = (
            "SELECT ?s ?p ?o WHERE { "
            f"GRAPH <{instances_graph}> {{ ?s ?p ?o . }} "
            "}"
        )
        res = self.ogm.db.query(query=query, convert_bindings=True)
        bindings = (res or {}).get("results", {}).get("bindings", [])
        all_triples = [(b["s"], b["p"], b["o"]) for b in bindings]

        triples_by_subject: dict[str, list[tuple[Any, Any, Any]]] = {}
        for s, p, o in all_triples:
            triples_by_subject.setdefault(str(s), []).append((s, p, o))

        rdf_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
        module_class = "http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule"

        # Find all modules by rdf:type
        modules: set[Any] = set()
        for s, p, o in all_triples:
            if str(p) == rdf_type and str(o) == module_class:
                modules.add(s)

        for module_iri in modules:
            module_key = (
                module_iri if isinstance(module_iri, IRI) else IRI(str(module_iri))
            )
            adj_map[module_key] = []
            accessible_at_map[module_key] = None

        for module_iri in modules:
            module_key = (
                module_iri if isinstance(module_iri, IRI) else IRI(str(module_iri))
            )
            module_triples = triples_by_subject.get(str(module_iri), [])

            for _s, pred, obj in module_triples:
                pred_str = str(pred).lower()

                # Connections
                if "hasconnection" in pred_str:
                    connection_node_str = str(obj)
                    conn_triples = triples_by_subject.get(connection_node_str, [])
                    target: Any = None
                    direction: str | None = None

                    for _cs, c_pred, c_obj in conn_triples:
                        c_pred_str = str(c_pred).lower()
                        if "connectsto" in c_pred_str:
                            target = c_obj
                        elif "hasdirection" in c_pred_str:
                            direction = str(c_obj)

                    if target is not None:
                        target_iri = (
                            target if isinstance(target, IRI) else IRI(str(target))
                        )
                        adj_map[module_key].append((target_iri, direction))

        # Build directional rows
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

        adj = directional_rows
        self.accessible_at_by_module = accessible_at_map

        # First pass: ensure all modules are in the graph
        for row in adj:
            module = str(row[0])
            if module not in self.topology_graph:
                self.topology_graph[module] = []

        # Second pass: add all connections
        for row in adj:
            module = str(row[0])

            for i in range(1, 5):  # Indices 1-4: North, East, South, West
                neighbor = row[i]
                if neighbor != 0 and neighbor is not None:
                    neighbor_str = str(neighbor)
                    # Add bidirectional edges
                    if neighbor_str not in self.topology_graph[module]:
                        self.topology_graph[module].append(neighbor_str)
                    if neighbor_str not in self.topology_graph:
                        self.topology_graph[neighbor_str] = []
                    if module not in self.topology_graph[neighbor_str]:
                        self.topology_graph[neighbor_str].append(module)

        return self.topology_graph

    def _dijkstra_shortest_path(self, source: str, target: str) -> list:
        """Return shortest module path from source to target (unit weights)."""
        if not self.topology_graph:
            self._build_topology_graph()

        if source not in self.topology_graph or target not in self.topology_graph:
            return []

        distances: Dict[str, float] = {
            node: float("inf") for node in self.topology_graph
        }
        distances[source] = 0.0
        previous: Dict[str, Optional[str]] = {
            node: None for node in self.topology_graph
        }
        visited: set = set()
        pq: list = [(0.0, source)]  # (distance, node)

        while pq:
            current_dist, current = heapq.heappop(pq)

            if current in visited:
                continue
            visited.add(current)

            if current == target:
                break

            for neighbor in self.topology_graph.get(current, []):
                if neighbor in visited:
                    continue
                new_dist = current_dist + 1.0
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    previous[neighbor] = current
                    heapq.heappush(pq, (new_dist, neighbor))

        # Reconstruct path
        if distances[target] == float("inf"):
            return []

        path: list = []
        node: Optional[str] = target
        while node is not None:
            path.append(node)
            node = previous[node]
        path.reverse()

        return path

    # ------------------------------------------------------------------
    #  Three-step parcel movement workflows
    # ------------------------------------------------------------------

    def reserve(self, box_iri: str, source_module_iri: str) -> dict:
        """Step 1: Reserve - enqueue caller and process in FIFO order.

        Every reserve caller is queued. This module will trigger convey
        strictly in queue order (first caller, then second, ...).
        """
        self.logger.info(
            f"Reserve called for box {box_iri} from source {source_module_iri}"
        )

        if not self.remote_workflows:
            self._discover_remote_workflows()

        request = {
            "box_iri": str(box_iri),
            "source_module_iri": str(source_module_iri),
            "event": threading.Event(),
            "result": None,
        }

        should_start_worker = False
        with self._reserve_queue_lock:
            self._reserve_queue.append(request)
            queue_len = len(self._reserve_queue)
            self.logger.info(f"Queued reserve request at position {queue_len}")
            if not self._reserve_worker_running:
                self._reserve_worker_running = True
                should_start_worker = True

        if should_start_worker:
            worker = threading.Thread(
                target=self._process_reserve_queue,
                daemon=True,
                name=f"ReserveQueue-{self.module_id}",
            )
            worker.start()

        request["event"].wait()
        return (
            request["result"]
            if request["result"] is not None
            else {
                "status": "error",
                "module": str(self.module_id),
                "reason": "Reserve queue processing returned no result",
            }
        )

    def _process_reserve_queue(self) -> None:
        """Process queued reserve requests in strict FIFO order."""
        while True:
            with self._reserve_queue_lock:
                if not self._reserve_queue:
                    self._reserve_worker_running = False
                    return
                request = self._reserve_queue.popleft()

            try:
                result = self._handle_single_reserve_request(
                    box_iri=request["box_iri"],
                    source_module_iri=request["source_module_iri"],
                )
            except Exception as e:
                import traceback

                result = {
                    "status": "error",
                    "module": str(self.module_id),
                    "reason": str(e),
                    "traceback": traceback.format_exc(),
                }

            request["result"] = result
            request["event"].set()

    def _handle_single_reserve_request(
        self, box_iri: str, source_module_iri: str, allow_override: bool = True
    ) -> dict:
        """Handle one reserve request: wait until free, then call source convey."""
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        has_possession = IRI(f"{FC}hasPossession")

        timeout_seconds = 50
        poll_interval = 0.5
        elapsed = 0.0

        while elapsed < timeout_seconds:
            possession_triples = self.ogm.db.triples_get(
                sub=self.module_id, pred=has_possession
            )
            boxes = (
                [str(t[2]) for t in possession_triples] if possession_triples else []
            )

            if not boxes:
                self.logger.info(
                    f"Free for queued box {box_iri}; triggering source convey"
                )
                break

            # Override allows concurrent convey for testing purposes - This must trigger a SHACL violation error
            if allow_override and self.concurrent_guard_override:
                self.logger.warning(
                    f"Busy with {len(boxes)} parcel(s): {boxes}. Concurrent guard override enabled! Proceeding with queued box {box_iri} anyways."
                )
                break

            self.logger.info(f"Busy with {len(boxes)} parcel(s): {boxes}. Waiting...")
            time.sleep(poll_interval)
            elapsed += poll_interval

        if elapsed >= timeout_seconds:
            self.logger.error(
                f"Reserve timeout after {timeout_seconds}s for box {box_iri}"
            )
            return {
                "status": "timeout",
                "module": str(self.module_id),
                "box": str(box_iri),
                "source_module": str(source_module_iri),
                "reason": "Module did not become free within timeout period",
            }

        response = self.remote_workflows[IRI(source_module_iri)]["convey"](
            ConveyPayload(
                box_iri=box_iri,
                destination_module_iri=str(self.module_id),
            )
        )

        if (
            hasattr(response, "text")
            and '"status":"ownership_transfer_failed"' in response.text
            and allow_override
        ):
            self.logger.warning(
                f"Convey-on-source failed due to ownership transfer, but concurrent guard override is enabled. Disabling guard to proceed with simulation."
            )
            return self._handle_single_reserve_request(
                box_iri=box_iri,
                source_module_iri=source_module_iri,
                allow_override=False,
            )

        if response.status_code >= 400:
            self.logger.error(
                f"Convey-on-source failed with HTTP {response.status_code}"
            )
            return {
                "status": "convey_request_failed",
                "module": str(self.module_id),
                "box": str(box_iri),
                "source_module": str(source_module_iri),
                "http_status": response.status_code,
                "http_text": response.text,
            }

        convey_result = response.json() if response.text else {}
        self.logger.info(
            f"Convey-on-source from {source_module_iri} to {self.module_id} response: {convey_result}"
        )
        return {
            "status": "reserved_and_pulled",
            "module": str(self.module_id),
            "box": str(box_iri),
            "source_module": str(source_module_iri),
            "convey": convey_result,
        }

    def convey(
        self,
        box_iri: str,
        destination_module_iri: str,
    ) -> dict:
        """Step 2: Convey - Executed on source module.

        Source module performs the full ownership transfer:
        remove ownership from source and assign ownership to destination,
        then triggers destination module `receive` asynchronously.

        Args:
            box_iri: IRI of the parcel being transferred.
            destination_module_iri: Destination module IRI.

        Returns:
            dict with removal and downstream receive status.
        """
        if not self.remote_workflows:
            self._discover_remote_workflows()

        box = IRI(box_iri) if not isinstance(box_iri, IRI) else box_iri
        destination_module = (
            IRI(destination_module_iri)
            if not isinstance(destination_module_iri, IRI)
            else destination_module_iri
        )

        self.logger.info(f"Conveying box {box} to {destination_module}")
        try:
            self.WMS_transfer_ownership(
                str(box), str(self.module_id), str(destination_module)
            )
        except Exception as e:
            self.logger.error(f"Convey ownership transfer failed: {e}")
            return {
                "status": "ownership_transfer_failed",
                "module": str(self.module_id),
                "box": str(box),
                "destination_module": str(destination_module),
                "reason": str(e),
            }

        # Wait 1 second to simulate transit time
        self.logger.info(f"Waiting 5 seconds for transit...")
        time.sleep(5)

        def _call_receive_in_background() -> None:
            try:
                response = self.remote_workflows[IRI(destination_module_iri)][
                    "receive"
                ](
                    ReceivePayload(
                        box_iri=box_iri,
                    )
                )
                if response.status_code >= 400:
                    self.logger.error(
                        f"Background destination receive failed with HTTP {response.status_code}: {response.text}"
                    )
                else:
                    self.logger.info("Background destination receive succeeded")
            except Exception as e:
                self.logger.error(f"Background destination receive exception: {e}")

        threading.Thread(
            target=_call_receive_in_background,
            daemon=True,
            name=f"ReceiveTrigger-{self.module_id}-to-{destination_module}",
        ).start()

        return {
            "status": "conveyed_receive_started",
            "module": str(self.module_id),
            "box": str(box),
            "to_module": str(destination_module),
            "receive": {"status": "started_async"},
        }

    def receive(self, box_iri: str) -> dict:
        """Step 3: Receive - Determine next hop and initiate reserve.

        This workflow computes the shortest path to the destination using
        Dijkstra and calls reserve on the next hop module.
        Ownership transfer is handled fully by the convey workflow.

        Args:
            box_iri: IRI string of the box being received.
            destination_iri: Optional IRI string of the destination module.

        Returns:
            dict describing the route and next hop reservation status.
        """
        if not self.remote_workflows:
            self._discover_remote_workflows()

        if not self.routing_table:
            self._populate_routing_table()

        FC = "http://w3id.org/circularfactory/FlexConveyor#"

        box_property_chains = [
            [IRI(f"{FC}isPossessedBy")],
            [IRI(f"{FC}hasDestination")],
            [IRI(f"{FC}hasState")],
        ]
        class_scope = ClassScope.from_property_chains(box_property_chains)
        box_instance = self.ogm.fetch(
            instance_iri=box_iri,
            class_scope=class_scope,
            materialize=True,
        ).instance

        self.logger.info(f"Receive: processing box {box_iri}")

        box_iri = box_instance.id
        posessor_iri = getattr(box_instance, IRI(f"{FC}isPossessedBy").lined)[0].id
        destination_iri = getattr(box_instance, IRI(f"{FC}hasDestination").lined)[0].id
        state_iri = getattr(box_instance, IRI(f"{FC}hasState").lined)[0].id

        if not posessor_iri == self.module_id:
            self.logger.error(
                f"Box {box_iri} is not possessed by this module. Current possessor: {posessor_iri}"
            )
            return {
                "status": "error",
                "module": str(self.module_id),
                "box": str(box_iri),
                "reason": f"Box is possessed by {posessor_iri}, not {self.module_id}",
            }

        if not state_iri == IRI(f"{FC}InTransit"):
            self.logger.error(
                f"Box {box_iri} is not in 'InTransit' state. Current state: {state_iri}"
            )
            return {
                "status": "error",
                "module": str(self.module_id),
                "box": str(box_iri),
                "reason": f"Box is in state {state_iri}, expected 'InTransit'",
            }

        if destination_iri == self.module_id:
            # Transfer to WMS and call WMS's accept_box workflow
            self._deliver_to_wms(str(box_iri))

            return {
                "status": "delivered",
                "module": str(self.module_id),
                "box": str(box_iri),
            }

        next_hop = self.routing_table.get(destination_iri)

        self.logger.info(f"Initiating pull-handshake transfer to {next_hop}")

        # Step 1: Reserve
        response = self.remote_workflows[next_hop]["reserve"](
            ReservePayload(
                box_iri=box_iri,
                source_module_iri=str(self.module_id),
            )
        )

        if response.status_code >= 400:
            self.logger.error(f"Reserve failed with HTTP {response.status_code}")
            return {
                "status": "reserve_failed",
                "module": str(self.module_id),
                "box": str(box_iri),
                "destination": str(destination_iri),
                "next_hop": next_hop,
                "http_status": response.status_code,
                "http_text": response.text,
            }

        reserve_result = response.json() if response.text else {}
        if reserve_result.get("status") != "reserved_and_pulled":
            self.logger.warning(
                f"Transfer did not complete: {reserve_result.get('reason', 'unknown')}"
            )
            return {
                "status": "reserve_or_pull_failed",
                "module": str(self.module_id),
                "box": str(box_iri),
                "destination": str(destination_iri),
                "next_hop": next_hop,
                "reserve_response": reserve_result,
            }

        self.logger.info(f"Pull-handshake transfer completed to {next_hop}")

        return {
            "status": "routed",
            "module": str(self.module_id),
            "box": str(box_iri),
            "destination": str(destination_iri),
            "next_hop": next_hop,
        }

    def _deliver_to_wms(self, box_iri: str) -> dict:
        """
        Deliver a box to the WMS by transferring ownership and calling WMS's accept_box workflow.

        Args:
            box_iri: IRI of the box to deliver

        Returns:
            Result dictionary from WMS's accept_box workflow
        """
        from mock_wms.MockWMS import AcceptBoxPayload

        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        WMS_IRI = f"{INST}#WMS"

        # Call WMS's accept_box workflow
        try:
            # Transfer ownership from this module to WMS
            self.WMS_transfer_ownership(
                box_iri,
                str(self.module_id),
                WMS_IRI,
            )

            wms_accept_workflow = Workflow.fetch_remote_workflow(
                resource_instance=IRI(WMS_IRI),
                workflow_class=IRI(f"{FC}AcceptBoxWorkflow"),
                payload_model=AcceptBoxPayload,
                ogm=self.ogm,
            )

            response = wms_accept_workflow(AcceptBoxPayload(box_iri=box_iri))

            if response.status_code >= 400:
                self.logger.error(
                    f"WMS accept_box workflow failed: {response.status_code}"
                )
                return {"status": "error", "error": f"HTTP {response.status_code}"}

            result = response.json() if response.text else {}
            self.logger.info(f"Box {box_iri} delivered to WMS!")
            return result

        except Exception as e:
            self.logger.error(f"Error calling WMS accept_box workflow: {e}")
            return {"status": "error", "error": str(e)}

    def WMS_transfer_ownership(
        self, box: str, origin_module: str, destination_module: str
    ) -> None:
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        has_possession = IRI(f"{FC}hasPossession")
        is_possessed_by = IRI(f"{FC}isPossessedBy")

        try:
            self.ogm.db.triples_update(
                old_triples=[
                    (origin_module, has_possession, box),
                    (box, is_possessed_by, origin_module),
                ],
                new_triples=[
                    (destination_module, has_possession, box),
                    (box, is_possessed_by, destination_module),
                ],
                named_graph=named_graph,
            )
        except Exception as e:
            raise Exception(
                f"Failed to transfer ownership of box {box} from {origin_module} to {destination_module}: {e}"
            )
        self.logger.info(
            f"Box ownership transferred: {origin_module} → {destination_module}"
        )

    def get_api_url(self) -> Optional[str]:
        """Get the URL where this module's REST API is accessible."""
        return self.url

    def get_ogm(self) -> OGM:
        """Get the OGM instance used by this module."""
        return self.ogm
