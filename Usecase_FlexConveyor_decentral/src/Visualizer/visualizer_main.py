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


def _bootstrap_import_paths() -> None:
    script_path = Path(__file__).resolve()
    package_dirs = (
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

    # Navigation tabs
    tab1, tab2, tab3 = st.tabs(["🏗️ Bootstrap", "📊 Monitor", "🎮 Control"])

    with tab1:
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

    with tab2:
        st.header("Runtime Monitoring")
        if "discovered_modules" not in st.session_state:
            st.session_state.discovered_modules = []
        if "adjacency_matrix" not in st.session_state:
            st.session_state.adjacency_matrix = {}

        action_col1, action_col2 = st.columns(2)

        if action_col1.button(
            "discover instantiated modules", key="discover_instantiated_modules"
        ):
            monitor_module = importlib.import_module("utils.system_state_monitor")
            monitor_module = importlib.reload(monitor_module)
            st.session_state.discovered_modules = monitor_module.discover_modules(
                st.session_state.get("ogm")
            )

        if action_col2.button(
            "build adjacency matrix", key="build_adjacency_matrix"
        ):
            monitor_module = importlib.import_module("utils.system_state_monitor")
            monitor_module = importlib.reload(monitor_module)
            st.session_state.adjacency_matrix = monitor_module.build_adjacency_matrix(
                st.session_state.get("ogm")
            )

        if st.session_state.adjacency_matrix:
            st.subheader("Adjacency Matrix")
            st.json(st.session_state.adjacency_matrix)

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

        st.info("Coming soon: Real-time system visualization")

    with tab3:
        st.header("Runtime Control")
        st.info("Coming soon: Simulation and box injection controls")


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
