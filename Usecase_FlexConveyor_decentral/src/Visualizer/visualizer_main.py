"""
FlexConveyor Visualizer - Main Entry Point

A Streamlit-powered user interface for the FlexConveyor system with GraphDB integration.
Provides system bootstrapping, runtime monitoring, and control capabilities.
"""

import streamlit as st
from utils.bootstrap import register_shutdown_handlers
from utils import (
    initialize_login_session_state,
    render_login_sidebar,
    is_connected,
    is_ogm_initialized,
    get_ogm,
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
            render_flex_module_instantiation(ogm)

    with tab2:
        st.header("Runtime Monitoring")
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
