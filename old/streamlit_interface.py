"""
FlexConveyor System Streamlit Interface

A web interface for managing and visualizing the FlexConveyor system,
allowing users to add parcels, visualize the system, and control parcel movement.
"""

import re
from typing import Dict, List, Tuple, Optional, Any

import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.axes import Axes

from flexconveyor_system import FlexConveyorSystem

# Constants
DEFAULT_IRI = "https://www.sfb1574.kit.edu/ontologies/FlexConveyor#exampleSystem1"
IRI_PATTERN = r"^https://www\.sfb1574\.kit\.edu/ontologies/FlexConveyor#"
DIRECTION_SYMBOLS = ["↑", "→", "↓", "←"]
DIRECTION_NAMES = ["north", "east", "south", "west"]
DIRECTIONS_COORDS = [(0, 1), (1, 0), (0, -1), (-1, 0)]  # north, east, south, west


# Utility Functions
def shorten_iri(iri: str) -> str:
    """Convert full IRI to shortened form by removing the base namespace."""
    return re.sub(IRI_PATTERN, "", iri)


def initialize_session_state(system_iri: str) -> None:
    """Initialize or update session state variables."""
    if (
        "system" not in st.session_state
        or st.session_state.get("system_iri") != system_iri
    ):
        st.session_state.system = FlexConveyorSystem(system_iri)
        st.session_state.system_iri = system_iri
        st.session_state.parcels = []
        st.session_state.selected_parcel = None
        if hasattr(st.session_state, "path"):
            st.session_state.path = None


# Main App
st.title("FlexConveyor System Interface")

# System IRI input
system_iri = st.text_input(
    "System IRI",
    value=DEFAULT_IRI,
    help="Enter the IRI of the FlexConveyor system to manage",
)

# Initialize session state
initialize_session_state(system_iri)

system = st.session_state.system
modules = list(system.adjacency_matrix.keys())


# Visualization Functions
def compute_module_positions(
    adjacency_matrix: Dict[str, List[str]],
) -> Dict[str, Tuple[int, int]]:
    """
    Compute 2D positions for modules using BFS to create a grid layout.

    Args:
        adjacency_matrix: Dictionary mapping modules to their connections in [N, E, S, W] order

    Returns:
        Dictionary mapping module IRIs to (x, y) coordinates
    """
    positions = {}
    modules = list(adjacency_matrix.keys())
    if not modules:
        return positions

    # Start with first module at origin
    queue = [modules[0]]
    positions[modules[0]] = (0, 0)
    visited = {modules[0]}

    while queue:
        current_module = queue.pop(0)
        if current_module not in adjacency_matrix:
            continue

        x, y = positions[current_module]
        connections = adjacency_matrix[current_module]

        for i, target_module in enumerate(connections):
            if target_module and target_module not in positions:
                dx, dy = DIRECTIONS_COORDS[i]
                positions[target_module] = (x + dx, y + dy)

                if target_module in adjacency_matrix and target_module not in visited:
                    queue.append(target_module)
                    visited.add(target_module)

    return positions


