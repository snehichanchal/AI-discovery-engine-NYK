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
import streamlit.components.v1 as components

import browser_storage
from auth import (AuthError, SESSION_TTL_SECONDS, credentials_configured,
                  issue_session_token, verify_session_token)
import gemini_cache
from preprocess import process_and_save, DATA_SOURCES
import rag_engine
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
    /* Pin Tab 2's chat box to the bottom. `sticky` rather than `fixed` so it
       inherits the content column's width and respects the sidebar, with no
       offset math to keep in sync. :has() scopes both rules to the tab that
       actually contains a chat input, leaving the other tabs untouched.
       Note the flex item is the element *container*, not the chat input two
       levels below it -- margin-top:auto on the input itself does nothing. */
    [role="tabpanel"]:has([data-testid="stChatInput"]) > [data-testid="stVerticalBlock"] {
        display: flex;
        flex-direction: column;
        min-height: calc(100vh - 245px);
    }
    [data-testid="stElementContainer"]:has(> [data-testid="stChatInput"]) {
        /* auto margin pushes it down when the transcript is short; sticky holds
           it in view once the transcript is long enough to scroll. */
        margin-top: auto;
        position: sticky;
        bottom: 0;
        z-index: 99;
    }
    /* Opaque strip so transcript text scrolls underneath, not through. */
    [data-testid="stElementContainer"]:has(> [data-testid="stChatInput"])::before {
        content: "";
        position: absolute;
        left: -1rem; right: -1rem; top: -0.75rem; bottom: -1rem;
        background: var(--background-color, #FFFFFF);
        z-index: -1;
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
MODEL_NAME = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-flash-latest"


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
        browser_storage.queue_token_clear()
        return ""


def restore_session_from_browser():
    """Adopts a still-valid token saved in this browser.

    st.session_state is per page load, so without this every refresh lands on
    the login form. The token is signed and expiring, so a stale or tampered
    copy is rejected here rather than trusted.

    Performs this run's single token-bridge render, so it must be called
    exactly once and before anything else touches that bridge.
    """
    stored = browser_storage.sync_session_token()

    if st.session_state.get("session_token"):
        return
    if stored is None or not stored:
        # Not reported yet, or nothing stored: fall through to the login form
        # rather than blocking, in case the browser never reports.
        return

    try:
        claims = verify_session_token(stored)
    except AuthError:
        browser_storage.queue_token_clear()
        return
    st.session_state["session_token"] = stored
    st.session_state["username"] = claims.get("sub", "")
    st.rerun()


def require_login():
    """Renders the sign-in form until the visitor holds a valid session token.

    Streamlit re-runs this script top to bottom on every interaction, so the
    token lives in st.session_state and is re-verified on each run. Nothing
    below this call executes for an unauthenticated session.
    """
    restore_session_from_browser()

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
                token = issue_session_token(username.strip())
                st.session_state.clear()
                st.session_state["session_token"] = token
                st.session_state["username"] = username.strip()
                # Persisted on the next run; see browser_storage's
                # single-render contract.
                browser_storage.queue_token_save(token)
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
    browser_storage.queue_token_clear()
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
        gemini_cache.invalidate()
        rag_engine.reset_collection()
        load_feedback_table.clear()
        st.sidebar.success("✅ Pre-processing & indexing complete!")


# Main Application Interface
st.markdown('<div class="main-header">🔍 User Feedback Discovery Engine</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Ingest user feedback across 8 public domain sources & ask natural language questions using AI.</div>', unsafe_allow_html=True)

# Tabs
tab1, tab2, tab3 = st.tabs([
    "🎯 Tab 1: RAG Discovery Engine",
    "⚡ Tab 2: Massive Context Engine",
    "📊 Tab 3: Data Explorer & Stats"
])


# Focus the active tab's text box so typing works without clicking first.
# Runs in a zero-height iframe; Streamlit re-renders the panel on every tab
# switch, so this listens for tab clicks rather than firing once on load.
_autofocus_component = components.declare_component(
    "tab_autofocus",
    path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "autofocus"),
)
# Focus the active tab's text box so typing works without clicking first.
_autofocus_component(key="tab_autofocus")


# TAB 1: RAG DISCOVERY ENGINE
with tab1:
    st.subheader("RAG Discovery Engine")
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


# TAB 2: MASSIVE CONTEXT ENGINE
with tab2:
    st.subheader("Massive Context Engine")
    st.caption(
        "The full dataset lives in a shared Gemini context cache, uploaded once and "
        "reused by every query. Only your question travels on the wire. Ask follow-up "
        "questions -- the conversation is kept in your browser."
    )

    # Restore the conversation from localStorage. Server-side session state is
    # discarded on page reload, so without this a refresh would lose the thread.
    browser_storage.sync_chat()
    history = st.session_state.setdefault(browser_storage.HISTORY_KEY, [])

    hcol1, hcol2 = st.columns([4, 1])
    with hcol1:
        if history:
            st.caption(f"{len(history)} message(s) in this conversation, saved in your browser.")
    with hcol2:
        if history and st.button("🗑️ Clear chat", key="btn_clear_chat"):
            st.session_state[browser_storage.HISTORY_KEY] = []
            browser_storage.queue_clear()
            st.rerun()

    # Transcript
    for entry in history:
        with st.chat_message("user"):
            st.markdown(entry.get("question", ""))
        with st.chat_message("assistant"):
            st.markdown(entry.get("answer", ""))
            meta = entry.get("meta") or {}
            if meta:
                bits = []
                if meta.get("cached_tokens"):
                    bits.append(f"{meta['cached_tokens']:,} cached tokens")
                if meta.get("fresh_tokens"):
                    bits.append(f"{meta['fresh_tokens']:,} fresh")
                if meta.get("elapsed"):
                    bits.append(f"{meta['elapsed']}s")
                if bits:
                    st.caption(" · ".join(bits))

    mc_query = st.chat_input(
        "Ask a question about the feedback dataset...",
        key="mc_chat_input",
    )

    if mc_query:
        if not selected_sources:
            st.warning("Please select at least one data source from the sidebar checkboxes.")
        else:
            with st.chat_message("user"):
                st.markdown(mc_query)

            spinner_text = (
                "Building the shared dataset cache (one-time), then querying "
                f"{PROVIDER_LABEL}..."
                if not gemini_cache.cache_status()["cache_name"]
                else f"Querying {PROVIDER_LABEL} against the cached dataset..."
            )
            with st.chat_message("assistant"):
                with st.spinner(spinner_text):
                    mc_result = query_massive_context(
                        query=mc_query,
                        selected_sources=selected_sources,
                        provider=PROVIDER,
                        api_key=API_KEY,
                        model_name=MODEL_NAME,
                        session_token=SESSION_TOKEN,
                        all_sources=list(DATA_SOURCES.keys()),
                        history=history,
                    )

                st.markdown(mc_result.answer)

                fresh_tokens = max(0, mc_result.prompt_tokens - mc_result.cached_tokens)
                bits = []
                if mc_result.cached_tokens:
                    bits.append(f"{mc_result.cached_tokens:,} cached tokens")
                if fresh_tokens:
                    bits.append(f"{fresh_tokens:,} fresh")
                bits.append(f"{mc_result.elapsed_seconds}s")
                if mc_result.total_records:
                    bits.append(f"{mc_result.total_records:,} records")
                st.caption(" · ".join(bits))

                if mc_result.cache_created:
                    st.info("Shared cache built by this query. Every later query reuses it.")
                if mc_result.cache_error:
                    st.warning(
                        "Context caching unavailable, so the full dataset was sent uncached "
                        f"(this query cost more than it needed to). Reason: {mc_result.cache_error}"
                    )
                if mc_result.sources_note:
                    st.caption(mc_result.sources_note)

            history.append({
                "question": mc_query,
                "answer": mc_result.answer,
                "meta": {
                    "cached_tokens": mc_result.cached_tokens,
                    "fresh_tokens": fresh_tokens,
                    "elapsed": mc_result.elapsed_seconds,
                },
            })
            st.session_state[browser_storage.HISTORY_KEY] = history
            browser_storage.queue_save(history)
            st.rerun()


@st.cache_data(show_spinner=False)
def load_feedback_table(csv_path, mtime):
    """Tab 3's table. Keyed on mtime so a re-index invalidates it.

    Streamlit re-runs the whole script on every interaction, so without this the
    full CSV was parsed again on each one.
    """
    return pd.read_csv(csv_path)


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
        df_all = load_feedback_table(csv_file, os.path.getmtime(csv_file))
        
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
