from graph_db_interface import GraphDB
import json
import heapq
import logging
from enum import Enum

logging.basicConfig(
    filename="flexconveyor.log",
    filemode="w",  # Overwrite log file on startup
    format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.DEBUG,
)

# Write a startup message to ensure log file exists
logging.info("FlexConveyorSystem module loaded.")


class FlexConveyorSystem:

    class Direction(Enum):
        NORTH = "north"
        EAST = "east"
        SOUTH = "south"
        WEST = "west"

    def __init__(
        self,
        system_iri: str = "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#exampleSystem1",
    ) -> None:
        """
        Build a FlexConveyor instance.
        Setup the connection to GraphDB
        Fetch datamodel for Flexconveyor and configure connections accordingly
        """
        self.system_iri = system_iri
        self.db = GraphDB(
            base_url="http://172.22.223.165:7200/",
            username="admin",
            password="qqq",
            repository="JMS_Usecase_2",
        )
        self.parcels = {}

        self.build_adjacency_matrix()
        self.get_parcels()
        self.parcel_counter = len(self.parcels)
        logging.info(f"Initialized FlexConveyorSystem for {system_iri}")

    def get_parcels(self):
        """Get all parcels currently in the system"""
        self.parcels = {}

        for module in self.adjacency_matrix:
            parcel_triples = self.db.triples_get(
                sub=module,
                pred="https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasPossession",
            )
            if parcel_triples:
                # triples_get returns a list of triples, get the object (parcel IRI) from the first triple
                parcel_iri = parcel_triples[0][2]

                dest_triples = self.db.triples_get(
                    sub=parcel_iri,
                    pred="https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasDestination",
                )
                destination_iri = None
                if dest_triples:
                    destination_iri = dest_triples[0][2]

                self.parcels[parcel_iri] = {
                    "current_position": module,
                    "destination": destination_iri,
                }

        # Check for parcels that have reached their destination and delete them
        parcels_to_delete = []
        for parcel_iri, info in self.parcels.items():
            if info["current_position"] == info["destination"]:
                logging.info(
                    f"Parcel {self._shorten_iri(parcel_iri)} has reached its destination at {self._shorten_iri(info['current_position'])}"
                )
                parcels_to_delete.append(parcel_iri)

        # Delete parcels that reached their destination
        for parcel_iri in parcels_to_delete:
            logging.info(f"Deleting parcel {parcel_iri}")
            try:
                self.delete_parcel(parcel_iri)
                logging.info(
                    f"Parcel {self._shorten_iri(parcel_iri)} deleted successfully"
                )
                # Remove from local parcels dict
                if parcel_iri in self.parcels:
                    del self.parcels[parcel_iri]
            except Exception as e:
                logging.error(f"Failed to delete parcel {parcel_iri}: {e}")

        return self.parcels

    def build_adjacency_matrix(self):
        """Build the adjacency matrix for the conveyor system modules"""
        connections = {
            "north": "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasNorthConnection",
            "east": "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasEastConnection",
            "south": "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasSouthConnection",
            "west": "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasWestConnection",
        }

        # Query for all modules in the system
        query = (
            f"SELECT ?o WHERE {{ "
            f"<{self.system_iri}> <https://www.sfb1574.kit.edu/ontologies/FlexConveyor#containsFlexConveyorModule> ?o . "
            f"}}"
        )

        query_result = self.db.query(query)
        modules_queried = []
        if (
            query_result
            and isinstance(query_result, dict)
            and "results" in query_result
            and "bindings" in query_result["results"]
        ):
            modules_queried = [
                binding["o"]["value"] for binding in query_result["results"]["bindings"]
            ]

        # Initialize adjacency matrix as a dictionary for fast lookup
        adjacency_dict = {}
        for module in modules_queried:
            connections_list = []
            for direction in ["north", "east", "south", "west"]:
                property_iri = connections[direction]
                connection_query = (
                    f"SELECT ?o WHERE {{ " f"<{module}> <{property_iri}> ?o . " f"}}"
                )

                query_result = self.db.query(connection_query)
                if (
                    query_result
                    and isinstance(query_result, dict)
                    and "results" in query_result
                    and "bindings" in query_result["results"]
                    and query_result["results"]["bindings"]
                ):
                    connections_list.append(
                        query_result["results"]["bindings"][0]["o"]["value"]
                    )
                else:
                    connections_list.append(None)

            adjacency_dict[module] = connections_list

        self.adjacency_matrix = adjacency_dict
        logging.info(
            f"Built adjacency matrix with {len(self.adjacency_matrix)} modules"
        )

        # Debug output
        print("Adjacency Matrix (dict):")
        print("Format: module_iri: [north, east, south, west]")
        for mod, conns in self.adjacency_matrix.items():
            print(f"{mod}: {conns}")

    def convey(self, current_module, next_module_iri):
        """
        Convey a parcel from the specified module to the next module.
        Computes direction internally and logs the action.
        """
        logging.info(
            f"Conveying parcel from module: {current_module} to module: {next_module_iri}"
        )
        parcel_iri_list = self.db.triples_get(
            sub=current_module,
            pred="https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasPossession",
        )
        parcel_iri = (
            parcel_iri_list[0][2]
            if parcel_iri_list and len(parcel_iri_list[0]) > 2
            else ""
        )
        parcel = self.parcels.get(parcel_iri)
        logging.info(f"Parcel info: {parcel}")

        connections = self.adjacency_matrix.get(current_module)
        if connections is None:
            logging.error(f"Module {current_module} not found in adjacency matrix")
            raise ValueError(f"Module {current_module} not found in adjacency matrix")
        directions = ["north", "east", "south", "west"]
        direction = None
        for idx, target in enumerate(connections):
            if target == next_module_iri:
                direction = directions[idx]
                break
        if direction is None:
            logging.error(
                f"No valid direction from {current_module} to {next_module_iri}"
            )
            raise ValueError(
                f"No valid direction from {current_module} to {next_module_iri}"
            )
        log_msg = (
            f"Conveying {self._shorten_iri(parcel_iri)} into {direction} Direction."
        )
        logging.info(log_msg)
        triples_to_delete = [
            (
                current_module,
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasPossession",
                parcel_iri,
            ),
            (
                parcel_iri,
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#isPossessedBy",
                current_module,
            ),
        ]
        triples_to_insert = [
            (
                next_module_iri,
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasPossession",
                parcel_iri,
            ),
            (
                parcel_iri,
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#isPossessedBy",
                next_module_iri,
            ),
        ]
        try:
            result = self.db.triples_update(
                old_triples=triples_to_delete,
                new_triples=triples_to_insert,
                check_exist=True,
            )
        except Exception as e:
            logging.error(f"Error during convey operation: {e}")
            raise e

        logging.info(f"SPARQL Update Result: {result}")
        return result, log_msg

    def add_parcel(self, destination_iri, start_module_iri):
        parcel_iri = f"https://www.sfb1574.kit.edu/ontologies/FlexConveyor#parcel{self.parcel_counter + 1}"
        triples_to_insert = []
        triples_to_insert.append(
            (
                parcel_iri,
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#Parcel",
            )
        )
        triples_to_insert.append(
            (
                parcel_iri,
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                "http://www.w3.org/2002/07/owl#NamedIndividual",
            )
        )
        triples_to_insert.append(
            (
                parcel_iri,
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasDestination",
                destination_iri,
            )
        )
        triples_to_insert.append(
            (
                parcel_iri,
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#isPossessedBy",
                start_module_iri,
            )
        )
        triples_to_insert.append(
            (
                start_module_iri,
                "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#hasPossession",
                parcel_iri,
            )
        )
        try:
            result = self.db.triples_add(
                triples_to_add=triples_to_insert,
            )
            self.parcel_counter += 1
            self.get_parcels()  # Refresh parcels after adding a new one
        except Exception as e:
            logging.error(f"Error during add_parcel operation: {e}")
            raise e

    def delete_parcel(self, parcel_iri):
        triples_to_delete: list[tuple[str, str, str]] = []
        subject_triples = self.db.triples_get(sub=parcel_iri)
        object_triples = self.db.triples_get(obj=parcel_iri)

        for triple in subject_triples:
            if (
                isinstance(triple, tuple)
                and len(triple) == 3
                and all(isinstance(x, str) for x in triple)
            ):
                triples_to_delete.append(triple)
        for triple in object_triples:
            if (
                isinstance(triple, tuple)
                and len(triple) == 3
                and all(isinstance(x, str) for x in triple)
            ):
                triples_to_delete.append(triple)
        if not triples_to_delete:
            logging.error(f"Parcel {parcel_iri} not found in database")
            raise ValueError(f"Parcel {parcel_iri} not found in database")

        self.db.triples_delete(triples_to_delete=triples_to_delete)

    def find_path(self, start_module_iri, target_module_iri):
        """
        Find the shortest path between start and target modules using Dijkstra's algorithm.
        Returns a list of module IRIs representing the path, or None if no path exists.
        """
        # Build a graph representation from adjacency matrix (dict)
        graph = {}
        modules = list(self.adjacency_matrix.keys())
        for module_id, connections in self.adjacency_matrix.items():
            graph[module_id] = []
            for connected_module in connections:
                if connected_module is not None:
                    graph[module_id].append(
                        (connected_module, 1)
                    )  # Weight = 1 for each connection

        # Verify start and target modules exist
        if start_module_iri not in modules:
            print(f"Start module {start_module_iri} not found in system")
            return None
        if target_module_iri not in modules:
            print(f"Target module {target_module_iri} not found in system")
            return None

        # If start equals target, return single-node path
        if start_module_iri == target_module_iri:
            return [start_module_iri]

        # Dijkstra's algorithm implementation
        distances = {module: float("infinity") for module in modules}
        distances[start_module_iri] = 0
        previous = {module: None for module in modules}
        pq = [(0, start_module_iri)]
        visited = set()
        while pq:
            current_distance, current_module = heapq.heappop(pq)
            if current_module in visited:
                continue
            visited.add(current_module)
            if current_module == target_module_iri:
                break
            for neighbor, weight in graph.get(current_module, []):
                if neighbor not in visited:
                    distance = current_distance + weight
                    if distance < distances[neighbor]:
                        distances[neighbor] = distance
                        previous[neighbor] = current_module
                        heapq.heappush(pq, (distance, neighbor))
        if distances[target_module_iri] == float("infinity"):
            print(f"No path found from {start_module_iri} to {target_module_iri}")
            return None
        path = []
        current = target_module_iri
        while current is not None:
            path.append(current)
            current = previous[current]
        path.reverse()
        print(
            f"Path found with distance {distances[target_module_iri]}: {len(path)} modules"
        )
        return path

    def _shorten_iri(self, iri: str) -> str:
        return iri.split("#")[-1] if "#" in iri else iri.split("/")[-1]


if __name__ == "__main__":
    flex_conveyor_system = FlexConveyorSystem()
