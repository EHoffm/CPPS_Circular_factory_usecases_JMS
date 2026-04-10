from typing import Optional, Any, Dict
import semantic_middleware as smw
from graph_db_interface import IRI
from pydantic import BaseModel
import requests

from kapps_ogm.ogm import OGM
from kapps_ogm.utils.class_scope import ClassScope

import logging


class Service:
    service_method: callable
    service_class: IRI
    resource_instance: IRI
    payload_model: Optional[BaseModel] = None
    _service_url: str = None
    name: str = None
    _service_instance: IRI = None
    _middleware: smw.Middleware = None
    _is_remote: bool = False

    def __init__(
        self,
        service_method: callable,
        service_class: IRI,
        resource_instance: IRI,
        payload_model: Optional[BaseModel] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.service_method = service_method
        self.service_class = IRI(service_class)
        self.resource_instance = IRI(resource_instance)
        self.payload_model = payload_model
        self.logger = logger or logging.getLogger(
            f"Service-{self.resource_instance.fragment}-{self.name}"
        )

        self.name = self.service_method.__qualname__.split(".")[-1]

    @classmethod
    def fetch_remote_service(
        cls,
        resource_instance: IRI,
        service_class: IRI,
        payload_model: Optional[BaseModel],
        ogm: OGM,
        logger: Optional[logging.Logger] = None,
    ) -> "Service":
        query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT DISTINCT ?service_url
        WHERE {{
            {{
                <{resource_instance}> <http://w3id.org/circularfactory/FlexConveyor#hasService> ?service .
            }}
            UNION
            {{
                ?service <http://w3id.org/circularfactory/FlexConveyor#isServiceOf> <{resource_instance}> .
            }}
            ?service rdf:type <{service_class}> .
            ?service <http://w3id.org/circularfactory/FlexConveyor#accessibleAt> ?service_url .
        }}
        """
        results = ogm.db.query(query, convert_bindings=True)
        services = [result["service_url"] for result in results["results"]["bindings"]]
        if not services:
            raise ValueError(
                f"No service of class {service_class} found for resource instance {resource_instance}"
            )
        if len(services) > 1:
            raise ValueError(
                f"Multiple services of class {service_class} found for resource instance {resource_instance}, expected only one."
            )
        service_url = services[0]

        def remote_method(payload: BaseModel):
            return requests.post(
                service_url,
                json=payload.model_dump(),
                timeout=None,
            )

        logger = logger or logging.getLogger(
            f"Service-Remote@{resource_instance.fragment}-{service_class.fragment}"
        )

        service = cls(
            service_method=remote_method,
            service_class=service_class,
            resource_instance=resource_instance,
            payload_model=payload_model,
            logger=logger,
        )
        service._service_url = service_url
        service._is_remote = True
        return service

    def register_in_middleware(self, mw: smw.Middleware):
        if self._is_remote:
            raise ValueError("Remote services cannot be registered in middleware.")

        self._middleware = mw
        mw.workflow()(self.service_method)
        self.logger.info(f"Registered in middleware with name '{self.name}'")

    def register_in_graph_db(self, host_url: str, ogm: OGM, named_graph: IRI = None):
        if self._is_remote:
            raise ValueError("Remote services cannot be registered in graph database.")
        if not self._middleware:
            raise ValueError(
                "Middleware must be registered before registering service in graph database."
            )

        self._service_url = f"{host_url}/workflows/{self.name}/execute"

        property_chains = [
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf"),
            ],
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
        ]
        class_scope = ClassScope.from_property_chains(property_chains)

        data = {
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"): [
                self._service_url
            ],
            IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf"): [
                {"id": self.resource_instance}
            ],
        }

        service_node = ogm.create(
            class_iri=self.service_class,
            class_scope=class_scope,
            data=data,
            named_graph=named_graph,
        )
        self._service_instance = service_node.id
        self.logger.info(
            f"Registered in knowledge graph with IRI '{self._service_instance}' and URL '{self._service_url}'"
        )

    def deregister_in_middleware(self, ogm: OGM):
        if self._is_remote:
            raise ValueError("Remote services cannot be deregistered.")
        self._service_instance = None
        self.logger.warning(f"Service middleware deregistration not yet implemented")

    def deregister_in_graph_db(self, ogm: OGM, named_graph: IRI = None):
        """Remove service registration from the knowledge graph."""
        if self._is_remote:
            raise ValueError("Remote services cannot be cleaned from graph database.")
        if not self._service_instance:
            self.logger.info("Service not registered in graph, skipping cleanup")
            return

        self.logger.warning(f"Service GraphDB deregistration not yet implemented")

    def __call__(self, payload: BaseModel) -> dict[str, Any]:
        if not isinstance(payload, self.payload_model):
            raise ValueError(
                f"Invalid payload type, expected {self.payload_model}, got {type(payload)}"
            )
        self.logger.info(f"Invoking with payload: {payload}")
        response = self.service_method(payload)
        self.logger.info(f"Completed with response: {response}")
        return response
