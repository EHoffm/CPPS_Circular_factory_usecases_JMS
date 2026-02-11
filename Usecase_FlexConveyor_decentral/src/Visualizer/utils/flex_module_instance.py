"""
FlexConveyor Module Instance Management

Provides functionality for creating and managing FlexConveyor module instances
in the knowledge base using OGM.
"""

import streamlit as st
import json
from typing import Any, Dict, Optional
from pydantic import BaseModel

from graph_db_interface.utils.iri import IRI
from circular_factory_ogm.utils.class_scope import ClassScope
from circular_factory_ogm.ogm import OGM


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
]

CLASS_IRI = IRI("http://w3id.org/circularfactory/FlexConveyor#FlexConveyorModule")
DEFAULT_INSTANCE_IRI = IRI("http://w3id.org/circularfactory/FlexConveyor#TemporaryModule")


def create_blank_flexconveyor_instance(ogm: OGM, instance_iri: Optional[IRI] = None) -> BaseModel:
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


def render_connection_item(connection_data: Dict[str, Any], index: int, field_path: str):
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
            if st.button("🗑️ Remove", key=f"{field_path}_remove_{index}", use_container_width=True):
                return None  # Signal to remove this connection
        
        # Find connectsTo and direction keys (they might be mangled)
        connects_to_key = None
        direction_key = None
        connects_to_value = ""
        direction_value = ""
        
        if isinstance(connection_data, dict):
            for key in connection_data.keys():
                if is_connects_to_field(key):
                    connects_to_key = key
                    # Extract value from list if it's a list
                    val = connection_data[key]
                    if isinstance(val, list) and len(val) > 0:
                        connects_to_value = str(val[0]) if val[0] and not isinstance(val[0], dict) else ""
                    elif not isinstance(val, (list, dict)):
                        connects_to_value = str(val)
                elif is_direction_field(key):
                    direction_key = key
                    # Extract value from list if it's a list
                    val = connection_data[key]
                    if isinstance(val, list) and len(val) > 0:
                        direction_value = str(val[0]) if val[0] and not isinstance(val[0], dict) else ""
                    elif not isinstance(val, (list, dict)):
                        direction_value = str(val)
        
        # Text input for connectsTo
        new_connects_to = st.text_input(
            "Connects To (Module IRI)",
            value=connects_to_value,
            key=f"{field_path}_connectsTo_{index}",
            placeholder="http://w3id.org/circularfactory/FlexConveyor#TargetModule"
        )
        
        # Dropdown for direction
        direction_options = [
            "",
            "http://w3id.org/circularfactory/FlexConveyor#East",
            "http://w3id.org/circularfactory/FlexConveyor#North",
            "http://w3id.org/circularfactory/FlexConveyor#South",
            "http://w3id.org/circularfactory/FlexConveyor#West"
        ]
        
        # Find current index
        current_index = 0
        if direction_value in direction_options:
            current_index = direction_options.index(direction_value)
        
        new_direction = st.selectbox(
            "Direction",
            options=direction_options,
            index=current_index,
            key=f"{field_path}_direction_{index}"
        )
        
        # Return updated connection data with original keys
        result = {}
        if connects_to_key:
            result[connects_to_key] = [new_connects_to] if new_connects_to else [{}]
        if direction_key:
            result[direction_key] = [new_direction] if new_direction else [{}]
        
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
                key=f"{field_path}_{key}"
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
            updated_item = render_connection_item(item, idx, f"{field_path}_{field_name}")
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
            if st.session_state[session_key] and isinstance(st.session_state[session_key][0], dict):
                template = {}
                for key in st.session_state[session_key][0].keys():
                    template[key] = [{}]
                st.session_state[session_key].append(template)
            else:
                # Fallback: create with generic keys (shouldn't happen)
                st.session_state[session_key].append({})
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
                        result.append(render_nested_dict(item, f"{field_path}_{field_name}_{idx}"))
                else:
                    value = st.text_input(
                        f"Item {idx + 1}",
                        value=str(item) if item is not None else "",
                        key=f"{field_path}_{field_name}_{idx}"
                    )
                    result.append(value)
            
            with col2:
                if st.button("🗑️", key=f"{field_path}_{field_name}_remove_{idx}"):
                    st.session_state[session_key].pop(idx)
                    st.rerun()
        
        # Add button for new item
        if st.button(f"➕ Add Item", key=f"{field_path}_{field_name}_add"):
            st.session_state[session_key].append("" if not data or not isinstance(data[0], dict) else {})
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


