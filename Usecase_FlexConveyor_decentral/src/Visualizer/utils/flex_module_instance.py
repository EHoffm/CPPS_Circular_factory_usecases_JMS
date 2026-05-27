"""
FlexConveyor Module Instance Management

Provides functionality for creating and managing FlexConveyor module instances
in the knowledge base using OGM.
"""

import streamlit as st
import json
import os
from typing import Any, Dict, Optional
from pydantic import BaseModel

from graph_db_interface import IRI
from kapps_ogm import OGM, ClassScope

from .bootstrap import instantiate_modules, instantiate_wms

# Hardcoded configuration for FlexConveyor modules
PROPERTY_CHAINS = [
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
        IRI("http://w3id.org/circularfactory/FlexConveyor#connectsTo"),
    ],
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasDirection"),
    ],
    [
        IRI("http://w3id.org/circularfactory/FlexConveyor#hasConnection"),
        IRI("http://w3id.org/circularfactory/FlexConveyor#onPort"),
    ],
]

CLASS_IRI = IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule")
DEFAULT_INSTANCE_IRI = IRI(
    "http://w3id.org/circularfactory/FlexConveyor#TemporaryModule"
)
FLEXCONVEYOR_INSTANCES_GRAPH_IRI = IRI(
    "http://w3id.org/circularfactory/FlexConveyorInstances"
)


def clear_flexconveyor_instances_graph(ogm: OGM) -> bool:
    """Clear the FlexConveyor instances named graph."""
    return ogm.db.clear_graph(FLEXCONVEYOR_INSTANCES_GRAPH_IRI)


def create_blank_flexconveyor_instance(
    ogm: OGM, instance_iri: Optional[IRI] = None
) -> BaseModel:
    """
    Create a blank FlexConveyor module instance from the ontology.

    Args:
        ogm: The OGM instance connected to GraphDB
        instance_iri: Optional custom instance IRI (uses default if not provided)

    Returns:
        BaseModel: A pydantic model instance with blank values conforming to the ontology
    """
    if instance_iri is None:
        instance_iri = DEFAULT_INSTANCE_IRI

    # Convert property chains to ClassScope
    class_scope = ClassScope.from_property_chains(PROPERTY_CHAINS)

    # Create blank instance
    blank_instance = ogm.create_blank_instance(
        instance_iri=instance_iri,
        class_iri=CLASS_IRI,
        class_scope=class_scope,
    )

    return blank_instance


def extract_fields_from_instance(instance: BaseModel) -> Dict[str, Any]:
    """
    Extract field names and their default values from a pydantic instance.

    Args:
        instance: The pydantic model instance

    Returns:
        Dict containing field names and their default values
    """
    return instance.model_dump()


def initialize_form_data_in_session(fields: Dict[str, Any], form_key: str):
    """Initialize form data in session state if not already present."""
    session_key = f"{form_key}_data"
    if session_key not in st.session_state:
        st.session_state[session_key] = json.loads(json.dumps(fields))


def is_connection_field(field_name: str) -> bool:
    """Check if a field name represents a connection field."""
    return "connection" in field_name.lower()


def is_connects_to_field(field_name: str) -> bool:
    """Check if a field name represents a connectsTo field."""
    return "connectsto" in field_name.lower().replace("_", "")


def is_direction_field(field_name: str) -> bool:
    """Check if a field name represents a direction field."""
    return "direction" in field_name.lower()


