import os
import sys
import time

# Prevent threading locks & segmentation faults in Streamlit / PyTorch / HuggingFace
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except Exception:
    pass

import pandas as pd
import streamlit as st

from auth import (AuthError, SESSION_TTL_SECONDS, credentials_configured,
                  issue_session_token, verify_session_token)
from preprocess import process_and_save, DATA_SOURCES
from rag_engine import search_and_answer
from context_engine import query_massive_context

# Page Configuration
st.set_page_config(
    page_title="User Feedback Discovery Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich Aesthetics
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E88E5;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #546E7A;
        margin-bottom: 1.5rem;
    }
    .stCard {
        background-color: #F8F9FA;
        border-radius: 10px;
        padding: 1.2rem;
        border: 1px solid #E0E0E0;
        margin-bottom: 1rem;
    }
    .metric-badge {
        background-color: #E3F2FD;
        color: #1565C0;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# LLM Configuration (server-side only; never sent to the browser)
PROVIDER = "gemini"           # dispatch key for llm_provider.query_llm()
PROVIDER_LABEL = "Google Gemini"
MODEL_NAME = "gemini-flash-latest"


def get_api_key():
    """Reads GEMINI_API_KEY from the environment, falling back to st.secrets.

    The key is used only for server-side calls in llm_provider.py and is never
    bound to a widget, so it never reaches the client.

    st.secrets raises StreamlitSecretNotFoundError (not KeyError) when no
    secrets.toml exists at all, which is the normal case for a fresh clone.
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        return ""


API_KEY = get_api_key()

if not API_KEY:
    # Fail the process rather than rendering a configuration error in the browser.
    # run.sh performs this same check before the server starts; this guard covers
    # `streamlit run app.py` invoked directly.
    sys.stderr.write(
        "\nERROR: GEMINI_API_KEY is not set.\n\n"
        "This app reads the Google Gemini API key from the server environment.\n"
        "Set it and try again:\n\n"
        "    export GEMINI_API_KEY=\"your-key-here\"\n"
        "    ./run.sh\n\n"
        "On Streamlit Community Cloud, add it under App settings -> Secrets as\n"
        "    GEMINI_API_KEY = \"your-key-here\"\n\n"
    )
    sys.stderr.flush()
    os._exit(1)


# --- Authentication ----------------------------------------------------------
if not credentials_configured():
    sys.stderr.write(
        "\nERROR: APP_USERNAME and APP_PASSWORD are not set.\n\n"
        "Set them in the server environment and try again:\n\n"
        "    export APP_USERNAME=\"your-username\"\n"
        "    export APP_PASSWORD=\"your-password\"\n"
        "    export APP_SECRET_KEY=\"$(python3 -c 'import secrets;print(secrets.token_hex(32))')\"\n"
        "    ./run.sh\n\n"
        "On Streamlit Community Cloud, add them under App settings -> Secrets.\n\n"
    )
    sys.stderr.flush()
    os._exit(1)


def current_session_token():
    """Returns the active token, clearing it once the 72-hour window closes."""
    token = st.session_state.get("session_token", "")
    if not token:
        return ""
    try:
        verify_session_token(token)
        return token
    except AuthError as e:
        st.session_state.clear()
        st.session_state["auth_message"] = str(e)
        return ""


def require_login():
    """Renders the sign-in form until the visitor holds a valid session token.

    Streamlit re-runs this script top to bottom on every interaction, so the
    token lives in st.session_state and is re-verified on each run. Nothing
    below this call executes for an unauthenticated session.
    """
    if current_session_token():
        return

    st.markdown('<div class="main-header">🔍 User Feedback Discovery Engine</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Sign in to continue.</div>', unsafe_allow_html=True)

    expired = st.session_state.get("auth_message")
    if expired:
        st.warning(expired)

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary")

        if submitted:
            from auth import verify_credentials
            if verify_credentials(username, password):
                st.session_state.clear()
                st.session_state["session_token"] = issue_session_token(username.strip())
                st.session_state["username"] = username.strip()
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.stop()


require_login()
SESSION_TOKEN = current_session_token()


# Sidebar Configuration
st.sidebar.title("⚙️ Engine Configuration")

st.sidebar.subheader("1. LLM Provider")
st.sidebar.caption(f"Provider: **{PROVIDER_LABEL}**")
st.sidebar.caption(f"Model: `{MODEL_NAME}`")
st.sidebar.caption("API key loaded from the server environment.")

st.sidebar.divider()

# 2. Data Source Checkboxes (Default: ALL CHECKED)
st.sidebar.subheader("2. Data Source Selection")
st.sidebar.caption("By default, all 8 public feedback sources are selected:")

selected_sources = []
for key, info in DATA_SOURCES.items():
    # Checkbox checked by default as requested!
    is_checked = st.sidebar.checkbox(
        label=info["name"],
        value=True,
        key=f"chk_{key}"
    )
    if is_checked:
        selected_sources.append(key)

st.sidebar.divider()

_expiry = verify_session_token(SESSION_TOKEN)["exp"]
_hours_left = max(0, int((_expiry - time.time()) // 3600))
st.sidebar.caption(f"Signed in as **{st.session_state.get('username', '')}**")
st.sidebar.caption(f"Session expires in ~{_hours_left}h (max {SESSION_TTL_SECONDS // 3600}h).")
if st.sidebar.button("Sign out"):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()

# Automatic initialization check for Streamlit Cloud deployment
csv_path = os.path.join(os.path.dirname(__file__), "processed_data", "unified_feedback.csv")
vector_db_path = os.path.join(os.path.dirname(__file__), "vector_db")

if not os.path.exists(csv_path) or not os.path.exists(vector_db_path) or not os.listdir(vector_db_path):
    with st.spinner("Initializing dataset and building vector database for first-time setup..."):
        process_and_save()

# 3. Data Re-processing Trigger
if st.sidebar.button("🔄 Run / Refresh Data Pre-processing"):
    with st.spinner("Processing 8 raw datasets & building vector index..."):
        csv_out = process_and_save()
        st.sidebar.success("✅ Pre-processing & indexing complete!")


# Main Application Interface
st.markdown('<div class="main-header">🔍 User Feedback Discovery Engine</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Ingest user feedback across 8 public domain sources & ask natural language questions using AI.</div>', unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3 = st.tabs([
    "🎯 Tab 1: RAG Discovery Engine (Approaches 1 & 3)",
    "⚡ Tab 2: Massive Context Engine (5th Approach)",
    "📊 Tab 3: Data Explorer & Stats"
])


# TAB 1: RAG DISCOVERY ENGINE
with tab1:
    st.subheader("RAG Discovery Engine (Vector Search + Semantic QA)")
    st.caption("Retrieves top matching feedback snippets from ChromaDB and generates a grounded answer.")

    col1, col2 = st.columns([3, 1])
    with col1:
        user_query = st.text_input(
            "Ask a question to the user feedback engine:",
            placeholder="e.g., What are the main customer complaints regarding returns and refunds?",
            key="rag_query"
        )
    with col2:
        top_k = st.slider("Top-K Snippets to Retrieve", min_value=1, max_value=20, value=5)

    if st.button("🚀 Ask RAG Engine", type="primary", key="btn_rag"):
        if not selected_sources:
            st.warning("Please select at least one data source from the sidebar checkboxes.")
        elif not user_query.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner(f"Retrieving top {top_k} matches from ChromaDB & querying {PROVIDER_LABEL}..."):
                answer, citations = search_and_answer(
                    query=user_query,
                    selected_sources=selected_sources,
                    provider=PROVIDER,
                    api_key=API_KEY,
                    model_name=MODEL_NAME,
                    top_k=top_k,
                    session_token=SESSION_TOKEN
                )

            st.markdown("### 💡 Direct Answer")
            st.info(answer)

            if citations:
                st.markdown("### 📚 Retrieved Context Snippets")
                for cite in citations:
                    with st.expander(f"Snippet #{cite['index']} | {cite['source']} ({cite['platform']}) - Author: {cite['author']}"):
                        st.markdown(f"**Rating:** {cite['rating']}")
                        if cite['url']:
                            st.markdown(f"**URL:** [{cite['url']}]({cite['url']})")
                        st.write(cite['text'])


# TAB 2: MASSIVE CONTEXT ENGINE (5TH APPROACH)
with tab2:
    st.subheader("Massive Context Engine (5th Approach - Whole Dataset Prompting)")
    st.caption("Feeds the entire filtered CSV text directly into an LLM with massive context window. Supports Context Caching.")

    caching_enabled = st.checkbox("Enable Context Caching Optimization (Recommended for Gemini / Claude)", value=True)

    mc_query = st.text_input(
        "Ask a holistic question over the entire dataset:",
        placeholder="e.g., Synthesize the top 5 distinct customer issues across all platforms and rank them by frequency.",
        key="mc_query"
    )

    if st.button("⚡ Query Whole-Dataset Engine", type="primary", key="btn_mc"):
        if not selected_sources:
            st.warning("Please select at least one data source from the sidebar checkboxes.")
        elif not mc_query.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner(f"Processing whole dataset context & querying {PROVIDER_LABEL}..."):
                answer, total_records, est_tokens, elapsed_time = query_massive_context(
                    query=mc_query,
                    selected_sources=selected_sources,
                    provider=PROVIDER,
                    api_key=API_KEY,
                    model_name=MODEL_NAME,
                    enable_caching=caching_enabled,
                    session_token=SESSION_TOKEN
                )

            st.markdown("### 📊 Query Execution Metrics")
            mcol1, mcol2, mcol3, mcol4 = st.columns(4)
            mcol1.metric("Ingested Records", f"{total_records:,}")
            mcol2.metric("Estimated Tokens", f"{est_tokens:,}")
            mcol3.metric("Latency", f"{elapsed_time} s")
            mcol4.metric("Context Caching", "Active" if caching_enabled else "Disabled")

            st.markdown("### 💡 Comprehensive Whole-Dataset Synthesis")
            st.success(answer)


def safe_dataframe(df, **kwargs):
    try:
        st.dataframe(df, width="stretch", **kwargs)
    except Exception:
        st.dataframe(df, use_container_width=True, **kwargs)

# TAB 3: DATA EXPLORER & STATS
with tab3:
    st.subheader("Data Explorer & Source Breakdown")

    csv_file = os.path.join(os.path.dirname(__file__), "processed_data", "unified_feedback.csv")
    if os.path.exists(csv_file):
        df_all = pd.read_csv(csv_file)
        
        # Stats Cards
        scol1, scol2, scol3 = st.columns(3)
        scol1.metric("Total Feedback Records", f"{len(df_all):,}")
        scol2.metric("Active Sources Ingested", len(df_all["source_key"].unique()))
        scol3.metric("Unique Authors/Users", len(df_all["author"].unique()))

        st.markdown("#### Feedback Count per Source")
        source_counts = df_all["source_name"].value_counts().reset_index()
        source_counts.columns = ["Data Source", "Record Count"]
        safe_dataframe(source_counts)

        st.markdown("#### Ingested Feedback Data Viewer")
        filter_source = st.multiselect(
            "Filter Table by Source",
            options=df_all["source_name"].unique(),
            default=df_all["source_name"].unique()
        )
        filtered_df = df_all[df_all["source_name"].isin(filter_source)]
        safe_dataframe(filtered_df[["source_name", "platform", "author", "rating", "date", "text"]])
    else:
        st.warning("No processed dataset found. Click 'Run / Refresh Data Pre-processing' in the sidebar to generate.")