def render_instance_form(fields: Dict[str, Any], form_key: str = "flexmodule_form") -> Dict[str, Any]:
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
            user_values[field_name] = st.text_input(
                "**Module Instance IRI**",
                value=str(field_value) if field_value is not None else "",
                key=f"{form_key}_{field_name}",
                help="Unique identifier for this FlexConveyor module instance"
            )
            st.divider()
            continue
        
        # Clean field name for display
        display_name = clean_field_name(field_name)
        
        if isinstance(field_value, dict):
            # Nested dictionary
            with st.expander(f"📦 {display_name}", expanded=True):
                user_values[field_name] = render_nested_dict(field_value, f"{form_key}_{field_name}")
                
        elif isinstance(field_value, list):
            # List field (including connections)
            user_values[field_name] = render_list_field(field_value, field_name, form_key)
            
        else:
            # Simple field
            user_values[field_name] = st.text_input(
                f"**{display_name}**",
                value=str(field_value) if field_value is not None else "",
                key=f"{form_key}_{field_name}"
            )
        
        st.divider()
    
    # Form submission buttons (outside form since we're using session state)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Instance", type="primary", use_container_width=True, key=f"{form_key}_submit"):
            return user_values
    with col2:
        if st.button("❌ Cancel", use_container_width=True, key=f"{form_key}_cancel"):
            # Clear session state
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith(form_key)]
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


def render_flex_module_instantiation(ogm: OGM):
    """
    Render the complete FlexConveyor module instantiation interface.
    
    Args:
        ogm: The OGM instance connected to GraphDB
    """
    initialize_flex_instance_session_state()
    
    st.subheader("Create FlexConveyor Module Instances")
    st.markdown("*Use this interface to instantiate new FlexConveyor modules in the knowledge base.*")
    
    # Display created modules
    if st.session_state.modules:
        st.success(f"✅ {len(st.session_state.modules)} module(s) created")
        
        with st.expander(f"📋 View Created Modules ({len(st.session_state.modules)})", expanded=False):
            for idx, module in enumerate(st.session_state.modules):
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    
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
                        if st.button("🗑️", key=f"remove_module_{idx}", use_container_width=True):
                            st.session_state.modules.pop(idx)
                            st.rerun()
                
                # Show detailed JSON in expander
                with st.expander(f"🔍 View Details - Module {idx + 1}"):
                    st.json(module)
        
        st.divider()
    
    # Button to create blank instance or add another module
    if not st.session_state.show_flex_form:
        button_label = "➕ Add FlexConveyor Module Instance" if not st.session_state.modules else "➕ Add Another Module"
        
        if st.button(button_label, type="primary"):
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
                    
                st.success("✅ Loaded ontology structure!")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Failed to create blank instance: {str(e)}")
    
    # Show form if blank instance was created
    if st.session_state.show_flex_form and st.session_state.flex_instance_fields:
        st.info("💡 Below are the fields extracted from the FlexConveyor ontology. Fill them in to create a new instance.")
        
        # Render the form
        user_values = render_instance_form(st.session_state.flex_instance_fields)
        
        if user_values is not None and user_values != "continue":
            # User submitted the form - add to modules list
            st.session_state.modules.append(user_values)
            st.success(f"✅ Module saved! Total modules: {len(st.session_state.modules)}")
            
            # Reset form state
            st.session_state.show_flex_form = False
            st.session_state.flex_blank_instance = None
            st.session_state.flex_instance_fields = None
            
            # Clear form-related session state
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith("flexmodule_form")]
            for key in keys_to_clear:
                del st.session_state[key]
            
            st.rerun()
            
        elif user_values is None:
            # User cancelled
            st.warning("❌ Cancelled")
            st.session_state.show_flex_form = False
            st.session_state.flex_blank_instance = None
            st.session_state.flex_instance_fields = None
            st.rerun()
