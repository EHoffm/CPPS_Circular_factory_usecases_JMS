from typing import Optional, Any, Dict
import aas_middleware as aas
from graph_db_interface.utils.iri import IRI
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
    _service_name: str = None
    _service_instance: IRI = None
    _middleware: aas.Middleware = None
    _is_remote: bool = False

    def __init__(
        self,
        service_method: callable,
        service_class: IRI,
        resource_instance: IRI,
        payload_model: Optional[BaseModel] = None,
    ):
        self.service_method = service_method
        self.service_class = service_class
        self.resource_instance = resource_instance
        self.payload_model = payload_model
        self._service_name = self.service_method.__qualname__.split(".")[-1]

    @classmethod
    def fetch_remote_service(
        cls,
        resource_instance: IRI,
        service_class: IRI,
        payload_model: Optional[BaseModel],
        ogm: OGM,
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
            if not isinstance(payload, payload_model):
                raise ValueError(
                    f"Invalid payload type, expected {payload_model}, got {type(payload)}"
                )
            return requests.post(
                service_url,
                json=payload.model_dump(),
                timeout=None,
            )

        service = cls(
            service_method=remote_method,
            service_class=service_class,
            resource_instance=resource_instance,
            payload_model=payload_model,
        )
        service._service_url = service_url
        service._is_remote = True
        return service

    def register_in_middleware(self, mw: aas.Middleware):
        if self._is_remote:
            raise ValueError("Remote services cannot be registered in middleware.")
        self._middleware = mw
        mw.workflow()(self.service_method)
        logging.info(f"Registered service method {self._service_name} in middleware.")

    def register_in_graph_db(self, host_url: str, ogm: OGM, named_graph: IRI = None):
        if self._is_remote:
            raise ValueError("Remote services cannot be registered in graph database.")
        if not self._middleware:
            raise ValueError(
                "Middleware must be registered before registering service in graph database."
            )

        self._service_url = f"{host_url}/workflows/{self._service_name}/execute"

        # 1. We only define the simple literal properties for OGM creation
        property_chains = [
            [
                IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"),
            ],
        ]
        class_scope = ClassScope.from_property_chains(property_chains)

        data = {
            IRI("http://w3id.org/circularfactory/FlexConveyor#accessibleAt"): [
                self._service_url
            ],
        }

        # 2. Create the node with accessibleAt and its rdf:type
        service_node = ogm.create(
            class_iri=self.service_class,
            class_scope=class_scope,
            data=data,
            named_graph=named_graph,
        )
        self._service_instance = service_node.id

        # 3. Add the structural relationships manually as clean IRIs
        is_service_of = IRI("http://w3id.org/circularfactory/FlexConveyor#isServiceOf")
        has_service = IRI("http://w3id.org/circularfactory/FlexConveyor#hasService")

        try:
            ogm.db.triples_add(
                [
                    (
                        self._service_instance,
                        is_service_of,
                        self.resource_instance,
                    ),
                    (
                        self.resource_instance,
                        has_service,
                        self._service_instance,
                    ),
                ],
                check_exist=False,
                named_graph=named_graph,
            )
            print("✅ Successfully added service relationship triples to GraphDB.")
        except Exception as e:
            logging.error(f"Failed to add relationship triples to GraphDB: {e}")

        logging.info(
            f"Registered service in knowledge graph with IRI: {self._service_instance} and URL: {self._service_url}"
        )
    def deregister(self, ogm: OGM):
        if self._is_remote:
            raise ValueError("Remote services cannot be deregistered.")
        self._service_instance = None
        logging.warning(
            f"TODO cleanup required for runtime service triples of module {self.resource_instance} (service node: {self._service_instance})"
        )

    def __call__(self, *args, **kwds):
        return self.service_method(*args, **kwds)