def render_connection_item(
    connection_data: Dict[str, Any],
    index: int,
    field_path: str,
    connections_list: list,
):
    """
    Render a single connection item with inputs for connectsTo and direction.

    Args:
        connection_data: Dictionary containing connection fields
        index: Index of this connection in the list
        field_path: Path identifier for unique keys

    Returns:
        Updated connection dictionary or None if removed
    """
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(f"**Connection #{index + 1}**")

        with col2:
            # Delete button for this connection
            if st.button(
                "🗑️ Remove", key=f"{field_path}_remove_{index}", width="stretch"
            ):
                return None  # Signal to remove this connection

        # Find connectsTo, direction, and onPort keys (they might be mangled)
        id_key = "id"
        id_value = ""
        connects_to_key = None
        direction_key = None
        on_port_key = None
        connects_to_value = ""
        direction_value = ""
        on_port_value = 0

        if isinstance(connection_data, dict):
            for key in connection_data.keys():
                if key == "id":
                    id_key = key
                    id_value = str(connection_data.get(key, ""))
                if is_connects_to_field(key):
                    connects_to_key = key
                    # Extract value from list if it's a list
                    val = connection_data[key]
                    if isinstance(val, list) and len(val) > 0:
                        if isinstance(val[0], dict):
                            connects_to_value = str(val[0].get("id", ""))
                        elif val[0]:
                            connects_to_value = str(val[0])
                    elif not isinstance(val, (list, dict)):
                        connects_to_value = str(val)
                elif is_direction_field(key):
                    direction_key = key
                    # Extract value from list if it's a list
                    val = connection_data[key]
                    if isinstance(val, list) and len(val) > 0:
                        if isinstance(val[0], dict):
                            direction_value = str(val[0].get("id", ""))
                        elif val[0]:
                            direction_value = str(val[0])
                    elif not isinstance(val, (list, dict)):
                        direction_value = str(val)
                elif "onport" in key.lower():
                    on_port_key = key
                    # Extract integer value
                    val = connection_data[key]
                    if isinstance(val, list) and len(val) > 0:
                        on_port_value = int(val[0]) if val[0] is not None else 0
                    elif isinstance(val, (int, str)) and val:
                        on_port_value = int(val)
                    else:
                        on_port_value = 0

        if not id_value:
            id_value = get_next_connection_id(
                st.session_state.get("modules", []), connections_list
            )

        # Text input for connection id
        new_connection_id = st.text_input(
            "Connection IRI",
            value=id_value,
            key=f"{field_path}_id_{index}",
        )

        # Dropdown for connectsTo based on created modules
        modules = st.session_state.get("modules", [])
        module_options = [module.get("id", "") for module in modules if "id" in module]
        module_options = [opt for opt in module_options if opt]
        connects_to_options = [""] + module_options

        if connects_to_value and connects_to_value not in connects_to_options:
            connects_to_options.append(connects_to_value)

        connects_to_index = 0
        if connects_to_value in connects_to_options:
            connects_to_index = connects_to_options.index(connects_to_value)

        new_connects_to = st.selectbox(
            "Connects To (Module IRI)",
            options=connects_to_options,
            index=connects_to_index,
            key=f"{field_path}_connectsTo_{index}",
        )

        # Dropdown for direction
        direction_options = [
            "",
            "http://w3id.org/circularfactory/FlexConveyor#East",
            "http://w3id.org/circularfactory/FlexConveyor#North",
            "http://w3id.org/circularfactory/FlexConveyor#South",
            "http://w3id.org/circularfactory/FlexConveyor#West",
        ]

        # Find current index
        current_index = 0
        if direction_value in direction_options:
            current_index = direction_options.index(direction_value)

        new_direction = st.selectbox(
            "Direction",
            options=direction_options,
            index=current_index,
            key=f"{field_path}_direction_{index}",
        )

        # Number input for onPort
        new_on_port = st.number_input(
            "Port Number",
            min_value=0,
            max_value=65535,
            value=on_port_value,
            step=1,
            key=f"{field_path}_onPort_{index}",
        )

        # Return updated connection data with original keys
        result = {id_key: new_connection_id}
        if connects_to_key:
            result[connects_to_key] = (
                [{"id": new_connects_to}] if new_connects_to else [{}]
            )
        if direction_key:
            result[direction_key] = [{"id": new_direction}] if new_direction else [{}]

        # Add onPort field
        if on_port_key:
            result[on_port_key] = [new_on_port]
        else:
            # Use the expected property name from the ontology
            result["http://w3id.org/circularfactory/FlexConveyor#onPort"] = [
                new_on_port
            ]

        return result


