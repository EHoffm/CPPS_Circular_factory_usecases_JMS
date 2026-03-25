# Plan: Funktion zum starten des generierens von Boxen alle x Sekunden
# hier für über GraphDB infos prüfen welche Module frei sind
# dann start auf ein zufälliges freies Modul setzen und ende auf ein anderes zufälliges Modul

from datetime import datetime
import time
import random
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from graph_db_interface import IRI
from kapps_ogm import OGM

from CPPS_Circular_factory_usecases_JMS.Usecase_FlexConveyor_decentral.src.Visualizer.utils.flex_module_instance import (
    extract_fields_from_instance,
)
from CPPS_Circular_factory_usecases_JMS.Usecase_FlexConveyor_decentral.src.mock_wms.bootstrap_boxes import (
    create_blank_box_instance,
    instantiate_boxes,
)


def generate_box(ogm: OGM):
    """
    Generates a box on a random free FlexConveyor module in the system.

    Args:
        ogm: The OGM instance connected to GraphDB
    """
    print("entered generate box")
    # Query GraphDB for free FlexConveyor modules
    discovered_modules = st.session_state.get("discovered_modules", [])
    free_modules = []
    property_possession = IRI(
        "http://w3id.org/circularfactory/FlexConveyor#hasPossession"
    )
    # add module to the list of free modules, if the module has no value for hasPossession (no Box on it)
    for module in discovered_modules:
        # TODO: hier ggf statt triples_get mit query arbeiten?
        triples = ogm.db.triples_get(
            subj=IRI(module["module_id"]), pred=property_possession
        )

        has_value = len(triples) > 0
        value = str(triples[0][2]) if has_value else None
        if value == None:
            free_modules.append(module)
        print(f"Tripel: {triples}, has_value: {has_value}, value: {value}")

    print(f"Module:{discovered_modules}")
    print(f"freie Module:{free_modules}")
    print(f"Länge von discovered_modules{len(discovered_modules)}")
    if len(discovered_modules) < 2 or not discovered_modules:
        st.session_state.box_generation_active = False
        st.session_state.next_box_time = None
        st.info(
            "Box generation is stopped. Please add at least two FlexConveyorModules before starting the box generation again."
        )
    elif not free_modules:
        print("No free FlexConveyor modules available. Retrying...")
    else:
        # Randomly select a start and end module from the free modules
        start_module = random.choice(free_modules)
        end_module = random.choice([m for m in discovered_modules if m != start_module])

        # Generate a box on the start module and set it to move to the end module
        # TODO: erzeuge Box instanz mit den start_module und end_module daten und
        # passe hasPossession von dem Modul auf das die Box gesetzt wird an.
        # Dann starte Wegfindung und transport der Box

        # the data for the new box (at the moment just one box, but can be more)
        boxes = []
        timestemp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hasOrigin = IRI("http://w3id.org/circularfactory/FlexConveyor#hasOrigin").lined
        print(hasOrigin)
        hasDestination = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#hasDestination"
        ).lined
        hasState = IRI("http://w3id.org/circularfactory/FlexConveyor#hasState").lined
        isPossessedBy = IRI(
            "http://w3id.org/circularfactory/FlexConveyor#isPossessedBy"
        ).lined
        box_data = {
            "id": f"http://w3id.org/circularfactory/BoxInstances#box_{timestemp}",
            hasOrigin: start_module.get("module_id"),
            hasDestination: end_module.get("module_id"),
            hasState: "http://w3id.org/circularfactory/FlexConveyor#Created",
            isPossessedBy: start_module.get("module_id"),
        }
        boxes.append(box_data)
        instantiate_boxes(boxes, ogm)
        print(f"Generated box on {start_module} moving to {end_module}")


def check_and_generate_box(ogm: OGM, interarrival_time):
    """Prüft, ob eine Box erzeugt werden soll, und aktualisiert den Timer."""
    now = time.time()
    if st.session_state.box_generation_active and now >= st.session_state.next_box_time:
        generate_box(ogm)
        st.session_state.next_box_time = now + interarrival_time


def render_box_instantiation(ogm: OGM):
    initialize_box_instance_session_state()
    # automatic re-run every second
    st_autorefresh(interval=1000, key="timer_refresh")

    interarrival_time = 10  # default value
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        box_interarrival_time_input = st.text_input(
            "Enter interarrival time for the boxes (seconds)", ""
        )

    with col2:
        if st.button("Start box generation"):
            st.session_state.box_generation_active = True
            try:
                interarrival_time = int(box_interarrival_time_input)
            except ValueError:
                interarrival_time = 10
            st.session_state.next_box_time = time.time() + interarrival_time
            st.info(f"Box generation started with {interarrival_time}s interval.")
            # Create blank instance
            # blank_instance = create_blank_box_instance(ogm)

            # Extract fields
            # fields = extract_fields_from_instance(blank_instance)
            # print(fields)
            # Store in session state
            # st.session_state.box_instance_fields = fields

    with col3:
        if st.button("Stop box generation"):
            st.session_state.box_generation_active = False
            st.session_state.next_box_time = None

    if st.session_state.box_generation_active:
        check_and_generate_box(ogm, interarrival_time)


def initialize_box_instance_session_state():
    """Initialize session state variables for Box instance management."""
    if "box_instance_fields" not in st.session_state:
        st.session_state.box_instance_fields = None

    if "boxes" not in st.session_state:
        st.session_state.boxes = []

    if "editing_box_index" not in st.session_state:
        st.session_state.editing_box_index = None

    if "editing_box_fields" not in st.session_state:
        st.session_state.editing_box_fields = None

    if "box_generation_active" not in st.session_state:
        st.session_state.box_generation_active = False

    if "next_box_time" not in st.session_state:
        st.session_state.next_box_time = None