def draw_conveyor_image(fig_size: int = 8) -> Figure:
    """
    Create a matplotlib figure showing the conveyor system layout with parcels and paths.

    Args:
        fig_size: Size of the figure (default: 8)

    Returns:
        Matplotlib figure object
    """
    try:
        positions = compute_module_positions(system.adjacency_matrix)
        fig, ax = plt.subplots(figsize=(fig_size, fig_size))
        square_size = 1

        # Draw modules as rectangles
        for module_iri, (x, y) in positions.items():
            rect = mpatches.Rectangle(
                (x * square_size, y * square_size),
                square_size,
                square_size,
                facecolor="lightblue",
                edgecolor="black",
                linewidth=1,
            )
            ax.add_patch(rect)

            # Add module label
            ax.text(
                x * square_size + 0.05,
                y * square_size + square_size - 0.15,
                shorten_iri(module_iri),
                fontsize=8,
                ha="left",
                va="top",
                weight="bold",
            )

        # Refresh and draw parcels from the system
        system.get_parcels()
        _draw_system_parcels(ax, positions, square_size)
        _draw_session_parcels(ax, positions, square_size)
        _draw_path_if_exists(ax, positions, square_size)

        # Set axis limits and remove axes
        if positions:
            x_coords = [x for x, y in positions.values()]
            y_coords = [y for x, y in positions.values()]
            ax.set_xlim(min(x_coords) - 1, max(x_coords) + 2)
            ax.set_ylim(min(y_coords) - 1, max(y_coords) + 2)

        ax.set_aspect("equal")
        ax.axis("off")
        return fig

    except Exception as e:
        st.error(f"Error creating visualization: {e}")
        # Return empty figure on error
        fig, ax = plt.subplots(figsize=(fig_size, fig_size))
        ax.text(
            0.5,
            0.5,
            "Error loading visualization",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.axis("off")
        return fig


def _draw_system_parcels(
    ax: Axes, positions: Dict[str, Tuple[int, int]], square_size: float
) -> None:
    """Draw parcels that exist in the system database."""
    if not system.parcels:
        return

    for parcel_iri, info in system.parcels.items():
        position = positions.get(info["current_position"])
        if position:
            x, y = position
            circle = mpatches.Circle(
                (x * square_size + 0.5, y * square_size + 0.5),
                0.2,
                color="orange",
                zorder=10,
            )
            ax.add_patch(circle)
            ax.text(
                x * square_size + 0.5,
                y * square_size + 0.5,
                shorten_iri(parcel_iri),
                color="white",
                fontsize=8,
                ha="center",
                va="center",
                zorder=11,
                weight="bold",
            )


def _draw_session_parcels(
    ax: Axes, positions: Dict[str, Tuple[int, int]], square_size: float
) -> None:
    """Draw parcels from the session state (temporary parcels)."""
    for idx, parcel in enumerate(st.session_state.parcels):
        position = positions.get(parcel["entrance"])
        if position:
            x, y = position
            circle = mpatches.Circle(
                (x * square_size + 0.5, y * square_size + 0.5),
                0.2,
                color="orange",
                zorder=10,
            )
            ax.add_patch(circle)
            ax.text(
                x * square_size + 0.5,
                y * square_size + 0.5,
                str(idx + 1),
                color="white",
                fontsize=10,
                ha="center",
                va="center",
                zorder=11,
                weight="bold",
            )


def _draw_path_if_exists(
    ax: Axes, positions: Dict[str, Tuple[int, int]], square_size: float
) -> None:
    """Draw the current path if one exists."""
    if not (hasattr(st.session_state, "path") and st.session_state.path):
        return

    path = st.session_state.path
    path_positions = [positions.get(module) for module in path if module in positions]
    path_positions = [pos for pos in path_positions if pos is not None]

    if len(path_positions) > 1:
        xs, ys = zip(
            *[(x * square_size + 0.5, y * square_size + 0.5) for x, y in path_positions]
        )
        ax.plot(xs, ys, color="red", linewidth=3, zorder=20, alpha=0.8)
        ax.scatter(
            xs[0],
            ys[0],
            color="green",
            s=100,
            zorder=21,
            marker="o",
            edgecolor="darkgreen",
        )
        ax.scatter(
            xs[-1],
            ys[-1],
            color="red",
            s=100,
            zorder=21,
            marker="s",
            edgecolor="darkred",
        )


# UI Helper Functions
def refresh_parcels_and_check_completions() -> None:
    """Refresh parcels and display info messages for any that completed their journey."""
    # Store current parcels before refresh
    parcels_before = dict(system.parcels)

    # Refresh parcels (this will auto-remove completed ones in the backend)
    system.get_parcels()

    # Check which parcels were removed
    parcels_after = set(system.parcels.keys())
    parcels_before_set = set(parcels_before.keys())
    removed_parcels = parcels_before_set - parcels_after

    # Display info message for each removed parcel
    for parcel_iri in removed_parcels:
        parcel_info = parcels_before.get(parcel_iri, {})
        destination = parcel_info.get("destination", "unknown destination")
        info_placeholder.info(
            f"Parcel {shorten_iri(parcel_iri)} reached its final destination "
            f"({shorten_iri(destination)}) and left the system."
        )


def handle_convey_operation(
    parcel_iri: str,
    current_pos: str,
    target_module: str,
    direction_name: str,
    log_placeholder,
    error_placeholder,
    image_placeholder,
) -> None:
    """
    Handle the conveying operation for a parcel with proper error handling.

    Args:
        parcel_iri: IRI of the parcel to move
        current_pos: Current position of the parcel
        target_module: Target module to move to
        direction_name: Direction symbol for logging
        log_placeholder: Streamlit placeholder for success messages
        error_placeholder: Streamlit placeholder for error messages
        image_placeholder: Streamlit placeholder for image updates
    """
    try:
        system.get_parcels()
        result, log_msg = system.convey(current_pos, target_module)

        short_parcel = shorten_iri(parcel_iri)
        short_current = shorten_iri(current_pos)
        short_target = shorten_iri(target_module)

        log_placeholder.success(
            f"Conveyed parcel {short_parcel} {direction_name} from {short_current} to {short_target}"
        )

        if log_msg:
            info_placeholder.info(log_msg)

        # Refresh parcels and check for completions
        refresh_parcels_and_check_completions()

        image_placeholder.pyplot(draw_conveyor_image())
        st.rerun()

    except Exception as e:
        error_placeholder.error(f"Convey operation failed: {str(e)}")
        image_placeholder.pyplot(draw_conveyor_image())


def create_parcel_table() -> None:
    """Create and display the interactive parcel management table."""
    st.subheader("Parcels in System")

    if not system.parcels:

        return

    # Table headers
    cols = st.columns([2, 2, 2, 4])
    cols[0].markdown("**Parcel Name**")
    cols[1].markdown("**Current Position**")
    cols[2].markdown("**Destination**")
    cols[3].markdown("**Convey Directions**")

    # Create placeholders for messages
    log_placeholder = st.empty()

    # Interactive parcel rows
    for parcel_iri, position_info in system.parcels.items():
        col1, col2, col3, col4 = st.columns([2, 2, 2, 4])

        short_parcel_iri = shorten_iri(parcel_iri)
        short_current_position = shorten_iri(position_info["current_position"])
        short_destination = shorten_iri(position_info.get("destination", "N/A"))

        # Clickable parcel name for selection
        if col1.button(short_parcel_iri, help="Click to select this parcel"):
            st.session_state.selected_parcel = (parcel_iri, position_info)

        col2.write(short_current_position)
        col3.write(short_destination)

        # Direction buttons
        current_pos = position_info["current_position"]
        connections = system.adjacency_matrix.get(current_pos, [])

        with col4:
            direction_cols = st.columns(4)
            for idx, target_module in enumerate(connections):
                if target_module:  # If there's a connection in this direction
                    direction_symbol = DIRECTION_SYMBOLS[idx]
                    button_key = f"convey_{short_parcel_iri}_{direction_symbol}"

                    with direction_cols[idx]:
                        if st.button(
                            f"{direction_symbol}",
                            key=button_key,
                            help=f"Move to {shorten_iri(target_module)}",
                        ):
                            handle_convey_operation(
                                parcel_iri,
                                current_pos,
                                target_module,
                                direction_symbol,
                                log_placeholder,
                                error_placeholder,  # Use global error placeholder
                                image_placeholder,
                            )


def create_pathfinding_section() -> None:
    """Create the pathfinding and automated convey section."""
    if not st.session_state.selected_parcel:
        return

    parcel_iri, position_info = st.session_state.selected_parcel

    st.subheader("Selected Parcel Control")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.write(f"**Parcel:** {shorten_iri(parcel_iri)}")
        st.write(
            f"**Current Position:** {shorten_iri(position_info['current_position'])}"
        )

    with col2:
        if st.button("Deselect", help="Clear selected parcel"):
            st.session_state.selected_parcel = None
            if hasattr(st.session_state, "path"):
                st.session_state.path = None
            st.rerun()

    dest_full_iri = position_info.get("destination")
    if not dest_full_iri:
        st.warning("This parcel has no destination set.")
        return

    st.write(f"**Destination:** {shorten_iri(dest_full_iri)}")

    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("Find Path", help="Calculate path to destination"):
            try:
                path = system.find_path(
                    position_info["current_position"], dest_full_iri
                )
                st.session_state.path = path

                if path:
                    st.success(
                        f"Path found: {' → '.join([shorten_iri(p) for p in path])}"
                    )
                else:
                    error_placeholder.error("No path found to destination.")
            except Exception as e:
                error_placeholder.error(f"Pathfinding error: {e}")

    with col2:
        if (
            hasattr(st.session_state, "path")
            and st.session_state.path
            and len(st.session_state.path) > 1
        ):
            if st.button("Convey Next", help="Move parcel one step along path"):
                _handle_path_convey(parcel_iri, position_info)


def _handle_path_convey(parcel_iri: str, position_info: Dict[str, Any]) -> None:
    """Handle conveying along a calculated path."""
    try:
        path = st.session_state.path
        current_pos = path[0]
        next_pos = path[1]

        # Find direction index
        for idx, target in enumerate(system.adjacency_matrix.get(current_pos, [])):
            if target == next_pos:
                result, log_msg = system.convey(current_pos, next_pos)

                st.success(
                    f"Conveyed {shorten_iri(parcel_iri)} from {shorten_iri(current_pos)} to {shorten_iri(next_pos)}"
                )

                if log_msg:
                    info_placeholder.info(log_msg)

                # Refresh parcels and check for completions
                refresh_parcels_and_check_completions()

                # Update path by removing first element
                st.session_state.path = path[1:]

                # Clear path if destination reached
                if next_pos == position_info.get("destination"):
                    st.session_state.path = None
                    st.session_state.selected_parcel = None

                st.rerun()
                break
        else:
            error_placeholder.error(
                "Could not determine direction for convey operation."
            )

    except Exception as e:
        error_placeholder.error(f"Path convey error: {e}")


def create_add_parcel_section() -> None:
    """Create the add new parcel section."""
    st.subheader("Add New Parcel")

    if not modules:
        st.error("No modules available in the system.")
        return

    # Create mapping between short names and full IRIs
    module_options = {shorten_iri(module): module for module in modules}
    short_module_names = list(module_options.keys())

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        entrance_short = st.selectbox(
            "Entrance Position",
            short_module_names,
            key="entrance_select",
            help="Select where the parcel enters the system",
        )

    with col2:
        target_short = st.selectbox(
            "Destination",
            short_module_names,
            key="target_select",
            help="Select the parcel's final destination",
        )

    with col3:
        st.write("")  # Spacer
        if st.button("Add Parcel", help="Add parcel to the system"):
            if entrance_short == target_short:
                st.warning("Entrance and destination cannot be the same.")
                return

            entrance_full = module_options[entrance_short]
            target_full = module_options[target_short]

            try:
                system.add_parcel(target_full, entrance_full)
                st.success(f"Parcel added from {entrance_short} to {target_short}!")
                refresh_parcels_and_check_completions()
                st.rerun()
            except Exception as e:
                error_placeholder.error(f"Failed to add parcel: {str(e)}")


# Main UI Layout
st.markdown("---")

# Configuration sidebar
with st.sidebar:
    st.header("System Configuration")

    # Auto-refresh option
    auto_refresh = st.checkbox(
        "Auto-refresh parcels", value=True, help="Automatically refresh parcel data"
    )

    # Visualization options
    st.subheader("Visualization")
    show_grid = st.checkbox("Show grid lines", value=False)
    fig_size = st.slider("Figure size", min_value=6, max_value=12, value=8)

    # System info
    st.subheader("System Info")
    if modules:
        st.metric("Total Modules", len(modules))
        st.metric("Active Parcels", len(system.parcels))

    # Help section
    with st.expander("Help"):
        st.markdown(
            """
        **How to use this interface:**
        
        1. **View System**: The visualization shows modules (blue squares) and parcels (orange circles)
        2. **Select Parcels**: Click on parcel names to select them
        3. **Move Parcels**: Use direction arrows (↑→↓←) to move parcels manually
        4. **Auto-Path**: Use "Find Path" and "Convey Next" for automated movement
        5. **Add Parcels**: Use the form at the bottom to add new parcels
        
        **Legend:**
        - Blue squares: Modules
        - Orange circles: Parcels  
        - Green marker: Start position
        - Red marker: End position
        - Red line: Path
        """
        )

# Initialize placeholders for dynamic content
image_placeholder = st.empty()

# Display the conveyor system visualization
# Error placeholder directly under the image
error_placeholder = st.empty()

# Info placeholder directly under the error placeholder
info_placeholder = st.empty()

try:
    with st.spinner("Loading system visualization..."):
        fig = draw_conveyor_image(fig_size)
        if show_grid:
            fig.axes[0].grid(True, alpha=0.3)
        image_placeholder.pyplot(fig)
        # Don't clear error or info messages - let them persist until replaced
except Exception as e:
    error_placeholder.error(f"Failed to load system visualization: {e}")

st.markdown("---")

# Create the parcel management interface
create_parcel_table()

st.markdown("---")

# Create pathfinding section
create_pathfinding_section()

st.markdown("---")

# Create add parcel section
create_add_parcel_section()

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; font-size: 0.9em;'>
        FlexConveyor System Interface | Built with Streamlit
    </div>
    """,
    unsafe_allow_html=True,
)


def main():
    """Main function for console script entry point."""
    import streamlit.web.cli as stcli
    import sys
    import os

    # Get the path to this file
    script_path = os.path.abspath(__file__)

    # Run streamlit with this script
    sys.argv = ["streamlit", "run", script_path]
    sys.exit(stcli.main())


if __name__ == "__main__":
    # This allows the script to be run directly with python
    pass
