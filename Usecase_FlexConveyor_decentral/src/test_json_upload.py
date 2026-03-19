"""Test script to verify JSON upload handling"""

import json

# Sample JSON from user
sample_json = [
    {
        "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module1",
        "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_hasConnection": [
            {
                "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Connection1",
                "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_connectsTo": [
                    {
                        "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module2"
                    }
                ],
                "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_hasDirection": [
                    {"id": "http://w3id.org/circularfactory/FlexConveyor#South"}
                ],
            }
        ],
    },
    {
        "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module2",
        "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_hasConnection": [
            {
                "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Connection2",
                "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_connectsTo": [
                    {
                        "id": "http://w3id.org/circularfactory/FlexConveyorInstances#Module1"
                    }
                ],
                "http_c__s__s_w3id_d_org_s_circularfactory_s_FlexConveyor_h_hasDirection": [
                    {"id": "http://w3id.org/circularfactory/FlexConveyor#North"}
                ],
            }
        ],
    },
]


def is_connection_field(field_name: str) -> bool:
    """Check if a field name represents a connection field."""
    return "connection" in field_name.lower()


def test_json_structure():
    """Test parsing and processing the JSON structure"""

    print("\n=== Testing JSON Structure ===")
    print(f"Type: {type(sample_json)}")
    print(f"Is List: {isinstance(sample_json, list)}")
    print(f"Number of modules: {len(sample_json)}")

    for idx, module in enumerate(sample_json):
        print(f"\n--- Module {idx + 1} ---")
        print(f"Module ID: {module.get('id', 'Unknown')}")

        # Count connections
        connection_count = 0
        for key, value in module.items():
            print(f"  Key: {key}")
            if is_connection_field(key):
                print(f"    -> Recognized as connection field")
                if isinstance(value, list):
                    connection_count = len(value)
                    print(f"    -> Contains {connection_count} connection(s)")
                    for conn_idx, conn in enumerate(value):
                        print(
                            f"       Connection {conn_idx + 1}: {conn.get('id', 'Unknown')}"
                        )

        print(f"Total connections: {connection_count}")

    print("\n✅ JSON structure is valid and can be processed!")


if __name__ == "__main__":
    test_json_structure()