def render_nested_dict(data: Dict[str, Any], field_path: str) -> Dict[str, Any]:
    """
    Render nested dictionary fields recursively.

    Args:
        data: Dictionary to render
        field_path: Path identifier for unique keys

    Returns:
        Updated dictionary with user inputs
    """
    result = {}

    for key, value in data.items():
        if isinstance(value, dict):
            with st.expander(f"📦 {key}", expanded=True):
                result[key] = render_nested_dict(value, f"{field_path}_{key}")
        elif isinstance(value, list):
            result[key] = render_list_field(value, key, field_path)
        else:
            result[key] = st.text_input(
                f"{key}",
                value=str(value) if value is not None else "",
                key=f"{field_path}_{key}",
            )

    return result


def render_list_field(data: list, field_name: str, field_path: str) -> list:
    """
    Render list fields with add/remove functionality.
    Detects if list contains connection objects and renders them specially.

    Args:
        data: List to render
        field_name: Name of the field
        field_path: Path identifier for unique keys

    Returns:
        Updated list with user inputs
    """
    result = []

    # Check if this is a connections list
    is_connections_list = is_connection_field(field_name)

    # Also check if list items are connection objects (have connectsTo/direction fields)
    if not is_connections_list and len(data) > 0 and isinstance(data[0], dict):
        for key in data[0].keys():
            if is_connects_to_field(key) or is_direction_field(key):
                is_connections_list = True
                break

    if is_connections_list:
        st.markdown(f"**Connections**")

        # Initialize session state for this list if needed
        session_key = f"{field_path}_{field_name}_items"
        if session_key not in st.session_state:
            # Initialize with empty connection structure if empty
            if not data or (len(data) == 1 and not any(data[0].values())):
                # Create template with proper keys from first item if available
                if data and isinstance(data[0], dict):
                    template = {}
                    for key in data[0].keys():
                        if is_connects_to_field(key) or is_direction_field(key):
                            template[key] = [{}]
                    st.session_state[session_key] = [template] if template else []
                else:
                    st.session_state[session_key] = []
            else:
                st.session_state[session_key] = data

        # Render each connection
        connections_to_keep = []
        for idx, item in enumerate(st.session_state[session_key]):
            updated_item = render_connection_item(
                item,
                idx,
                f"{field_path}_{field_name}",
                st.session_state[session_key],
            )
            if updated_item is not None:  # None means user clicked remove
                connections_to_keep.append(updated_item)

        # Update session state if items were removed
        if len(connections_to_keep) != len(st.session_state[session_key]):
            st.session_state[session_key] = connections_to_keep
            st.rerun()

        result = connections_to_keep

        # Add button for new connection
        if st.button(f"➕ Add Connection", key=f"{field_path}_{field_name}_add"):
            # Create new connection with same keys as existing ones
            if st.session_state[session_key] and isinstance(
                st.session_state[session_key][0], dict
            ):
                template = {}
                for key in st.session_state[session_key][0].keys():
                    if key == "id":
                        template[key] = ""
                    else:
                        template[key] = [{}]
                if "id" not in template:
                    template["id"] = ""
                st.session_state[session_key].append(template)
            else:
                # Fallback: create with generic keys (shouldn't happen)
                st.session_state[session_key].append({"id": ""})
            st.rerun()

    else:
        # Generic list handling (for non-connection lists)
        st.markdown(f"**{field_name}**")

        session_key = f"{field_path}_{field_name}_items"
        if session_key not in st.session_state:
            st.session_state[session_key] = data if data else []

        for idx, item in enumerate(st.session_state[session_key]):
            col1, col2 = st.columns([5, 1])
            with col1:
                if isinstance(item, dict):
                    with st.expander(f"Item {idx + 1}", expanded=False):
                        result.append(
                            render_nested_dict(item, f"{field_path}_{field_name}_{idx}")
                        )
                else:
                    value = st.text_input(
                        f"Item {idx + 1}",
                        value=str(item) if item is not None else "",
                        key=f"{field_path}_{field_name}_{idx}",
                    )
                    result.append(value)

            with col2:
                if st.button("🗑️", key=f"{field_path}_{field_name}_remove_{idx}"):
                    st.session_state[session_key].pop(idx)
                    st.rerun()

        # Add button for new item
        if st.button(f"➕ Add Item", key=f"{field_path}_{field_name}_add"):
            st.session_state[session_key].append(
                "" if not data or not isinstance(data[0], dict) else {}
            )
            st.rerun()

    return result


