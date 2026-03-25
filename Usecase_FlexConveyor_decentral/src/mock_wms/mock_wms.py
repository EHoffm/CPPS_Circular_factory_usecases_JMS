# Plan: Funktion zum starten des generierens von Boxen alle x Sekunden
# hier für über GraphDB infos prüfen welche Module frei sind
# dann start auf ein zufälliges freies Modul setzen und ende auf ein anderes zufälliges Modul

import datetime
import time
import random
import streamlit as st

from graph_db_interface import IRI
from kapps_ogm import OGM

from CPPS_Circular_factory_usecases_JMS.Usecase_FlexConveyor_decentral.src.mock_wms.bootstrap_boxes import (
    instantiate_boxes,
)


def generate_box(ogm: OGM):
    """
    Generates a box on a random free FlexConveyor module in the system.

    Args:
        ogm: The OGM instance connected to GraphDB
    """
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

    if not free_modules:
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
    time = datetime.now().strftime("%Y%m%d_%H%M%S")
    hasOrigin = IRI("http://w3id.org/circularfactory/FlexConveyor#hasOrigin").lined()
    hasDestination = IRI(
        "http://w3id.org/circularfactory/FlexConveyor#hasDestination"
    ).lined()
    hasState = IRI("http://w3id.org/circularfactory/FlexConveyor#hasState").lined()
    isPossessedBy = IRI(
        "http://w3id.org/circularfactory/FlexConveyor#isPossessedBy"
    ).lined()
    box_data = {
        "id": f"http://w3id.org/circularfactory/BoxInstances#box_{time}",
        hasOrigin: start_module,
        hasDestination: end_module,
        hasState: "http://w3id.org/circularfactory/FlexConveyor#Created",
        isPossessedBy: start_module,
    }
    boxes.append(box_data)
    instantiate_boxes(boxes, ogm)
    print(f"Generated box on {start_module} moving to {end_module}")


def check_and_generate_box(ogm: OGM, interarrival_time):
    """Prüft, ob eine Box erzeugt werden soll, und aktualisiert den Timer."""
    if st.session_state.box_generation_active:
        if st.session_state.next_box_time is None:
            st.session_state.next_box_time = time.time() + interarrival_time
        elif time.time() >= st.session_state.next_box_time:
            generate_box(ogm)
            st.session_state.next_box_time = time.time() + interarrival_time
            st.experimental_rerun()  # Timer for the next box


def render_box_instantiation(ogm: OGM):
    initialize_box_instance_session_state()

    if "box_generation_active" not in st.session_state:
        st.session_state.box_generation_active = False
    if "next_box_time" not in st.session_state:
        st.session_state.next_box_time = None

    col1, col2, col3 = st.columns([1, 1, 1])
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

    with col3:
        if st.button("Stop box generation"):
            st.session_state.box_generation_active = False
            st.session_state.next_box_time = None

    # check for new box
    try:
        interarrival_time = int(box_interarrival_time_input)
    except ValueError:
        interarrival_time = 10

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
