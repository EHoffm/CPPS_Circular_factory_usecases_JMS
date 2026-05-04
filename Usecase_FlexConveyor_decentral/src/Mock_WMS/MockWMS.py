"""Mock Warehouse Management System (WMS) for FlexConveyor simulation.

The WMS is responsible for:
- Spawning boxes into the system from a random free module to a random destination
- Accepting delivered boxes from the system
- Automatically spawning new boxes after initialization and after each delivery
"""

import json
import logging
import threading
import time
from typing import Optional, Dict, Any, List
import random

from graph_db_interface.utils.iri import IRI
from pydantic import BaseModel

from kapps_ogm import OGM, ClassScope

# Absolute import - works whether run as script or installed package
from semantic_service import Service, Workflow, WorkflowPayload, WorkflowResponse

FC = "http://w3id.org/circularfactory/FlexConveyor#"


class MockWMS(Service):
    """
    Mock Warehouse Management System entity.

    Runs its own middleware instance with REST API to expose:
    - spawn_box workflow: Creates and injects a box into the system
    - accept_box workflow: Accepts a delivered box from the system

    Automatically spawns boxes:
    - Once after initialization
    - Every time a box is accepted
    """

    NAMED_GRAPH = IRI("http://w3id.org/circularfactory/FlexConveyorInstances")
    _WMS_SERVICE_ID = IRI("http://w3id.org/circularfactory/FlexConveyorInstances#WMS")

    def __init__(
        self,
        ogm: OGM,
        number_of_boxes: Optional[int] = 1,
        host: str = "0.0.0.0",
    ):
        """Initialize the WMS."""
        if ogm is None:
            raise ValueError("OGM instance is required to initialize MockWMS")

        self.box_counter = 0
        self.box_counter_lock = threading.Lock()
        self.spawn_after_accept = True
        self.initialized = False
        self.number_of_boxes: int = number_of_boxes

        super().__init__(service_id=self._WMS_SERVICE_ID, ogm=ogm, host=host)

    @property
    def wms_id(self) -> IRI:
        """Alias for service_id, preserving the original interface."""
        return self.service_id

    def on_start(self) -> None:
        """Spawn the initial batch of boxes after the server is ready."""
        if self.spawn_after_accept:
            threading.Thread(
                target=self._spawn_initial_boxes, daemon=True, name="InitialBoxSpawn"
            ).start()
        self.initialized = True

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
        spawn_workflow = self.workflows["spawn"]

        result = spawn_workflow(
            **{
                IRI(f"{FC}refersToBox").lined: box_iri,
                IRI(f"{FC}refersToOriginModule").lined: origin_iri,
                IRI(f"{FC}refersToDestinationModule").lined: destination_iri,
            }
        )

        # Parse WorkflowResponse
        if result.status == "spawned":
            self.logger.info(f"Box spawned successfully")
        else:
            self.logger.error(f"Spawn failed: {result.message}")

    @Service.workflow(workflow_class=IRI(f"{FC}SpawnBoxWorkflow"), key="spawn")
    def spawn_box_workflow(self, payload: WorkflowPayload) -> WorkflowResponse:
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
        named_graph = self.named_graph
        box_iri = IRI(getattr(payload, IRI(f"{FC}refersToBox").lined))
        origin_iri = IRI(getattr(payload, IRI(f"{FC}refersToOriginModule").lined))
        destination_iri = IRI(
            getattr(payload, IRI(f"{FC}refersToDestinationModule").lined)
        )

        # Get the spawn workflow to access its response_model
        response_model: WorkflowResponse = self.workflows["spawn"].response_model

        try:
            box_data = {
                "id": box_iri,
                IRI(f"{FC}hasState"): [{"id": IRI(f"{FC}InTransit")}],
                IRI(f"{FC}hasOrigin"): [{"id": origin_iri}],
                IRI(f"{FC}hasDestination"): [{"id": destination_iri}],
            }
            box_scope = ClassScope.from_data_dict(box_data)
            self.ogm.create(
                class_iri=IRI(f"{FC}Box"),
                class_scope=box_scope,
                data=box_data,
                named_graph=named_graph,
                persist=True,
            )

            # Set ownership to origin module
            self.ogm.db.triples_add(
                [
                    (origin_iri, IRI(f"{FC}hasPossession"), box_iri),
                    (box_iri, IRI(f"{FC}isPossessedBy"), origin_iri),
                ],
                check_exist=False,
                named_graph=named_graph,
            )

            # Call origin module's receive workflow
            receive_workflow = Workflow.fetch_remote_workflow(
                resource_instance=origin_iri,
                workflow_class=IRI(f"{FC}ReceiveWorkflow"),
                ogm=self.ogm,
                logger=self.logger_parent.getChild(
                    f"RemoteWorkflow@{origin_iri.fragment}-ReceiveWorkflow"
                ),
            )

            response = receive_workflow(**{IRI(f"{FC}refersToBox").lined: box_iri})

            return response_model(
                status_code=200,
                status="spawned",
                message="Box spawned and injected into origin module successfully",
                content=json.dumps(
                    {
                        IRI(f"{FC}response_box").lined: box_iri,
                        IRI(f"{FC}response_origin").lined: origin_iri,
                        IRI(f"{FC}response_destination").lined: destination_iri,
                        "receive_response": response.model_dump(),
                    }
                ),
            )

        except Exception as e:
            return response_model(
                status_code=500,
                status="spawn_failed",
                message=f"Failed to spawn box: {str(e)}",
                content=json.dumps({"error": str(e)}),
            )

    @Service.workflow(workflow_class=IRI(f"{FC}AcceptBoxWorkflow"), key="accept")
    def accept_box_workflow(self, payload: WorkflowPayload) -> WorkflowResponse:
        """
        Accept box workflow: Mark box as delivered and remove from system.

        Steps:
        1. Verify box is possessed by WMS
        2. Update hasState = Delivered
        3. Remove ownership triples (hasPossession/isPossessedBy)
        4. Trigger auto-spawn if enabled
        """
        named_graph = self.named_graph

        response_model = self.workflows["accept"].response_model

        try:
            box_iri = IRI(getattr(payload, IRI(f"{FC}refersToBox").lined))
            wms = self.wms_id

            has_state = IRI(f"{FC}hasState")
            delivered = IRI(f"{FC}Delivered")
            has_possession = IRI(f"{FC}hasPossession")
            is_possessed_by = IRI(f"{FC}isPossessedBy")
            in_transit = IRI(f"{FC}InTransit")

            # Verify ownership
            possession_check = self.ogm.db.triples_get(
                sub=box_iri, pred=is_possessed_by
            )
            if not possession_check or str(possession_check[0][2]) != str(wms):
                return response_model(
                    status_code=400,
                    status="not_possessed_by_wms",
                    message="Box is not possessed by WMS",
                    content=json.dumps({IRI(f"{FC}response_box").lined: box_iri}),
                )

            # Update state to Delivered
            state_updated = self.ogm.db.triple_update(
                old_triple=(box_iri, has_state, in_transit),
                new_triple=(box_iri, has_state, delivered),
                named_graph=named_graph,
            )

            # Remove ownership
            self.ogm.db.triples_delete(
                [
                    (wms, has_possession, box_iri),
                    (box_iri, is_possessed_by, wms),
                ],
                check_exist=False,
                named_graph=named_graph,
            )

            self.logger.info(f"Box {IRI(box_iri).fragment} accepted and delivered!")

            # Auto-spawn next box
            if self.spawn_after_accept:
                threading.Thread(
                    target=self._spawn_random_box, daemon=True, name="AutoSpawn"
                ).start()

            return response_model(
                status_code=200,
                status="accepted",
                message="Box accepted and marked as delivered",
                content=json.dumps({IRI(f"{FC}response_box").lined: box_iri}),
            )

        except Exception as e:
            return response_model(
                status_code=500,
                status="accept_failed",
                message=f"Failed to accept box: {str(e)}",
                content=json.dumps(
                    {IRI(f"{FC}response_box").lined: box_iri, "error": str(e)}
                ),
            )
