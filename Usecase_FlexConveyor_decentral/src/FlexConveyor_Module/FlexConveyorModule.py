import heapq
import logging
import json
import threading
import time
from collections import deque
from typing import Optional, Any, Dict
import semantic_middleware as smw
from graph_db_interface import IRI

from kapps_ogm import OGM, ClassScope
from semantic_service import Service, Workflow, WorkflowPayload, WorkflowResponse

FC = "http://w3id.org/circularfactory/FlexConveyor#"


class FlexConveyor(Service):
    """Represents a FlexConveyor module in the system.

    Each instance runs a separate middleware instance with its own REST API server
    on a unique port. Modules can communicate with each other via HTTP calls to
    their REST endpoints.

    Designed to support distributed systems - modules can run on different hosts
    and machines.
    """

    NAMED_GRAPH = IRI("http://w3id.org/circularfactory/FlexConveyorInstances")

    def __init__(
        self,
        module_id: IRI,
        ogm: OGM,
        host: str = "0.0.0.0",
        concurrent_guard_override: bool = True,
    ):
        """Initialize one FlexConveyor module."""
        if ogm is None:
            raise ValueError(
                "OGM instance is required to initialize FlexConveyor module"
            )

        self.concurrent_guard_override = concurrent_guard_override
        self.topology_graph: Dict[str, list] = {}
        self.accessible_at_by_module: dict[IRI, str | None] = {}
        self._reserve_queue: deque[dict[str, Any]] = deque()
        self._reserve_queue_lock = threading.Lock()
        self._reserve_worker_running = False
        self.routing_table: Dict[str, str] = {}

        super().__init__(service_id=module_id, ogm=ogm, host=host)

    @property
    def module_id(self) -> IRI:
        """Alias for service_id, preserving the original interface."""
        return self.service_id

    def _setup_middleware_data_model(self) -> None:
        """
        Load the FlexConveyor module's OGM data node into the middleware.
        Falls back to manual DataModel population if schema introspection fails.
        """
        property_chains = [
            [IRI(f"{FC}hasConnection"), IRI(f"{FC}connectsTo")],
            [IRI(f"{FC}hasConnection"), IRI(f"{FC}hasDirection")],
            [IRI(f"{FC}hasConnection"), IRI(f"{FC}onPort")],
        ]
        class_scope = ClassScope.from_property_chains(property_chains)

        try:
            instance = self.ogm.fetch(
                instance_iri=self.service_id, class_scope=class_scope, materialize=True
            ).instance
        except Exception as e:
            msg = f"Failed to fetch instance for {self.service_id} from OGM: {e}"
            self.logger.error(msg)

        try:
            self.mw.load_data_model(
                name=str(self.service_id),
                data_model=smw.DataModel.from_models(instance),
                persist_instances=True,
            )
        except Exception as e:
            msg = f"Failed to load data model for {self.service_id} to middleware: {e}"
            self.logger.error(msg)
            raise RuntimeError(msg)

        try:
            self.mw.generate_rest_api_for_data_model(str(self.service_id))
        except Exception as e:
            msg = f"Failed to generate REST API for {self.service_id}: {e}"
            self.logger.error(msg)
            raise RuntimeError(msg)

    def on_start(self) -> None:
        """Discover remote workflow proxies and build the routing table."""
        try:
            self._discover_remote_workflows()
            self._populate_routing_table()
        except Exception as e:
            self.logger.warning(
                f"Remote workflow discovery at startup failed: {e}. "
                "Will retry lazily on first workflow invocation."
            )

    @staticmethod
    def _direction_to_index(direction: str | None) -> int | None:
        if not direction:
            return None
        direction_map = {
            f"{FC}North": 1,
            f"{FC}East": 2,
            f"{FC}South": 3,
            f"{FC}West": 4,
        }
        return direction_map.get(str(direction))

    def _discover_remote_workflows(self):
        property_chains = [
            [
                IRI(f"{FC}hasConnection"),
                IRI(f"{FC}connectsTo"),
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
            IRI(f"{FC}hasConnection").lined,
        ):
            neighbor_module_iris.add(
                getattr(
                    connection,
                    IRI(f"{FC}connectsTo").lined,
                )[0].id
            )

        for module_iri in neighbor_module_iris:
            self.remote_workflows[module_iri] = {
                "receive": Workflow.fetch_remote_workflow(
                    resource_instance=module_iri,
                    workflow_class=IRI(f"{FC}ReceiveWorkflow"),
                    ogm=self.ogm,
                    logger=self.logger_parent.getChild(
                        f"RemoteWorkflow@{module_iri.fragment}-ReceiveWorkflow"
                    ),
                ),
                "reserve": Workflow.fetch_remote_workflow(
                    resource_instance=module_iri,
                    workflow_class=IRI(f"{FC}ReserveWorkflow"),
                    ogm=self.ogm,
                    logger=self.logger_parent.getChild(
                        f"RemoteWorkflow@{module_iri.fragment}-ReserveWorkflow"
                    ),
                ),
                "convey": Workflow.fetch_remote_workflow(
                    resource_instance=module_iri,
                    workflow_class=IRI(f"{FC}ConveyWorkflow"),
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

    @Service.workflow(workflow_class=IRI(f"{FC}ReserveWorkflow"), key="reserve")
    def reserve_workflow(self, payload: WorkflowPayload) -> WorkflowResponse:
        """
        Implements http://w3id.org/circularfactory/FlexConveyor#ReserveWorkflow

        Payload structure:
            - box_iri: IRI of the box to be conveyed
            - source_module_iri: IRI of the module from which the box is to be conveyed

        Response structure:
            - status_code: HTTP status code indicating success or type of failure
            - status: Short string indicating result ("success", "timeout", "error", etc.)
            - message: Human-readable message describing the result
            - data: Optional field for additional response data, encoded as a JSON string
            - response_module: IRI of the module processing the request (this module)
            - response_box: IRI of the box involved in the request
            - response_module: IRI of the source module from the request
            - response_source_module: IRI of the source module from the request

        """
        box_iri = IRI(getattr(payload, IRI(f"{FC}refersToBox").lined))
        source_module_iri = IRI(
            getattr(payload, IRI(f"{FC}refersToSourceModule").lined)
        )

        response_model = self.workflows.get("reserve").response_model

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
            else response_model(
                status_code=500,
                status="queue_no_result",
                message="Reserve queue processing returned no result",
                content=json.dumps(
                    {IRI(f"{FC}response_module").lined: str(self.module_id)}
                ),
            )
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

                response_model = self.workflows.get("reserve").response_model
                result = response_model(
                    status_code=500,
                    status="error",
                    message=f"Reserve queue processing failed: {str(e)}",
                    content=json.dumps(
                        {
                            IRI(f"{FC}response_module").lined: str(self.module_id),
                            "traceback": traceback.format_exc(),
                        }
                    ),
                )

            request["result"] = result
            request["event"].set()

    def _handle_single_reserve_request(
        self, box_iri: str, source_module_iri: str, allow_override: bool = True
    ) -> WorkflowResponse:
        """Handle one reserve request: wait until free, then call source convey."""
        response_model = self.workflows["reserve"].response_model

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
            return response_model(
                status_code=408,
                status="timeout",
                message=f"Module did not become free within {timeout_seconds}s timeout period",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_module").lined: str(self.module_id),
                        IRI(f"{FC}response_box").lined: str(box_iri),
                        IRI(f"{FC}response_source_module").lined: str(
                            source_module_iri
                        ),
                    }
                ),
            )

        response = self.remote_workflows[IRI(source_module_iri)]["convey"](
            **{
                IRI(f"{FC}refersToBox").lined: box_iri,
                IRI(f"{FC}refersToDestinationModule").lined: str(self.module_id),
            }
        )

        if response.status_code >= 400:
            if response.status == "ownership_transfer_failed" and allow_override:
                self.logger.warning(
                    f"Convey-on-source failed due to ownership transfer, but concurrent guard override is enabled. Disabling guard to proceed with simulation."
                )
                return self._handle_single_reserve_request(
                    box_iri=box_iri,
                    source_module_iri=source_module_iri,
                    allow_override=False,
                )

            self.logger.error(
                f"Convey-on-source failed with HTTP {response.status_code}"
            )
            return response_model(
                status_code=500,
                status="remote_convey_failed",
                message=f"Remote convey call to source module failed",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_module").lined: str(self.module_id),
                        IRI(f"{FC}response_box").lined: str(box_iri),
                        IRI(f"{FC}response_source_module").lined: str(
                            source_module_iri
                        ),
                        "remote_details": {
                            "http_status": response.status_code,
                            "remote_status": response.status,
                            "remote_message": response.message,
                        },
                    }
                ),
            )

        convey_result = response.model_dump()
        self.logger.info(
            f"Convey-on-source from {source_module_iri} to {self.module_id} response: {convey_result}"
        )
        return response_model(
            status_code=200,
            status="reserved_and_pulled",
            message="Box reserved and pulled from source module successfully",
            content=json.dumps(
                {
                    IRI(f"{FC}response_module").lined: str(self.module_id),
                    IRI(f"{FC}response_box").lined: str(box_iri),
                    IRI(f"{FC}response_source_module").lined: str(source_module_iri),
                    "convey_details": convey_result,
                }
            ),
        )

    @Service.workflow(workflow_class=IRI(f"{FC}ConveyWorkflow"), key="convey")
    def convey_workflow(
        self,
        payload: WorkflowPayload,
    ) -> WorkflowResponse:
        """
        Implements http://w3id.org/circularfactory/FlexConveyor#ConveyWorkflow
        """
        box_iri: str = getattr(payload, IRI(f"{FC}refersToBox").lined)
        destination_module_iri = getattr(
            payload, IRI(f"{FC}refersToDestinationModule").lined
        )

        response_model = self.workflows["convey"].response_model

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
            self.transfer_box_ownership(
                str(box), str(self.module_id), str(destination_module)
            )
        except Exception as e:
            self.logger.error(f"Convey ownership transfer failed: {e}")
            return response_model(
                status_code=500,
                status="ownership_transfer_failed",
                message="Failed to transfer box ownership in knowledge graph",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_box").lined: str(box),
                        IRI(f"{FC}response_from_module").lined: str(self.module_id),
                        IRI(f"{FC}response_to_module").lined: str(destination_module),
                        "error": str(e),
                    }
                ),
            )

        # Wait 1 second to simulate transit time
        self.logger.info(f"Waiting 5 seconds for transit...")
        time.sleep(5)

        def _call_receive_in_background() -> None:
            try:
                response = self.remote_workflows[IRI(destination_module_iri)][
                    "receive"
                ](**{IRI(f"{FC}refersToBox").lined: box_iri})
                if response.status_code >= 400:
                    self.logger.error(
                        f"Background destination receive failed: [{response.status_code}] {response.status} - {response.message}"
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

        return response_model(
            status_code=200,
            status="conveyed_receive_started",
            message="Box conveyed successfully, receive workflow started",
            content=json.dumps(
                {
                    IRI(f"{FC}response_box").lined: str(box),
                    IRI(f"{FC}response_from_module").lined: str(self.module_id),
                    IRI(f"{FC}response_to_module").lined: str(destination_module),
                    IRI(f"{FC}response_receive_status").lined: "started_async",
                }
            ),
        )

    @Service.workflow(workflow_class=IRI(f"{FC}ReceiveWorkflow"), key="receive")
    def receive_workflow(self, payload: WorkflowPayload) -> WorkflowResponse:
        """
        Implements http://w3id.org/circularfactory/FlexConveyor#ReceiveWorkflow
        """
        box_iri = IRI(getattr(payload, IRI(f"{FC}refersToBox").lined))

        # Get the receive workflow to access its response_model
        response_model = self.workflows["receive"].response_model

        if not self.remote_workflows:
            self._discover_remote_workflows()

        if not self.routing_table:
            self._populate_routing_table()

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
        posessor_iri = IRI(getattr(box_instance, IRI(f"{FC}isPossessedBy").lined)[0].id)
        destination_iri = IRI(
            getattr(box_instance, IRI(f"{FC}hasDestination").lined)[0].id
        )
        state_iri = IRI(getattr(box_instance, IRI(f"{FC}hasState").lined)[0].id)

        if not posessor_iri == self.module_id:
            self.logger.error(
                f"Box {box_iri} is not possessed by this module. Current possessor: {posessor_iri}"
            )
            return response_model(
                status_code=400,
                status="wrong_possession",
                message=f"Box is not possessed by this module",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_module").lined: str(self.module_id),
                        IRI(f"{FC}response_box").lined: str(box_iri),
                        "actual_possessor": str(posessor_iri),
                    }
                ),
            )

        if not state_iri == IRI(f"{FC}InTransit"):
            self.logger.error(
                f"Box {box_iri} is not in 'InTransit' state. Current state: {state_iri}"
            )
            return response_model(
                status_code=400,
                status="invalid_state",
                message=f"Box is not in InTransit state",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_module").lined: str(self.module_id),
                        IRI(f"{FC}response_box").lined: str(box_iri),
                        "actual_state": str(state_iri),
                        "expected_state": f"{FC}InTransit",
                    }
                ),
            )

        if destination_iri == self.module_id:
            # Transfer to WMS and call WMS's accept_box workflow
            self._deliver_to_wms(str(box_iri))

            return response_model(
                status_code=200,
                status="delivered",
                message="Box delivered to final destination (WMS)",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_module").lined: str(self.module_id),
                        IRI(f"{FC}response_box").lined: str(box_iri),
                        IRI(f"{FC}response_action").lined: "delivered",
                    }
                ),
            )

        next_hop = self.routing_table.get(destination_iri)

        self.logger.info(f"Initiating pull-handshake transfer to {next_hop}")

        # Step 1: Reserve
        response = self.remote_workflows[next_hop]["reserve"](
            **{
                IRI(f"{FC}refersToBox").lined: box_iri,
                IRI(f"{FC}refersToSourceModule").lined: str(self.module_id),
            }
        )

        if response.status_code >= 400:
            self.logger.error(f"Reserve failed with HTTP {response.status_code}")
            return response_model(
                status_code=500,
                status="remote_reserve_failed",
                message="Remote reserve call to next hop failed",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_module").lined: str(self.module_id),
                        IRI(f"{FC}response_box").lined: str(box_iri),
                        IRI(f"{FC}response_destination").lined: str(destination_iri),
                        IRI(f"{FC}response_next_hop").lined: next_hop,
                        "remote_details": {
                            "http_status": response.status_code,
                            "remote_status": response.status,
                            "remote_message": response.message,
                        },
                    }
                ),
            )

        # Parse the WorkflowResponse
        reserve_status = response.status
        if reserve_status != "reserved_and_pulled":
            self.logger.warning(f"Transfer did not complete: {response.message}")
            return response_model(
                status_code=500,
                status="reserve_or_pull_failed",
                message="Reserve succeeded but pull operation failed",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_module").lined: str(self.module_id),
                        IRI(f"{FC}response_box").lined: str(box_iri),
                        IRI(f"{FC}response_destination").lined: str(destination_iri),
                        IRI(f"{FC}response_next_hop").lined: next_hop,
                        "reserve_response": response.model_dump(),
                    }
                ),
            )

        self.logger.info(f"Pull-handshake transfer completed to {next_hop}")

        return response_model(
            status_code=200,
            status="routed",
            message="Box routed to next hop successfully",
            content=json.dumps(
                {
                    IRI(f"{FC}response_module").lined: str(self.module_id),
                    IRI(f"{FC}response_box").lined: str(box_iri),
                    IRI(f"{FC}response_action").lined: "routed",
                    IRI(f"{FC}response_destination").lined: str(destination_iri),
                    IRI(f"{FC}response_next_hop").lined: next_hop,
                }
            ),
        )

    def _deliver_to_wms(self, box_iri: str) -> None:
        """
        Deliver a box to the WMS by transferring ownership and calling WMS's accept_box workflow.

        Args:
            box_iri: IRI of the box to deliver
        """
        WMS_IRI = IRI("http://w3id.org/circularfactory/FlexConveyorInstances#WMS")

        # Call WMS's accept_box workflow
        try:
            # Transfer ownership from this module to WMS
            self.transfer_box_ownership(
                box_iri,
                str(self.module_id),
                WMS_IRI,
            )

            wms_accept_workflow = Workflow.fetch_remote_workflow(
                resource_instance=IRI(WMS_IRI),
                workflow_class=IRI(f"{FC}AcceptBoxWorkflow"),
                ogm=self.ogm,
            )

            response = wms_accept_workflow(**{IRI(f"{FC}refersToBox").lined: box_iri})

            if response.status_code >= 400:
                self.logger.error(
                    f"WMS accept_box workflow failed: {response.status_code}"
                )
            else:
                self.logger.info(f"Box {box_iri} delivered to WMS!")

        except Exception as e:
            self.logger.error(f"Error calling WMS accept_box workflow: {e}")

    def transfer_box_ownership(
        self, box: str, origin_module: str, destination_module: str
    ) -> None:
        named_graph = self.named_graph

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
