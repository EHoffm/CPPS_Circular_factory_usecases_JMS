from typing import Optional, Any, Dict
import semantic_middleware as smw
from graph_db_interface import IRI
from pydantic import BaseModel
import requests

from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope

import logging


class Workflow:
    workflow_method: callable
    workflow_class: IRI
    resource_instance: IRI
    payload_model: Optional[BaseModel] = None
    _workflow_url: str = None
    name: str = None
    _workflow_instance: IRI = None
    _middleware: smw.Middleware = None
    _is_remote: bool = False

    def __init__(
        self,
        workflow_method: callable,
        workflow_class: IRI,
        resource_instance: IRI,
        payload_model: Optional[BaseModel] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.workflow_method = workflow_method
        self.workflow_class = IRI(workflow_class)
        self.resource_instance = IRI(resource_instance)
        self.payload_model = payload_model
        self.logger = logger or logging.getLogger(
            f"Workflow-{self.resource_instance.fragment}-{self.name}"
        )

        self.name = self.workflow_method.__qualname__.split(".")[-1]

    @classmethod
    def fetch_remote_workflow(
        cls,
        resource_instance: IRI,
        workflow_class: IRI,
        payload_model: Optional[BaseModel],
        ogm: OGM,
        logger: Optional[logging.Logger] = None,
    ) -> "Workflow":
        query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT DISTINCT ?workflow_url
        WHERE {{
            {{
                <{resource_instance}> <http://w3id.org/circularfactory/FlexConveyor#hasWorkflow> ?workflow .
            }}
            UNION
            {{
                ?workflow <http://w3id.org/circularfactory/FlexConveyor#isWorkflowOf> <{resource_instance}> .
            }}
            ?workflow rdf:type <{workflow_class}> .
            ?workflow <http://w3id.org/circularfactory/FlexConveyor#accessibleAt> ?workflow_url .
        }}
        """
        results = ogm.db.query(query, convert_bindings=True)
        workflows = [
            result["workflow_url"] for result in results["results"]["bindings"]
        ]
        if not workflows:
            raise ValueError(
                f"No workflow of class {workflow_class} found for resource instance {resource_instance}"
            )
        if len(workflows) > 1:
            raise ValueError(
                f"Multiple workflows of class {workflow_class} found for resource instance {resource_instance}, expected only one."
            )
        workflow_url = workflows[0]

        def remote_method(payload: BaseModel):
            return requests.post(
                workflow_url,
                json=payload.model_dump(),
                timeout=None,
            )

        logger = logger or logging.getLogger(
            f"Workflow-Remote@{resource_instance.fragment}-{workflow_class.fragment}"
        )

        workflow = cls(
            workflow_method=remote_method,
            workflow_class=workflow_class,
            resource_instance=resource_instance,
            payload_model=payload_model,
            logger=logger,
        )
        workflow._workflow_url = workflow_url
        workflow._is_remote = True
        return workflow

    def register_in_middleware(self, mw: smw.Middleware):
        if self._is_remote:
            raise ValueError("Remote workflows cannot be registered in middleware.")

        self._middleware = mw
        mw.workflow()(self.workflow_method)
        self.logger.info(f"Registered in middleware with name '{self.name}'")

    def register_in_graph_db(self, host_url: str, ogm: OGM, named_graph: IRI = None):
        if self._is_remote:
            raise ValueError("Remote workflows cannot be registered in graph database.")
        if not self._middleware:
            raise ValueError(
                "Middleware must be registered before registering workflow in graph database."
            )

        self._workflow_url = f"{host_url}/workflows/{self.name}/execute"

        property_chains = [
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#isWorkflowOf"),
            ],
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
        ]
        class_scope = ClassScope.from_property_chains(property_chains)

        data = {
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"): [
                self._workflow_url
            ],
            IRI("http://w3id.org/circularfactory/FlexConveyor#isWorkflowOf"): [
                {"id": self.resource_instance}
            ],
        }

        workflow_node = ogm.create(
            class_iri=self.workflow_class,
            class_scope=class_scope,
            data=data,
            named_graph=named_graph,
        )
        self._workflow_instance = workflow_node.id
        self.logger.info(
            f"Registered in knowledge graph with IRI '{self._workflow_instance}' and URL '{self._workflow_url}'"
        )

    def deregister_in_middleware(self, ogm: OGM):
        if self._is_remote:
            raise ValueError("Remote workflows cannot be deregistered.")
        self._workflow_instance = None
        self.logger.warning(f"Workflow middleware deregistration not yet implemented")

    def deregister_in_graph_db(self, ogm: OGM, named_graph: IRI = None):
        """Remove workflow registration from the knowledge graph."""
        if self._is_remote:
            raise ValueError("Remote workflows cannot be cleaned from graph database.")
        if not self._workflow_instance:
            self.logger.info("Workflow not registered in graph, skipping cleanup")
            return

        self.logger.warning(f"Workflow GraphDB deregistration not yet implemented")

    def __call__(self, payload: BaseModel) -> dict[str, Any]:
        if not isinstance(payload, self.payload_model):
            raise ValueError(
                f"Invalid payload type, expected {self.payload_model}, got {type(payload)}"
            )
        self.logger.info(f"Invoking with payload: {payload}")
        response = self.workflow_method(payload)
        self.logger.info(f"Completed with response: {response}")
        return response
