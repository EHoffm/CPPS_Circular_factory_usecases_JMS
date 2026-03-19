import heapq
import json
import threading
import time
from collections import deque
from typing import Optional, Any, Dict

import requests
import uvicorn
import aas_middleware as aas
from graph_db_interface.utils.iri import IRI
from pydantic import BaseModel

from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope
from aas_middleware.model.util import convert_camel_case_to_underscrore_str, get_id_with_patch


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
        """Initialize one module service."""
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
        self._reserve_queue: deque[dict[str, Any]] = deque()
        self._reserve_queue_lock = threading.Lock()
        self._reserve_worker_running = False

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

        # OGM-generated dynamic Pydantic models can have field annotations
        # that are incompatible with aas_middleware's schema introspection
        # (issubclass checks). Fall back to manual DataModel population.
        try:
            self.mw.load_data_model(
                name=str(self.module_id),
                data_model=aas.DataModel.from_models(data_node.instance),
                persist_instances=True,
            )
        except TypeError as e:
            if "issubclass" in str(e):
                print(f"  ⚠️  Schema introspection failed, using simplified fallback")
                data_model = aas.DataModel()
                model_id = get_id_with_patch(data_node.instance)
                data_model._key_ids_models[model_id] = data_node.instance
                type_name = type(data_node.instance).__name__.split(".")[-1]
                data_model._models_key_type.setdefault(type_name, []).append(model_id)
                data_model._schemas[type_name] = type(data_node.instance)
                underscore_name = convert_camel_case_to_underscrore_str(type_name)
                data_model._top_level_models.setdefault(underscore_name, []).append(model_id)
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
                print(f"  ⚠️  REST API generation limited (schema introspection issue)")
            else:
                raise

        class ReceivePayload(BaseModel):
            box_iri: str
            destination_iri: str | None = None

        class ReservePayload(BaseModel):
            box_iri: str
            source_module_iri: str

        class ConveyPayload(BaseModel):
            box_iri: str
            destination_module_iri: str
            destination_module_url: str

        def reserve(payload: ReservePayload) -> dict:
            """Step 1: Reserve workflow - check if this module is ready to receive.

            Called by the source module before attempting to transfer a parcel.
            This module checks if it currently has a parcel; if so, it waits
            until the parcel is moved from it before returning ready status.
            """
            return self.reserve(payload.box_iri, payload.source_module_iri)

        def convey(payload: ConveyPayload) -> dict:
            """Step 2: Convey workflow - transfer parcel ownership.

            Called on the source module by the destination module.
            Source removes ownership, then triggers destination receive.
            """
            return self.convey(
                payload.box_iri,
                payload.destination_module_iri,
                payload.destination_module_url,
            )

        def receive(payload: ReceivePayload) -> dict:
            """Step 3: Receive workflow - finalize reception and route.

            Called by the source module after convey completes.
            Updates the parcel state and runs Dijkstra to route to the
            next hop or destination.
            """
            box_iri = payload.box_iri
            destination_iri = payload.destination_iri
            return self.receive(str(box_iri), str(destination_iri) if destination_iri else None)

        def has_parcel() -> dict:
            return self.has_parcel()

        def clear_parcels() -> dict:
            return self.clear_parcels()

        self.mw.workflow()(reserve)
        self.mw.workflow()(convey)
        self.mw.workflow()(receive)
        self.mw.workflow()(has_parcel)
        self.mw.workflow()(clear_parcels)

        print(f"✓ FlexConveyor module initialized: {self.module_id}")
        print(f"  Assigned port: {self.port}")
        print(f"  Host: {self.host}")

    def start(self):
        """Start the REST API server in a background thread."""
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
        """Create runtime service triples for this module."""
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
        try:
            has_service = IRI("http://w3id.org/circularfactory/FlexConveyor#hasService")
            self.ogm.db.triples_add(
                [(self.module_id, has_service, self.service_instance_iri)],
                check_exist=False,
                named_graph=IRI("http://w3id.org/circularfactory/FlexConveyorInstances"),
            )
        except Exception as e:
            print(f"  ⚠️  Could not link module to service node via hasService: {e}")
        print(f"✓ Registered service in knowledge graph with IRI: {service_node.id}")

    def _cleanup_service_in_knowledge_graph(self) -> None:
        """Cleanup runtime service information for this module from the knowledge graph."""
        if self.service_instance_iri is None:
            return

        # TODO: Remove hasService, accessibleAt, isServiceOf, and related service-node triples for this module.
        print(
            f"TODO cleanup required for runtime service triples of module {self.module_id} (service node: {self.service_instance_iri})"
        )

    def has_parcel(self) -> dict:
        """Return whether this module currently has a box."""
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        has_possession = IRI(f"{FC}hasPossession")

        possession_triples = self.ogm.db.triples_get(
            sub=self.module_id, pred=has_possession
        )

        boxes = [str(t[2]) for t in possession_triples] if possession_triples else []
        result = {
            "module": str(self.module_id),
            "has_parcel": bool(boxes),
            "boxes": boxes,
            "count": len(boxes),
        }

        print(f"📊 [{self.module_id}] has_parcel={bool(boxes)}, boxes={boxes}")
        return result

    def clear_parcels(self) -> dict:
        """Remove all parcels from the system.

        Deletes all hasPossession and isPossessedBy triples, effectively
        removing all parcel ownership relationships from all modules.

        Returns:
            dict with status and count of parcels removed.
        """
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        has_possession = IRI(f"{FC}hasPossession")
        is_possessed_by = IRI(f"{FC}isPossessedBy")

        # Get all possession triples across the entire system
        all_possession = self.ogm.db.triples_get(pred=has_possession)
        all_possessed = self.ogm.db.triples_get(pred=is_possessed_by)

        count = len(all_possession) if all_possession else 0

        # Delete all ownership relationships
        if all_possession:
            self.ogm.db.triples_delete(
                all_possession, check_exist=False, named_graph=named_graph
            )
        if all_possessed:
            self.ogm.db.triples_delete(
                all_possessed, check_exist=False, named_graph=named_graph
            )

        print(f"🗑️  Cleared {count} parcel(s) from entire system")

        return {
            "status": "cleared",
            "parcels_removed": count,
        }

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

        try:
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
                module_key = module_iri if isinstance(module_iri, IRI) else IRI(str(module_iri))
                adj_map[module_key] = []
                accessible_at_map[module_key] = None

            for module_iri in modules:
                module_key = module_iri if isinstance(module_iri, IRI) else IRI(str(module_iri))
                module_triples = triples_by_subject.get(str(module_iri), [])

                # Preferred: module -> hasService -> serviceNode -> accessibleAt
                # Fallback: serviceNode -> isServiceOf -> module (inverse lookup)
                service_nodes: list[str] = []
                for _s, pred, obj in module_triples:
                    if "hasservice" in str(pred).lower():
                        service_nodes.append(str(obj))

                if not service_nodes:
                    for s, p, o in all_triples:
                        if str(o) == str(module_iri) and "isserviceof" in str(p).lower():
                            service_nodes.append(str(s))

                for service_node_str in service_nodes:
                    service_triples = triples_by_subject.get(service_node_str, [])
                    for _ss, s_pred, s_obj in service_triples:
                        if "accessibleat" in str(s_pred).lower():
                            accessible_at_map[module_key] = str(s_obj)
                            break
                    if accessible_at_map.get(module_key):
                        break

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
                            target_iri = target if isinstance(target, IRI) else IRI(str(target))
                            adj_map[module_key].append((target_iri, direction))

                    # Service URL discovery is handled above.
                    elif "hasservice" in pred_str or "isserviceof" in pred_str or "accessibleat" in pred_str:
                        continue

        except Exception as e:
            import traceback
            print(f"Exception parsing triples: {e}")
            traceback.print_exc()

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

        self.adj = directional_rows
        self.accessible_at_by_module = accessible_at_map
        return self.adj


    # ------------------------------------------------------------------
    #  Topology helpers
    # ------------------------------------------------------------------

    def _build_topology_graph(self) -> Dict[str, list]:
        """Build an undirected adjacency list from directional rows."""
        graph: Dict[str, list] = {}

        # First pass: ensure all modules are in the graph
        for row in self.adj:
            module = str(row[0])
            if module not in graph:
                graph[module] = []

        # Second pass: add all connections
        for row in self.adj:
            module = str(row[0])

            for i in range(1, 5):  # Indices 1-4: North, East, South, West
                neighbor = row[i]
                if neighbor != 0 and neighbor is not None:
                    neighbor_str = str(neighbor)
                    # Add bidirectional edges
                    if neighbor_str not in graph[module]:
                        graph[module].append(neighbor_str)
                    if neighbor_str not in graph:
                        graph[neighbor_str] = []
                    if module not in graph[neighbor_str]:
                        graph[neighbor_str].append(module)

        return graph

    def _dijkstra_shortest_path(self, source: str, target: str) -> list:
        """Return shortest module path from source to target (unit weights)."""
        graph = self._build_topology_graph()

        if source not in graph or target not in graph:
            return []

        distances: Dict[str, float] = {node: float("inf") for node in graph}
        distances[source] = 0.0
        previous: Dict[str, Optional[str]] = {node: None for node in graph}
        visited: set = set()
        pq: list = [(0.0, source)]  # (distance, node)

        while pq:
            current_dist, current = heapq.heappop(pq)

            if current in visited:
                continue
            visited.add(current)

            if current == target:
                break

            for neighbor in graph.get(current, []):
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
        print(f"\n🔖 [{self.module_id}] Reserve called for box {box_iri} from source {source_module_iri}")

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
            print(f"  📥 Queued reserve request at position {queue_len}")
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
        return request["result"] if request["result"] is not None else {
            "status": "error",
            "module": str(self.module_id),
            "reason": "Reserve queue processing returned no result",
        }

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

    def _handle_single_reserve_request(self, box_iri: str, source_module_iri: str) -> dict:
        """Handle one reserve request: wait until free, then call source convey."""
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        has_possession = IRI(f"{FC}hasPossession")

        timeout_seconds = 50
        poll_interval = 0.5
        elapsed = 0.0

        while elapsed < timeout_seconds:
            possession_triples = self.ogm.db.triples_get(sub=self.module_id, pred=has_possession)
            boxes = [str(t[2]) for t in possession_triples] if possession_triples else []

            if not boxes:
                print(f"  ✓ [{self.module_id}] Free for queued box {box_iri}; triggering source convey")
                break

            print(f"  ⏳ [{self.module_id}] Busy with {len(boxes)} parcel(s): {boxes}. Waiting...")
            time.sleep(poll_interval)
            elapsed += poll_interval

        if elapsed >= timeout_seconds:
            print(f"  ❌ [{self.module_id}] Reserve timeout after {timeout_seconds}s for box {box_iri}")
            return {
                "status": "timeout",
                "module": str(self.module_id),
                "box": str(box_iri),
                "source_module": str(source_module_iri),
                "reason": "Module did not become free within timeout period",
            }

        self.discover_connections_and_services()
        source_iri = IRI(source_module_iri) if not isinstance(source_module_iri, IRI) else source_module_iri
        source_url = self.accessible_at_by_module.get(source_iri)

        if not source_url:
            print(f"  ❌ Source URL not found for {source_module_iri}")
            return {
                "status": "source_unreachable",
                "module": str(self.module_id),
                "box": str(box_iri),
                "source_module": str(source_module_iri),
                "reason": "Could not resolve source module service URL",
            }

        convey_url = f"{source_url}/workflows/convey/execute"
        print(f"  📡 Calling source convey: {convey_url}")
        response = requests.post(
            convey_url,
            json={
                "box_iri": box_iri,
                "destination_module_iri": str(self.module_id),
                "destination_module_url": str(self.url),
            },
            timeout=None,
        )

        if response.status_code >= 400:
            print(f"  ❌ Convey-on-source failed with HTTP {response.status_code}")
            return {
                "status": "convey_request_failed",
                "module": str(self.module_id),
                "box": str(box_iri),
                "source_module": str(source_module_iri),
                "http_status": response.status_code,
                "http_text": response.text,
            }

        convey_result = response.json() if response.text else {}
        return {
            "status": "reserved_and_pulled",
            "module": str(self.module_id),
            "box": str(box_iri),
            "source_module": str(source_module_iri),
            "convey": convey_result,
        }

    def convey(self, box_iri: str, destination_module_iri: str, destination_module_url: str) -> dict:
        """Step 2: Convey - Executed on source module.

        Source module performs the full ownership transfer:
        remove ownership from source and assign ownership to destination,
        then triggers destination module `receive` asynchronously.

        Args:
            box_iri: IRI of the parcel being transferred.
            destination_module_iri: Destination module IRI.
            destination_module_url: Destination module base URL.

        Returns:
            dict with removal and downstream receive status.
        """
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        box = IRI(box_iri) if not isinstance(box_iri, IRI) else box_iri
        destination_module = (
            IRI(destination_module_iri)
            if not isinstance(destination_module_iri, IRI)
            else destination_module_iri
        )

        has_possession = IRI(f"{FC}hasPossession")
        is_possessed_by = IRI(f"{FC}isPossessedBy")

        print(f"\n📤 [{self.module_id}] Conveying box {box} to {destination_module}")

        # Wait 1 second to simulate transit time
        print(f"  ⏱️  Waiting 1 second for transit...")
        time.sleep(5)

        # Remove parcel from this source module
        old_possession = self.ogm.db.triples_get(sub=self.module_id, pred=has_possession, obj=box)
        if old_possession:
            self.ogm.db.triples_delete(
                old_possession, check_exist=False, named_graph=named_graph
            )
            print(f"  → Removed box from source module {self.module_id}")

        # Remove old isPossessedBy on the box
        old_possessed = self.ogm.db.triples_get(sub=box, pred=is_possessed_by)
        if old_possessed:
            self.ogm.db.triples_delete(
                old_possessed, check_exist=False, named_graph=named_graph
            )

        # Remove any stale hasPossession triples for this box on any module
        old_possession_any = self.ogm.db.triples_get(pred=has_possession, obj=box)
        if old_possession_any:
            self.ogm.db.triples_delete(
                old_possession_any, check_exist=False, named_graph=named_graph
            )

        # Assign ownership to destination module (B)
        self.ogm.db.triples_add(
            [
                (destination_module, has_possession, box),
                (box, is_possessed_by, destination_module),
            ],
            check_exist=False,
            named_graph=named_graph,
        )
        print(f"  ✓ Box ownership transferred: {self.module_id} → {destination_module}")

        # Step 5: trigger receive on destination module asynchronously
        receive_url = f"{destination_module_url}/workflows/receive/execute"
        print(f"  📡 Triggering destination receive in background: {receive_url}")

        def _call_receive_in_background() -> None:
            try:
                response = requests.post(
                    receive_url,
                    json={"box_iri": str(box)},
                    timeout=None,
                )
                if response.status_code >= 400:
                    print(
                        f"  ❌ Background destination receive failed with HTTP {response.status_code}: {response.text}"
                    )
                else:
                    print("  ✓ Background destination receive succeeded")
            except Exception as e:
                print(f"  ❌ Background destination receive exception: {e}")

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

    def receive(self, box_iri: str, destination_iri: str | None = None) -> dict:
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
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        box = IRI(box_iri) if not isinstance(box_iri, IRI) else box_iri
        has_destination = IRI(f"{FC}hasDestination")
        has_state_prop = IRI(f"{FC}hasState")
        delivered = IRI(f"{FC}Delivered")

        print(f"\n📥 [{self.module_id}] Receive: processing box {box}")

        # Get destination from payload or knowledge graph
        destination_arg = (
            IRI(destination_iri)
            if destination_iri is not None and not isinstance(destination_iri, IRI)
            else destination_iri
        )

        if destination_arg is not None:
            # Update destination in knowledge graph if provided
            old_destinations = self.ogm.db.triples_get(sub=box, pred=has_destination)
            if old_destinations:
                self.ogm.db.triples_delete(
                    old_destinations, check_exist=False, named_graph=named_graph
                )
            self.ogm.db.triples_add(
                [(box, has_destination, destination_arg)],
                check_exist=False,
                named_graph=named_graph,
            )

        # Get destination from knowledge graph
        dest_triples = self.ogm.db.triples_get(sub=box, pred=has_destination)
        destination = dest_triples[0][2] if dest_triples else None

        # Check if this module is the destination
        if destination and str(destination) == str(self.module_id):
            old_states = self.ogm.db.triples_get(sub=box, pred=has_state_prop)
            if old_states:
                self.ogm.db.triples_delete(
                    old_states, check_exist=False, named_graph=named_graph
                )
            self.ogm.db.triples_add(
                [(box, has_state_prop, delivered)],
                check_exist=False,
                named_graph=named_graph,
            )
            print(f"  ✅ Box {box} DELIVERED to destination {self.module_id}!")
            return {
                "status": "delivered",
                "module": str(self.module_id),
                "box": str(box),
            }

        # Not at destination - compute route and call reserve on next hop
        if destination:
            print(f"  🔄 Computing route to destination: {destination}")
            routing_result = self.route_box(str(box), str(destination))
            return {
                "status": "routed",
                "module": str(self.module_id),
                "box": str(box),
                "destination": str(destination),
                "routing": routing_result,
            }

        print(f"  ⚠️  No destination set for box {box}")
        return {
            "status": "received_no_destination",
            "module": str(self.module_id),
            "box": str(box),
        }

    def route_box(self, box_iri: str, destination_iri: str) -> dict:
        """Route a box to its destination using Dijkstra's shortest path.

        Uses the 3-step workflow: reserve → convey → receive.
        """
        try:
            source = str(self.module_id)
            target = destination_iri

            print(f"\n🗺️  [{self.module_id}] Computing route: {source} → {target}")

            # Always refresh topology
            self.discover_connections_and_services()

            path = self._dijkstra_shortest_path(source, target)

            if not path:
                print(f"  ❌ No route found from {source} to {target}")
                return {
                    "status": "no_route",
                    "source": source,
                    "destination": target,
                    "path": [],
                }

            if len(path) < 2:
                # Already at destination
                print("  ✅ Already at destination")
                return {
                    "status": "already_at_destination",
                    "source": source,
                    "destination": target,
                    "path": path,
                }

            print(f"  📍 Route: {' → '.join(path)}")

            next_hop = path[1]
            next_hop_iri = IRI(next_hop)

            # Find the URL of the next module's REST API
            next_url = self.accessible_at_by_module.get(next_hop_iri)

            if not next_url:
                print(f"  ❌ No accessible URL for next hop: {next_hop}")
                return {
                    "status": "next_hop_unreachable",
                    "next_hop": next_hop,
                    "path": path,
                }

            print(f"  📡 Initiating pull-handshake transfer to {next_hop}")

            # Step 1: Reserve
            reserve_url = f"{next_url}/workflows/reserve/execute"
            print(f"  1️⃣  Reserve: {reserve_url}")
            response = requests.post(
                reserve_url,
                json={
                    "box_iri": box_iri,
                    "source_module_iri": str(self.module_id),
                },
                timeout=None,
            )

            if response.status_code >= 400:
                print(f"  ❌ Reserve failed with HTTP {response.status_code}")
                return {
                    "status": "reserve_failed",
                    "next_hop": next_hop,
                    "http_status": response.status_code,
                    "http_text": response.text,
                }

            reserve_result = response.json() if response.text else {}
            if reserve_result.get("status") != "reserved_and_pulled":
                print(f"  ⏳ Transfer did not complete: {reserve_result.get('reason', 'unknown')}")
                return {
                    "status": "reserve_or_pull_failed",
                    "next_hop": next_hop,
                    "reserve_response": reserve_result,
                }

            print(f"  ✅ Pull-handshake transfer completed to {next_hop}")

            return {
                "status": "transferred",
                "next_hop": next_hop,
                "full_path": path,
                "hops_remaining": len(path) - 2,
                "steps": {
                    "reserve": reserve_result,
                },
            }

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"  ❌ Internal Error in route_box: {e}\n{error_trace}")
            return {
                "status": "error",
                "error": str(e),
                "traceback": error_trace
            }

    def get_api_url(self) -> Optional[str]:
        """Get the URL where this module's REST API is accessible."""
        return self.url

    def get_ogm(self) -> OGM:
        """Get the OGM instance used by this module."""
        return self.ogm
