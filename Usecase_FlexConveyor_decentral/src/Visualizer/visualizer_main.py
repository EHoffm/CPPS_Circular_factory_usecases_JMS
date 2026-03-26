"""
FlexConveyor Visualizer - Main Entry Point

A Streamlit-powered user interface for the FlexConveyor system with GraphDB integration.
Provides system bootstrapping, runtime monitoring, and control capabilities.
"""

import os
import importlib
import subprocess
import sys
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh


def _bootstrap_import_paths() -> None:
    script_path = Path(__file__).resolve()
    package_dirs = (
        "kapps_ogm",
        "circular_factory_ogm",
        "graph_db_interface",
        "aas_middleware_inf",
        "datamodel_connector",
    )

    for parent in script_path.parents:
        parent_str = str(parent)
        if parent_str not in sys.path:
            sys.path.insert(0, parent_str)
        for package_dir in package_dirs:
            candidate = parent / package_dir
            if candidate.is_dir():
                candidate_str = str(candidate)
                if candidate_str not in sys.path:
                    sys.path.insert(0, candidate_str)


_bootstrap_import_paths()

from utils.bootstrap import register_shutdown_handlers
from utils import (
    initialize_login_session_state,
    render_login_sidebar,
    is_connected,
    is_ogm_initialized,
    get_ogm,
    clear_flexconveyor_instances_graph,
    render_flex_module_instantiation,
    initialize_flex_instance_session_state,
)

register_shutdown_handlers()

# ============================================================================
# Page Configuration
# ============================================================================