def clean_field_name(field_name: str) -> str:
    """
    Clean up mangled field names for display.
    Converts Python-safe identifiers back to readable names.

    Args:
        field_name: The mangled field name

    Returns:
        Cleaned field name for display
    """
    # Extract the last part after the last # or /
    if "circularfactory" in field_name.lower():
        parts = field_name.replace("_h_", "#").replace("_s_", "/").split("#")
        if len(parts) > 1:
            return parts[-1]
    return field_name


def get_next_module_id(modules: list) -> str:
    """Return the next available ModuleN full IRI based on existing module ids."""
    base_iri = "http://w3id.org/circularfactory/FlexConveyorInstances#"
    used_numbers = set()

    for module in modules:
        module_id = str(module.get("id", ""))
        if "#" in module_id:
            module_id = module_id.split("#")[-1]
        if module_id.startswith("Module"):
            suffix = module_id.replace("Module", "", 1)
            if suffix.isdigit():
                used_numbers.add(int(suffix))

    next_number = 1
    while next_number in used_numbers:
        next_number += 1

    return f"{base_iri}Module{next_number}"


def _extract_connection_numbers(connection_ids: list) -> set:
    """Extract numeric suffixes from ConnectionN ids."""
    used_numbers = set()

    for connection_id in connection_ids:
        connection_id = str(connection_id)
        if "#" in connection_id:
            connection_id = connection_id.split("#")[-1]
        if connection_id.startswith("Connection"):
            suffix = connection_id.replace("Connection", "", 1)
            if suffix.isdigit():
                used_numbers.add(int(suffix))

    return used_numbers


def _collect_connection_ids_from_modules(modules: list) -> list:
    """Collect all connection ids from the current modules list."""
    connection_ids = []

    for module in modules:
        if not isinstance(module, dict):
            continue
        for key, value in module.items():
            if is_connection_field(key) and isinstance(value, list):
                for connection in value:
                    if isinstance(connection, dict) and connection.get("id"):
                        connection_ids.append(connection["id"])

    return connection_ids


def get_next_connection_id(modules: list, connections: list) -> str:
    """Return the next available ConnectionN full IRI across all modules."""
    base_iri = "http://w3id.org/circularfactory/FlexConveyorInstances#"
    connection_ids = _collect_connection_ids_from_modules(modules)

    for connection in connections:
        if isinstance(connection, dict) and connection.get("id"):
            connection_ids.append(connection["id"])

    used_numbers = _extract_connection_numbers(connection_ids)

    next_number = 1
    while next_number in used_numbers:
        next_number += 1

    return f"{base_iri}Connection{next_number}"


