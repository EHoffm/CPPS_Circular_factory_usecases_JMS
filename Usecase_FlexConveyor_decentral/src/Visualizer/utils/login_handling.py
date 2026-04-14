"""
Login Handling Module

Provides login UI components and session state management for GraphDB authentication.
"""

import streamlit as st
from graph_db_interface.utils.graph_db_credentials import GraphDBCredentials
from graph_db_interface import GraphDB
from graph_db_interface.utils.iri import IRI
<<<<<<< Updated upstream
from kapps_ogm import OGM
=======
from kapps_ogm.ogm import OGM
>>>>>>> Stashed changes


def initialize_login_session_state():
    """Initialize all login-related session state variables."""
    if "graphdb_credentials" not in st.session_state:
        st.session_state.graphdb_credentials = None

    if "graphdb_connected" not in st.session_state:
        st.session_state.graphdb_connected = False

    if "show_repo_selector" not in st.session_state:
        st.session_state.show_repo_selector = False

    if "available_repositories" not in st.session_state:
        st.session_state.available_repositories = []

    if "temp_credentials" not in st.session_state:
        st.session_state.temp_credentials = None

    if "ogm" not in st.session_state:
        st.session_state.ogm = None

    if "ogm_initialized" not in st.session_state:
        st.session_state.ogm_initialized = False


def render_connection_status():
    """Render the connection status and disconnect button."""
    if st.session_state.graphdb_connected:
        st.success("✅ Connected to GraphDB")
        if st.button("Disconnect", width="stretch"):
            st.session_state.graphdb_credentials = None
            st.session_state.graphdb_connected = False
            st.session_state.ogm = None
            st.session_state.ogm_initialized = False
            st.rerun()
    else:
        st.warning("❌ Not connected")


def render_manual_login():
    """Render manual login form with base URL, repository, username, and password."""
    st.subheader("Login Credentials")

    # Base URL
    base_url = st.text_input(
        "Base URL",
        value=st.session_state.get("temp_base_url", "http://localhost:7200"),
        key="input_base_url",
        help="GraphDB server base URL (e.g., http://localhost:7200)",
    )
    st.session_state.temp_base_url = base_url

    # Repository
    repository = st.text_input(
        "Repository",
        value=st.session_state.get("temp_repository", ""),
        key="input_repository",
        help="GraphDB repository name",
    )
    st.session_state.temp_repository = repository

    # Username
    username = st.text_input(
        "Username",
        value=st.session_state.get("temp_username", ""),
        key="input_username",
        help="GraphDB username",
    )
    st.session_state.temp_username = username

    # Password
    password = st.text_input(
        "Password",
        type="password",
        value=st.session_state.get("temp_password", ""),
        key="input_password",
        help="GraphDB password",
    )
    st.session_state.temp_password = password

    # Connect Button (Manual entry)
    if st.button("Connect to GraphDB", width="stretch", type="primary"):
        # Validate inputs
        if not base_url or not repository or not username or not password:
            st.error("❌ Please fill in all fields")
        else:
            try:
                # Create credentials object
                credentials = GraphDBCredentials(
                    base_url=base_url,
                    username=username,
                    password=password,
                    repository=repository,
                )

                # Test connection
                db = GraphDB(credentials=credentials)

                # Initialize OGM
                ogm = OGM(db=db)

                # Save to session state
                st.session_state.graphdb_credentials = credentials
                st.session_state.graphdb_connected = True
                st.session_state.ogm = ogm
                st.session_state.ogm_initialized = True

                st.success("✅ Connected successfully!")
                st.rerun()

            except Exception as e:
                st.error(f"❌ Connection failed: {str(e)}")


