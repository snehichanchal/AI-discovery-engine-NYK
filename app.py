import os
import sys

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


# Sidebar Configuration
st.sidebar.title("⚙️ Engine Configuration")

# 1. LLM Provider Selection & API Key Inputs
st.sidebar.subheader("1. LLM Provider Settings")

provider = st.sidebar.selectbox(
    "Select LLM Provider",
    options=["Google Gemini", "OpenAI ChatGPT", "Anthropic Claude", "DeepSeek"],
    index=0
)

# Model options per provider
model_map = {
    "Google Gemini": ["gemini-1.5-flash", "gemini-1.5-pro"],
    "OpenAI ChatGPT": ["gpt-4o-mini", "gpt-4o"],
    "Anthropic Claude": ["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307"],
    "DeepSeek": ["deepseek-chat", "deepseek-reasoner"]
}

selected_model = st.sidebar.selectbox("Select Model", options=model_map[provider])

api_key_env_var = {
    "Google Gemini": "GEMINI_API_KEY",
    "OpenAI ChatGPT": "OPENAI_API_KEY",
    "Anthropic Claude": "ANTHROPIC_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY"
}

def get_secret(key_name):
    if hasattr(st, "secrets") and key_name in st.secrets:
        return st.secrets[key_name]
    return os.environ.get(key_name, "")

default_api_key = get_secret(api_key_env_var[provider])
api_key = st.sidebar.text_input(
    f"Enter {provider} API Key",
    value=default_api_key,
    type="password",
    help=f"Enter your API key for {provider}. Keys are held securely in memory or pulled from Streamlit Secrets."
)

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
        if not api_key:
            st.error(f"Please enter your {provider} API Key in the sidebar.")
        elif not selected_sources:
            st.warning("Please select at least one data source from the sidebar checkboxes.")
        elif not user_query.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner(f"Retrieving top {top_k} matches from ChromaDB & querying {provider}..."):
                answer, citations = search_and_answer(
                    query=user_query,
                    selected_sources=selected_sources,
                    provider=provider,
                    api_key=api_key,
                    model_name=selected_model,
                    top_k=top_k
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
        if not api_key:
            st.error(f"Please enter your {provider} API Key in the sidebar.")
        elif not selected_sources:
            st.warning("Please select at least one data source from the sidebar checkboxes.")
        elif not mc_query.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner(f"Processing whole dataset context & querying {provider}..."):
                answer, total_records, est_tokens, elapsed_time = query_massive_context(
                    query=mc_query,
                    selected_sources=selected_sources,
                    provider=provider,
                    api_key=api_key,
                    model_name=selected_model,
                    enable_caching=caching_enabled
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