def render_instance_form(
    fields: Dict[str, Any], form_key: str = "flexmodule_form"
) -> Dict[str, Any]:
    """
    Render a Streamlit form for editing instance fields with proper nested structure handling.

    Args:
        fields: Dictionary of field names and their current values
        form_key: Unique key for the form

    Returns:
        Dictionary of user-entered values (or None if form not submitted)
    """
    st.subheader("FlexConveyor Module Instance Fields")
    st.markdown("*Fill in the values for each field below:*")

    # Initialize form data in session state
    initialize_form_data_in_session(fields, form_key)

    user_values = {}

    # Render each top-level field
    for field_name, field_value in fields.items():
        # Skip rendering if this is the 'id' field - handle it specially
        if field_name == "id":
            default_module_id = field_value
            if not st.session_state.get("editing_mode"):
                default_module_id = get_next_module_id(
                    st.session_state.get("modules", [])
                )

            user_values[field_name] = st.text_input(
                "**Module Instance IRI**",
                value=str(default_module_id) if default_module_id is not None else "",
                key=f"{form_key}_{field_name}",
                help="Unique identifier for this FlexConveyor module instance",
            )
            st.divider()
            continue

        # Clean field name for display
        display_name = clean_field_name(field_name)

        if isinstance(field_value, dict):
            # Nested dictionary
            with st.expander(f"📦 {display_name}", expanded=True):
                user_values[field_name] = render_nested_dict(
                    field_value, f"{form_key}_{field_name}"
                )

        elif isinstance(field_value, list):
            # List field (including connections)
            user_values[field_name] = render_list_field(
                field_value, field_name, form_key
            )

        else:
            # Simple field
            user_values[field_name] = st.text_input(
                f"**{display_name}**",
                value=str(field_value) if field_value is not None else "",
                key=f"{form_key}_{field_name}",
            )

        st.divider()

    # Form submission buttons (outside form since we're using session state)
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "💾 Save Instance",
            type="primary",
            width="stretch",
            key=f"{form_key}_submit",
        ):
            return user_values
    with col2:
        if st.button("❌ Cancel", width="stretch", key=f"{form_key}_cancel"):
            # Clear session state
            keys_to_clear = [
                k for k in st.session_state.keys() if k.startswith(form_key)
            ]
            for key in keys_to_clear:
                del st.session_state[key]
            return None

    return "continue"  # Special value to indicate form is still being edited


def initialize_flex_instance_session_state():
    """Initialize session state variables for FlexConveyor instance management."""
    if "flex_blank_instance" not in st.session_state:
        st.session_state.flex_blank_instance = None

    if "flex_instance_fields" not in st.session_state:
        st.session_state.flex_instance_fields = None

    if "show_flex_form" not in st.session_state:
        st.session_state.show_flex_form = False

    if "modules" not in st.session_state:
        st.session_state.modules = []

    if "editing_module_index" not in st.session_state:
        st.session_state.editing_module_index = None

    if "editing_module_fields" not in st.session_state:
        st.session_state.editing_module_fields = None

    if "editing_mode" not in st.session_state:
        st.session_state.editing_mode = False

    if "show_modules_preview" not in st.session_state:
        st.session_state.show_modules_preview = False

    if "last_uploaded_file" not in st.session_state:
        st.session_state.last_uploaded_file = None

    if "instantiation_requested" not in st.session_state:
        st.session_state.instantiation_requested = False

    if "wms_instantiation_requested" not in st.session_state:
        st.session_state.wms_instantiation_requested = False

    if "wms_spawn_box_requested" not in st.session_state:
        st.session_state.wms_spawn_box_requested = False