def render_env_login():
    """Render login from environment variables button and repository selector."""
    st.subheader("Or use environment variables")

    if st.button("Login from env", width="stretch"):
        try:
            # Create initial credentials from environment
            credentials = GraphDBCredentials.from_env()

            # Test connection and get available repositories
            db = GraphDB(credentials=credentials)
            repositories = db.get_list_of_repositories(only_ids=True)

            if repositories:
                # Store credentials and repositories, show selector
                st.session_state.temp_credentials = credentials
                st.session_state.available_repositories = repositories
                st.session_state.show_repo_selector = True
                st.rerun()
            else:
                st.error("❌ No repositories found on the GraphDB instance")

        except Exception as e:
            st.error(f"❌ Failed to load repositories: {str(e)}")

    # Repository selector (shown after fetching repositories)
    if st.session_state.show_repo_selector and st.session_state.available_repositories:
        st.info(
            f"Found {len(st.session_state.available_repositories)} repository/repositories"
        )

        selected_repo = st.selectbox(
            "Select Repository",
            options=st.session_state.available_repositories,
            key="selected_repository",
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Connect", width="stretch", type="primary"):
                try:
                    # Create new credentials with selected repository
                    credentials = GraphDBCredentials(
                        base_url=st.session_state.temp_credentials.base_url,
                        username=st.session_state.temp_credentials.username,
                        password=st.session_state.temp_credentials.password,
                        repository=selected_repo,
                    )

                    # Test connection
                    db = GraphDB(credentials=credentials)

                    # Initialize OGM
                    ogm = OGM(db=db)

                    # Save to session state
                    st.session_state.graphdb_credentials = credentials
                    st.session_state.graphdb_connected = True
                    st.session_state.ogm = ogm
                    st.session_state.ogm_initialized = True
                    st.session_state.show_repo_selector = False
                    st.session_state.available_repositories = []
                    st.session_state.temp_credentials = None

                    st.success(f"✅ Connected to repository: {selected_repo}")
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Connection failed: {str(e)}")

        with col2:
            if st.button("Cancel", width="stretch"):
                st.session_state.show_repo_selector = False
                st.session_state.available_repositories = []
                st.session_state.temp_credentials = None
                st.rerun()


def test_connection():
    """Test GraphDB connection by adding, retrieving, and deleting a test triple."""
    if not is_connected():
        st.warning("⚠️ Not connected to GraphDB")
        return

    try:
        db = GraphDB(credentials=st.session_state.graphdb_credentials)

        # Define test triple components
        test_subject = IRI("http://www.example.org/test/visualizer_test")
        test_predicate = IRI("http://www.example.org/test/hasTestStatus")
        test_object = IRI("http://www.example.org/test/success")
        test_triple = (test_subject, test_predicate, test_object)

        # Step 1: Add test triple
        st.info("🔄 Adding test triple...")
        db.triple_add(triple=test_triple)
        st.success("✅ Test triple added")

        # Step 2: Retrieve the triple
        st.info("🔄 Retrieving test triple...")
        results = db.triples_get(sub=test_subject)

        if results:
            st.success("✅ Test triple retrieved successfully")
            st.code(f"Retrieved {len(results)} triple(s):", language="text")
            for subject, predicate, obj in results:
                st.write(f"**Subject:** {subject}")
                st.write(f"**Predicate:** {predicate}")
                st.write(f"**Object:** {obj}")
        else:
            st.warning("⚠️ No triples retrieved")

        # Step 3: Delete the triple
        st.info("🔄 Deleting test triple...")
        db.triple_delete(triple=test_triple)
        st.success("✅ Test triple deleted")

        # Verify deletion
        st.info("🔄 Verifying deletion...")
        results_after_delete = db.triples_get(sub=test_subject)

        if not results_after_delete:
            st.success("✅ Connection test successful! Triple was properly deleted.")
        else:
            st.warning(f"⚠️ Found {len(results_after_delete)} triple(s) after deletion")

    except Exception as e:
        st.error(f"❌ Connection test failed: {str(e)}")


def render_connection_test():
    """Render connection test button (only visible when connected)."""
    st.divider()
    st.subheader("Connection Verification")
    if st.button("Test Connection", width="stretch", type="secondary"):
        test_connection()


def render_login_sidebar():
    """Render the complete login sidebar with all authentication options."""
    with st.sidebar:
        st.header("📊 GraphDB Connection")

        # Divider
        st.divider()

        # Display current connection status
        render_connection_status()

        if not is_connected():
            # Only show login forms when not connected
            # Divider
            st.divider()

            # Manual login form
            render_manual_login()

            # Divider
            st.divider()

            # Environment-based login
            render_env_login()
        else:
            # Only show connection test when connected
            render_connection_test()


def is_connected() -> bool:
    """Check if user is connected to GraphDB.

    Returns:
        bool: True if connected, False otherwise.
    """
    return st.session_state.graphdb_connected


def get_credentials() -> GraphDBCredentials:
    """Get the current GraphDB credentials from session state.

    Returns:
        GraphDBCredentials: The stored credentials, or None if not connected.
    """
    return st.session_state.graphdb_credentials


def get_ogm() -> OGM:
    """Get the current OGM instance from session state.

    Returns:
        OGM: The initialized OGM instance, or None if not initialized.
    """
    return st.session_state.ogm


def is_ogm_initialized() -> bool:
    """Check if OGM is initialized.

    Returns:
        bool: True if OGM is initialized, False otherwise.
    """
    return st.session_state.ogm_initialized