st.set_page_config(
    page_title="FlexConveyor Visualizer",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("FlexConveyor System Visualizer")

# ============================================================================
# Initialize Session State
# ============================================================================

initialize_login_session_state()
initialize_flex_instance_session_state()

if "current_page" not in st.session_state:
    st.session_state.current_page = "home"


# ============================================================================
# Sidebar - GraphDB Login
# ============================================================================

render_login_sidebar()


# ============================================================================
# Main Page
# ============================================================================

if not is_connected():
    st.info("👈 Please connect to GraphDB using the sidebar to get started")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Getting Started")
        st.markdown(
            """
        The FlexConveyor Visualizer provides three main capabilities:
        
        1. **System Bootstrapping** 🏗️
           - Create and place FlexConveyor modules
           - Define physical connections
           - Specify module roles (entry/exit)
        
        2. **Runtime Monitoring** 📊
           - Real-time box tracking
           - System state visualization
           - Connection and topology display
        
        3. **Runtime Control** 🎮
           - Inject boxes into the system
           - Start/stop/step simulation
           - Edit system configuration
        """
        )

    with col2:
        st.subheader("Connection Details")
        st.markdown(
            """
        To get started, you need:
        
        - **GraphDB Server**: A running GraphDB instance
        - **Repository**: Created and configured in GraphDB
        - **Credentials**: Valid username and password
        
        Default configuration (if running locally):
        - Base URL: `http://localhost:7200`
        - Username: `admin`
        - Password: Your admin password
        
        Once connected, you'll have access to:
        - Topology bootstrapping interface
        - Real-time system monitoring
        - Simulation controls
        - Box injection tools
        """
        )

else:
    # Display connection status with OGM information
    if is_ogm_initialized():
        st.success(
            "✅ Connected to GraphDB - Ready to use the visualizer | OGM initialized"
        )
    else:
        st.warning("✅ Connected to GraphDB - OGM not initialized")

    section = st.radio(
        "Section",
        options=["🏗️ Bootstrap", "📊 Monitor", "🎮 Control"],
        horizontal=True,
        key="main_section_selector",
    )

    if section == "🏗️ Bootstrap":
        st.header("System Bootstrapping")

        if not is_ogm_initialized():
            st.warning("⚠️ OGM not initialized. Please reconnect to GraphDB.")
        else:
            ogm = get_ogm()
            if st.button("clear Knowledge graph", key="clear_knowledge_graph"):
                if clear_flexconveyor_instances_graph(ogm):
                    st.success("Knowledge graph cleared successfully.")
                else:
                    st.error("Failed to clear knowledge graph.")
            render_flex_module_instantiation(ogm)

            st.divider()
            st.info(
                "ℹ️ **Box Generation**: Boxes are automatically spawned by the MockWMS entity "
                "after module instantiation and after each delivery. No manual intervention needed."
            )

    elif section == "📊 Monitor":
        st.header("Runtime Monitoring")
        if "discovered_modules" not in st.session_state:
            st.session_state.discovered_modules = []
        if "adjacency_matrix" not in st.session_state:
            st.session_state.adjacency_matrix = {}
        if "directional_rows" not in st.session_state:
            st.session_state.directional_rows = []

        action_col1, action_col2 = st.columns(2)

        if action_col1.button(
            "discover instantiated modules", key="discover_instantiated_modules"
        ):
            monitor_module = importlib.import_module("utils.system_state_monitor")
            st.session_state.discovered_modules = monitor_module.discover_modules(
                st.session_state.get("ogm")
            )

            st.session_state.adjacency_matrix = monitor_module.build_adjacency_matrix(
                st.session_state.get("ogm")
            )

            topology_module = importlib.import_module("utils.topology_renderer")
            st.session_state.directional_rows = (
                topology_module.adjacency_map_to_directional_rows(
                    st.session_state.adjacency_matrix
                )
            )

        if st.session_state.adjacency_matrix:
            # Live Monitoring Controls
            st.divider()

            # Initialize live monitoring state
            if "live_monitor_enabled" not in st.session_state:
                st.session_state.live_monitor_enabled = False
            if "live_monitor_refresh_rate" not in st.session_state:
                st.session_state.live_monitor_refresh_rate = 1000
            if "live_monitor_previous_state" not in st.session_state:
                st.session_state.live_monitor_previous_state = False

            # Control panel for live monitoring
            col1, col2, col3 = st.columns([2, 1, 2])
            with col1:
                enable_monitoring = st.checkbox(
                    "🔴 Enable live auto-refresh",
                    value=st.session_state.live_monitor_enabled,
                    key="enable_live_monitoring",
                    help="Automatically refresh box locations and topology at the specified interval",
                )

                # Detect state change and log it
                if enable_monitoring != st.session_state.live_monitor_previous_state:
                    live_monitor_module = importlib.import_module("utils.live_monitor")
                    live_monitor_module.log_monitoring_state_change(enable_monitoring)
                    st.session_state.live_monitor_previous_state = enable_monitoring

                st.session_state.live_monitor_enabled = enable_monitoring

            with col2:
                refresh_rate = st.selectbox(
                    "Refresh Rate",
                    options=[500, 1000, 2000, 5000],
                    index=1,
                    format_func=lambda x: f"{x/1000:.1f}s",
                    key="live_refresh_rate",
                )
                st.session_state.live_monitor_refresh_rate = refresh_rate

            with col3:
                if st.session_state.live_monitor_enabled:
                    st.success("🔄 Live monitoring active")
                else:
                    st.info("⏸️ Monitoring paused")

            # Auto-refresh mechanism (only triggers if enabled)
            if st.session_state.live_monitor_enabled:
                refresh_count = st_autorefresh(
                    interval=st.session_state.live_monitor_refresh_rate,
                    key="live_monitor_autorefresh",
                )

                # Call the update method
                live_monitor_module = importlib.import_module("utils.live_monitor")
                ogm = get_ogm()
                update_data = live_monitor_module.update_live_monitoring_data(ogm)

            st.subheader("System Topology")

            # Display dynamic topology visualization
            if st.session_state.directional_rows:
                topology_module = importlib.import_module("utils.topology_renderer")
                live_monitor_module = importlib.import_module("utils.live_monitor")

                ogm = get_ogm()
                box_locations = live_monitor_module.fetch_box_locations_for_monitoring(
                    ogm
                )

                # Create live PNG buffer with boxes (fast rendering)
                image_buf = live_monitor_module.create_live_topology_figure(
                    st.session_state.directional_rows, box_locations
                )
                st.image(image_buf, width="stretch")
            else:
                st.warning(
                    "No topology data available. Click 'build adjacency matrix' to generate it."
                )

            if st.session_state.directional_rows:
                st.caption("Adjacency Matrix")

                def _display_value(value):
                    if value == 0 or value is None:
                        return None
                    return str(value)

                topology_table = [
                    {
                        "module": _display_value(row[0]),
                        "North": _display_value(row[1]),
                        "East": _display_value(row[2]),
                        "South": _display_value(row[3]),
                        "West": _display_value(row[4]),
                    }
                    for row in st.session_state.directional_rows
                ]
                st.dataframe(topology_table, width="stretch")

        st.subheader("Box Locations")

        # Show live box locations if auto-refresh is enabled, otherwise show manual refresh button
        if st.session_state.get("live_monitor_enabled", True):
            # Live monitoring mode - fetch and display automatically
            live_monitor_module = importlib.import_module("utils.live_monitor")
            ogm = get_ogm()
            box_locations = live_monitor_module.fetch_box_locations_for_monitoring(ogm)

            col_metrics, col_data = st.columns([1, 3])

            with col_metrics:
                if box_locations:
                    total_boxes = sum(len(boxes) for boxes in box_locations.values())
                    st.metric("Active Boxes", total_boxes)
                    st.metric("Modules with Boxes", len(box_locations))
                else:
                    st.metric("Active Boxes", 0)

            with col_data:
                if box_locations:
                    location_data = []
                    for module_iri, box_iris in sorted(box_locations.items()):
                        for box_iri in box_iris:
                            location_data.append(
                                {
                                    "Module": module_iri,
                                    "Box": box_iri,
                                }
                            )
                    st.dataframe(location_data, width="stretch")
                else:
                    st.info("📦 No boxes currently in the system.")
        else:
            # Manual refresh mode - show button
            if st.button("Refresh box locations", key="refresh_box_locations"):
                monitor_module = importlib.import_module("utils.system_state_monitor")
                box_locations = monitor_module.get_box_locations(
                    st.session_state.get("ogm")
                )

                if not box_locations:
                    st.info("📦 No boxes currently in the system.")
                else:
                    location_data = []
                    for module_iri, box_iris in sorted(box_locations.items()):
                        for box_iri in box_iris:
                            location_data.append(
                                {
                                    "Module": module_iri,
                                    "Box": box_iri,
                                }
                            )

                    st.dataframe(location_data, width="stretch")

        button_columns = st.columns(4)
        for index, discovered_module in enumerate(st.session_state.discovered_modules):
            module_id = discovered_module.get("module_id", "unknown module")
            accessible_at = discovered_module.get("accessible_at")
            if accessible_at:
                swagger_ui_url = (
                    accessible_at
                    if accessible_at.rstrip("/").endswith("/docs")
                    else f"{accessible_at.rstrip('/')}/docs"
                )
                with button_columns[index % 4]:
                    st.link_button(
                        f"Open SwaggerUI ({module_id})",
                        swagger_ui_url,
                    )
            else:
                with button_columns[index % 4]:
                    st.caption(f"{module_id}: no accessibleAt value found")

    else:
        st.header("Runtime Control")

        if not is_ogm_initialized():
            st.warning("⚠️ OGM not initialized. Please reconnect to GraphDB.")
        else:
            ogm = get_ogm()

            # Ensure shared discovery state exists (also used by Monitor tab)
            if "discovered_modules" not in st.session_state:
                st.session_state.discovered_modules = []

            st.subheader("Inject and Route Boxes")

            control_module = importlib.import_module("utils.control")
            route_module = importlib.import_module("utils.route_planner")
            topology_module = importlib.import_module("utils.topology_renderer")

            col_refresh, _ = st.columns([1, 3])
            with col_refresh:
                if st.button(
                    "Refresh modules",
                    key="control_refresh_modules",
                    width="stretch",
                ):
                    st.session_state.discovered_modules = (
                        control_module.discover_modules(ogm)
                    )

            discovered = st.session_state.discovered_modules

            if not discovered:
                st.info(
                    "No instantiated modules discovered yet. "
                    "Use the Bootstrap & Monitor tabs to create modules, then click 'Refresh modules'."
                )
            else:
                module_ids = [
                    m.get("module_id", "") for m in discovered if m.get("module_id")
                ]

                entry_module_id = st.selectbox(
                    "Entry module (where the box is first received)",
                    options=module_ids,
                    key="control_entry_module_id",
                )

                box_iri = st.text_input(
                    "Box IRI",
                    value=st.session_state.get(
                        "control_box_iri",
                        "http://w3id.org/circularfactory/FlexConveyorInstances#Box1",
                    ),
                    key="control_box_iri",
                    help="Full IRI of the box to inject into the system.",
                )

                dest_options = ["(no override – use existing destination)"] + module_ids
                dest_choice = st.selectbox(
                    "Destination module (optional)",
                    options=dest_options,
                    key="control_destination_module_id",
                    help=(
                        "If set, the receive workflow will update the box's hasDestination "
                        "to this module and immediately start routing. If left as the first "
                        "option, any existing destination in the knowledge graph is used."
                    ),
                )

                destination_iri = (
                    None if dest_choice == dest_options[0] else dest_choice
                )

                # Look up the selected module's accessibleAt URL from the
                # cached discovery result so we don't touch GraphDB/OGM on
                # every injection.
                selected_module = next(
                    (m for m in discovered if m.get("module_id") == entry_module_id),
                    None,
                )
                entry_module_url = (
                    (selected_module or {}).get("accessible_at")
                    if selected_module
                    else None
                )

                if st.button("Inject box", type="primary", key="control_inject_box"):
                    if not box_iri:
                        st.error("Please provide a Box IRI before injecting.")
                    elif not entry_module_url:
                        st.error(
                            "Selected entry module has no accessibleAt URL. "
                            "Rebuild and discover modules in the Monitor tab, then refresh."
                        )
                    else:
                        with st.spinner("Sending box to selected module..."):
                            result = control_module.inject_box_via_url(
                                ogm=ogm,
                                entry_module_iri=entry_module_id,
                                entry_module_url=entry_module_url,
                                box_iri=box_iri,
                                destination_iri=destination_iri,
                            )

                        status = result.get("status")
                        if status == "ok":
                            st.success(
                                f"Box injected successfully into module {entry_module_id} "
                                f"(HTTP {result.get('http_status')})."
                            )
                        elif status == "downstream_error":
                            st.error(
                                "The target module responded with an error "
                                f"(HTTP {result.get('http_status')})."
                            )
                        else:
                            st.error(
                                result.get("error", "Unknown error during injection")
                            )

                        with st.expander("Request details", expanded=False):
                            st.json(
                                {
                                    "receive_url": result.get("receive_url"),
                                    "payload": result.get("payload"),
                                    "response": result.get("response"),
                                }
                            )

                st.divider()
                st.subheader("Step-by-step Route Visualization")

                if "simulation_route" not in st.session_state:
                    st.session_state.simulation_route = []
                if "simulation_step_index" not in st.session_state:
                    st.session_state.simulation_step_index = 0

                sim_col1, sim_col2, sim_col3 = st.columns(3)

                start_clicked = sim_col1.button("Start", key="sim_start")
                step_clicked = sim_col2.button("Step", key="sim_step")
                stop_clicked = sim_col3.button("Stop", key="sim_stop")

                if start_clicked:
                    if not destination_iri:
                        st.error(
                            "Please select a destination module for visualization."
                        )
                    else:
                        # Build or reuse adjacency map from the monitor helpers
                        if not st.session_state.get("adjacency_matrix"):
                            monitor_module = importlib.import_module(
                                "utils.system_state_monitor"
                            )
                            st.session_state.adjacency_matrix = (
                                monitor_module.build_adjacency_matrix(ogm)
                            )

                        adj_map = st.session_state.adjacency_matrix
                        graph = route_module.build_topology_graph(adj_map)
                        route = route_module.dijkstra_shortest_path(
                            graph,
                            source=entry_module_id,
                            target=destination_iri,
                        )

                        if not route or len(route) < 2:
                            st.error(
                                "No valid route found between the selected modules."
                            )
                            st.session_state.simulation_route = []
                            st.session_state.simulation_step_index = 0
                        else:
                            st.session_state.simulation_route = route
                            st.session_state.simulation_step_index = 0

                if step_clicked and st.session_state.simulation_route:
                    if (
                        st.session_state.simulation_step_index
                        < len(st.session_state.simulation_route) - 1
                    ):
                        st.session_state.simulation_step_index += 1

                if stop_clicked:
                    st.session_state.simulation_route = []
                    st.session_state.simulation_step_index = 0

                current_module_for_box = None
                if st.session_state.simulation_route:
                    idx = st.session_state.simulation_step_index
                    if 0 <= idx < len(st.session_state.simulation_route):
                        current_module_for_box = st.session_state.simulation_route[idx]

                if not st.session_state.get("adjacency_matrix"):
                    st.info(
                        "No topology information available yet. Use the Monitor tab "
                        "to build the adjacency matrix or press Start to initialize it."
                    )
                else:
                    if not st.session_state.get("directional_rows"):
                        st.session_state.directional_rows = (
                            topology_module.adjacency_map_to_directional_rows(
                                st.session_state.adjacency_matrix
                            )
                        )

                    if st.session_state.directional_rows:
                        fig = topology_module.directional_rows_to_figure_with_box(
                            st.session_state.directional_rows,
                            current_module_for_box,
                        )
                        st.pyplot(fig, clear_figure=True)


# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #888; font-size: 0.85em;'>
    FlexConveyor Visualizer v1.0 | Powered by Streamlit & GraphDB
    </div>
    """,
    unsafe_allow_html=True,
)


def _is_streamlit_runtime() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def main() -> int:
    """Run this visualizer via `streamlit run` when invoked as a plain Python script."""
    if _is_streamlit_runtime():
        return 0

    env = os.environ.copy()
    env["FLEXCONVEYOR_STREAMLIT_WRAPPER"] = "1"
    script_path = Path(__file__).resolve()
    return subprocess.call(
        [sys.executable, "-m", "streamlit", "run", str(script_path)],
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