def render_flex_module_instantiation(ogm: OGM):
    """
    Render the complete FlexConveyor module instantiation interface.

    Args:
        ogm: The OGM instance connected to GraphDB
    """
    initialize_flex_instance_session_state()

    st.subheader("Create FlexConveyor Module Instances")
    st.markdown(
        "*Use this interface to instantiate new FlexConveyor modules in the knowledge base.*"
    )

    # File upload section
    st.divider()
    st.markdown("**📤 Load from JSON**")

    uploaded_file = st.file_uploader(
        "Upload a previously exported modules JSON file:",
        type="json",
        key="modules_json_upload",
    )

    if uploaded_file is not None:
        # Check if we've already processed this file to avoid infinite rerun
        file_name = uploaded_file.name
        if st.session_state.get("last_uploaded_file") != file_name:
            try:
                file_content = json.load(uploaded_file)

                # Validate that it's a list
                if not isinstance(file_content, list):
                    st.error("❌ Invalid JSON format. Expected a list of modules.")
                else:
                    # Load modules into session state
                    st.session_state.modules = file_content
                    # Mark this file as processed
                    st.session_state.last_uploaded_file = file_name
                    # Automatically show the preview after loading
                    st.session_state.show_modules_preview = True
                    st.success(f"✅ Loaded {len(file_content)} module(s) from file!")
                    st.info(
                        "📋 The modules are now displayed below and ready to edit or instantiate."
                    )

                    # DEBUG: Show what was loaded
                    with st.expander("🔧 Loaded Data Preview", expanded=False):
                        st.json(file_content)

                    # Single rerun to refresh UI with loaded modules
                    st.rerun()

            except json.JSONDecodeError:
                st.error("❌ Failed to parse JSON file. Please ensure it's valid JSON.")
            except Exception as e:
                st.error(f"❌ Error loading file: {str(e)}")
        # If file was already processed, don't do anything (no rerun needed)

    st.divider()
    # Display created modules
    if st.session_state.modules:
        st.success(f"✅ {len(st.session_state.modules)} module(s) successfully loaded!")

        # DEBUG: Show what's in session state (collapsed by default)
        with st.expander("🔧 Debug: Session State", expanded=False):
            st.write("**Session state modules:**")
            st.write(f"Type: {type(st.session_state.modules)}")
            st.write(f"Length: {len(st.session_state.modules)}")
            st.write("**Raw modules:**")
            st.json(st.session_state.modules)

        with st.expander(
            f"📋 View Created Modules ({len(st.session_state.modules)})", expanded=True
        ):
            for idx, module in enumerate(st.session_state.modules):
                with st.container(border=True):
                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        module_id = module.get("id", "Unknown")
                        st.markdown(f"**Module {idx + 1}:** `{module_id}`")

                        # Show connection count
                        connection_count = 0
                        for key, value in module.items():
                            if is_connection_field(key) and isinstance(value, list):
                                connection_count = len(value)
                                break

                        st.caption(f"Connections: {connection_count}")

                    with col2:
                        if st.button(
                            "✏️",
                            key=f"edit_module_{idx}",
                            width="stretch",
                        ):
                            # Prepare edit form with existing module data
                            st.session_state.editing_module_index = idx
                            st.session_state.editing_mode = True
                            st.session_state.editing_module_fields = json.loads(
                                json.dumps(module)
                            )

                            st.session_state.flex_instance_fields = (
                                st.session_state.editing_module_fields
                            )
                            st.session_state.show_flex_form = True

                            # Clear form-related session state
                            keys_to_clear = [
                                k
                                for k in st.session_state.keys()
                                if k.startswith("flexmodule_form")
                            ]
                            for key in keys_to_clear:
                                del st.session_state[key]

                            st.rerun()

                    with col3:
                        if st.button("🗑️", key=f"remove_module_{idx}", width="stretch"):
                            st.session_state.modules.pop(idx)
                            st.rerun()

                # Show detailed JSON in expander
                with st.expander(f"🔍 View Details - Module {idx + 1}"):
                    st.json(module)

        st.divider()

    # Button to create blank instance or add another module
    if not st.session_state.show_flex_form:
        button_label = (
            "➕ Add FlexConveyor Module Instance"
            if not st.session_state.modules
            else "➕ Add Another Module"
        )

        col1, col2 = st.columns([2, 1])
        with col1:
            if st.button(button_label, type="primary", width="stretch"):
                try:
                    with st.spinner("Loading ontology structure..."):
                        # Create blank instance
                        blank_instance = create_blank_flexconveyor_instance(ogm)

                        # Extract fields
                        fields = extract_fields_from_instance(blank_instance)

                        # Store in session state
                        st.session_state.flex_blank_instance = blank_instance
                        st.session_state.flex_instance_fields = fields
                        st.session_state.show_flex_form = True

                        st.session_state.editing_mode = False
                        st.session_state.editing_module_index = None
                        st.session_state.editing_module_fields = None

                    st.success("✅ Loaded ontology structure!")
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Failed to create blank instance: {str(e)}")

        with col2:
            if st.button("👁️ Preview JSON", width="stretch"):
                st.session_state.show_modules_preview = (
                    not st.session_state.show_modules_preview
                )

        if st.session_state.show_modules_preview:
            preview_json = json.dumps(st.session_state.modules, indent=2)
            st.text_area(
                "Modules JSON Preview",
                value=preview_json,
                height=220,
                key="modules_json_preview",
                help="Preview of all created module objects",
            )

            with st.columns([1, 1])[1]:
                st.download_button(
                    label="⬇️ Download JSON",
                    data=preview_json,
                    file_name="modules_preview.json",
                    mime="application/json",
                    width="stretch",
                )

        # Instantiate button - always visible when modules exist
        st.divider()

        # Configuration options for instantiation
        st.markdown("**⚙️ Instantiation Options**")
        col_opt1, col_opt2 = st.columns([1, 1])
        with col_opt1:
            number_of_boxes = st.number_input(
                "Number of boxes to spawn (WMS)",
                min_value=1,
                max_value=100,
                value=st.session_state.get("wms_number_of_boxes", 1),
                step=1,
                help="Number of boxes that the WMS will spawn into the system",
                key="wms_number_of_boxes_input",
            )
            st.session_state.wms_number_of_boxes = number_of_boxes

        with col_opt2:
            concurrent_guard = st.checkbox(
                "Concurrent guard override (FlexConveyor)",
                value=st.session_state.get(
                    "flexconveyor_concurrent_guard_override", False
                ),
                help="If enabled, modules can accept boxes even when busy (for testing SHACL violations)",
                key="flexconveyor_concurrent_guard_override_input",
            )
            st.session_state.flexconveyor_concurrent_guard_override = concurrent_guard

        st.divider()
        col_inst1, col_inst2, col_inst3 = st.columns([1, 1, 1])
        with col_inst1:
            if st.button(
                "⚡ Instantiate Modules & WMS", width="stretch", type="primary"
            ):
                if not st.session_state.modules:
                    st.error(
                        "❌ No modules to instantiate. Add at least one module first."
                    )
                else:
                    # Set flag to trigger instantiation (persists across tab switches)
                    st.session_state.instantiation_requested = True
                    st.rerun()

        with col_inst2:
            if st.button("🏭 Instantiate WMS", width="stretch", type="secondary"):
                # Set flag to trigger WMS instantiation
                st.session_state.wms_instantiation_requested = True
                st.rerun()

        with col_inst3:
            if st.button("📦 Spawn Box", width="stretch", type="secondary"):
                st.session_state.wms_spawn_box_requested = True
                st.rerun()

    # Show form if blank instance was created or editing
    if st.session_state.show_flex_form and st.session_state.flex_instance_fields:
        st.info(
            "💡 Below are the fields extracted from the FlexConveyor ontology. Fill them in to create a new instance."
        )

        # Render the form
        user_values = render_instance_form(st.session_state.flex_instance_fields)

        if user_values is not None and user_values != "continue":
            # User submitted the form
            if (
                st.session_state.editing_mode
                and st.session_state.editing_module_index is not None
            ):
                st.session_state.modules[st.session_state.editing_module_index] = (
                    user_values
                )
                st.success("✅ Module updated!")
            else:
                st.session_state.modules.append(user_values)
                st.success(
                    f"✅ Module saved! Total modules: {len(st.session_state.modules)}"
                )

            # Reset form state
            st.session_state.show_flex_form = False
            st.session_state.flex_blank_instance = None
            st.session_state.flex_instance_fields = None

            st.session_state.editing_mode = False
            st.session_state.editing_module_index = None
            st.session_state.editing_module_fields = None

            # Clear form-related session state
            keys_to_clear = [
                k for k in st.session_state.keys() if k.startswith("flexmodule_form")
            ]
            for key in keys_to_clear:
                del st.session_state[key]

            st.rerun()

        elif user_values is None:
            # User cancelled
            st.warning("❌ Cancelled")
            st.session_state.show_flex_form = False
            st.session_state.flex_blank_instance = None
            st.session_state.flex_instance_fields = None

            st.session_state.editing_mode = False
            st.session_state.editing_module_index = None
            st.session_state.editing_module_fields = None
            st.rerun()
