#!/usr/bin/env python3
"""
Test script for FlexConveyorSystem
Tests all functions with a predefined sequence:
1. Initialize FlexConveyorSystem
2. Add a parcel from module1 to module2
3. Find path for the parcel
4. Convey the parcel along the path
5. Delete the parcel when it reaches destination
"""

import sys
import time
import logging
from flexconveyor_system import FlexConveyorSystem

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("flexconveyor_test.log"),
        logging.StreamHandler(sys.stdout),
    ],
)


def main():
    logging.info("Starting TestScript")
    system = FlexConveyorSystem(
        "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#exampleSystem1"
    )
    print(system.adjacency_matrix)
    print(system.get_parcels())
    module_1 = "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#module1"
    module_2 = "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#module2"
    system.add_parcel(module_1, module_2)
    system.get_parcels()
    print(system.parcels)
    parcel = system.parcels[
        "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#parcel1"
    ]
    print(f"Parcel info: {parcel}")

    path = system.find_path(parcel["current_position"], parcel["destination"])
    print(f"Path found: {path}")
    system.convey(parcel["current_position"], parcel["destination"])
    system.get_parcels()
    print(system.parcels)


if __name__ == "__main__":
    main()
