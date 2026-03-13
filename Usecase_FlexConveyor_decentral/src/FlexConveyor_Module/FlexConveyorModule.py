import heapq
import json
import threading
import time
from typing import Optional, Any, Dict

import requests
import uvicorn
import aas_middleware as aas
from graph_db_interface.utils.iri import IRI

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

        def receive(arg: str | None = None) -> dict:
            if not arg:
                return {
                    "status": "error",
                    "error": "Missing required workflow query parameter: arg",
                }

            box_iri, destination_iri = arg, None
            try:
                parsed = json.loads(arg)
                if isinstance(parsed, dict):
                    box_iri = parsed.get("box_iri") or parsed.get("box") or box_iri
                    destination_iri = parsed.get("destination_iri") or parsed.get("destination")
            except Exception:
                pass

            return self.receive(str(box_iri), str(destination_iri) if destination_iri else None)

        def has_parcel() -> dict:
            return self.has_parcel()

        self.mw.workflow()(receive)
        self.mw.workflow()(has_parcel)

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
    #  Core workflows
    # ------------------------------------------------------------------

    def receive(self, box_iri: str, destination_iri: str | None = None) -> dict:
        """Receive a box at this module.

        1. Ensures the box exists in GraphDB.
        2. Transfers ``hasPossession`` / ``isPossessedBy`` to this module
           (removes from any previous owner).
        3. Updates the box state to *InTransit* (or *Delivered* if this is
           the destination).
        4. If not at destination, triggers :meth:`route_box` to forward the
           box along the shortest path.


        Args:
            box_iri: IRI string of the box being received.
            destination_iri: Optional IRI string of the destination module.

        Returns:
            dict describing the outcome (delivered / routed / received_no_destination).
        """
        FC = "http://w3id.org/circularfactory/FlexConveyor#"
        INST = "http://w3id.org/circularfactory/FlexConveyorInstances"
        named_graph = IRI(INST)

        box = IRI(box_iri) if not isinstance(box_iri, IRI) else box_iri

        has_possession = IRI(f"{FC}hasPossession")
        is_possessed_by = IRI(f"{FC}isPossessedBy")
        has_state_prop = IRI(f"{FC}hasState")
        has_destination = IRI(f"{FC}hasDestination")
        has_origin = IRI(f"{FC}hasOrigin")
        in_transit = IRI(f"{FC}InTransit")
        delivered = IRI(f"{FC}Delivered")
        rdf_type = IRI("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        box_class = IRI(f"{FC}Box")

        destination_arg = (
            IRI(destination_iri)
            if destination_iri is not None and not isinstance(destination_iri, IRI)
            else destination_iri
        )

        print(
            f"\n📦 [{self.module_id}] Receiving box: {box}"
            + (f" (destination override: {destination_arg})" if destination_arg else "")
        )

        # 1. Ensure the box exists in GraphDB
        existing = self.ogm.db.triples_get(sub=box, pred=rdf_type, obj=box_class)
        if not existing:
            self.ogm.db.triples_add(
                [(box, rdf_type, box_class)],
                check_exist=False,
                named_graph=named_graph,
            )
            print(f"  → Created box {box} in knowledge graph")

        # Optional injection behavior: upsert destination (and origin if missing).
        if destination_arg is not None:
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

            origin_triples = self.ogm.db.triples_get(sub=box, pred=has_origin)
            if not origin_triples:
                self.ogm.db.triples_add(
                    [(box, has_origin, self.module_id)],
                    check_exist=False,
                    named_graph=named_graph,
                )

        # 2. Remove box from any previous module's hasPossession
        old_possessions = self.ogm.db.triples_get(pred=has_possession, obj=box)
        if old_possessions:
            self.ogm.db.triples_delete(
                old_possessions, check_exist=False, named_graph=named_graph
            )
            old_owners = [str(t[0]) for t in old_possessions]
            print(f"  → Removed box from previous owner(s): {old_owners}")

        # Remove old isPossessedBy
        old_possessed = self.ogm.db.triples_get(sub=box, pred=is_possessed_by)
        if old_possessed:
            self.ogm.db.triples_delete(
                old_possessed, check_exist=False, named_graph=named_graph
            )

        # 3. Add this module as the new possessor
        self.ogm.db.triples_add(
            [
                (self.module_id, has_possession, box),
                (box, is_possessed_by, self.module_id),
            ],
            check_exist=False,
            named_graph=named_graph,
        )
        print(f"  → Box is now at module {self.module_id}")

        # 4. Update box state — remove old state first
        old_states = self.ogm.db.triples_get(sub=box, pred=has_state_prop)
        if old_states:
            self.ogm.db.triples_delete(
                old_states, check_exist=False, named_graph=named_graph
            )

        # 5. Check if this module is the destination
        dest_triples = self.ogm.db.triples_get(sub=box, pred=has_destination)
        destination = dest_triples[0][2] if dest_triples else None

        if destination and str(destination) == str(self.module_id):
            # Box has arrived at its final destination
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

        # Box is in transit
        self.ogm.db.triples_add(
            [(box, has_state_prop, in_transit)],
            check_exist=False,
            named_graph=named_graph,
        )
        print(f"  📍 Box {box} is now IN TRANSIT at {self.module_id}")

        # 6. Trigger routing to forward the box towards its destination
        if destination:
            print(f"  🔄 Routing box towards destination: {destination}")
            routing_result = self.route_box(str(box), str(destination))
            return {
                "status": "routed",
                "module": str(self.module_id),
                "box": str(box),
                "destination": str(destination),
                "routing": routing_result,
            }

        print(f"  ⚠️  No destination set for box {box} — box will stay here")
        return {
            "status": "received_no_destination",
            "module": str(self.module_id),
            "box": str(box),
        }

    def route_box(self, box_iri: str, destination_iri: str) -> dict:
        """Route a box to its destination using Dijkstra's shortest path."""
        try:
            source = str(self.module_id)
            target = destination_iri

            print(f"\n🗺️  [{self.module_id}] Computing route: {source} → {target}")

            # Always refresh topology: at startup, modules are instantiated sequentially,
            # so early-started modules may have built a partial adjacency matrix.
            self.discover_connections_and_services()

            path = self._dijkstra_shortest_path(source, target)

            if not path:
                print(f"  ❌ No route found from {source} to {target}")
                return {
                    "status": "no_route",
                    "source": source,
                    "destination": target,
                    "path": [],
                    "internal_adj": [[str(x) for x in r] for r in self.adj]
                }

            if len(path) < 2:
                # Already at destination (shouldn't normally happen — receive handles it)
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

            # Forward the box to the next module by calling its receive workflow.
            # aas_middleware exposes workflows under /workflows/<name>/execute and
            # passes positional args via the `arg` query parameter.
            receive_workflow_url = f"{next_url}/workflows/receive/execute"
            print(f"  📡 Forwarding box to {next_hop} via {receive_workflow_url}")

            response = requests.post(
                receive_workflow_url,
                # Query-param based workflow invocation (single-arg workflow).
                params={"arg": box_iri},
                timeout=30,
            )

            if response.status_code >= 400:
                # Include body to make downstream errors debuggable.
                return {
                    "status": "downstream_error",
                    "next_hop": next_hop,
                    "full_path": path,
                    "http_status": response.status_code,
                    "http_text": response.text,
                    "receive_url": receive_workflow_url,
                }

            result = response.json() if response.text else {"status": "ok"}

            print(f"  ✅ Box forwarded successfully to {next_hop}")
            return {
                "status": "forwarded",
                "next_hop": next_hop,
                "full_path": path,
                "hops_remaining": len(path) - 2,
                "response": result,
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
