import os
import pandas as pd
import time
from auth import AuthError, verify_session_token
from llm_provider import query_llm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_CSV = os.path.join(BASE_DIR, "processed_data", "unified_feedback.csv")


def query_massive_context(query: str, selected_sources: list, provider: str, api_key: str, model_name: str, enable_caching: bool = True, session_token: str = ""):
    """
    Requires a valid session token; refused without one.

    Approach 5: Massive Context Window (Direct Prompting)
    Passes the entire feedback dataset (filtered by selected sources) directly into the LLM context.
    Supports context caching optimization for Gemini & Claude.
    """
    try:
        verify_session_token(session_token)
    except AuthError as e:
        return f"🔒 {e}", 0, 0, 0

    if not query.strip():
        return "Please enter a question.", 0, 0, 0

    if not os.path.exists(PROCESSED_CSV):
        return "⚠️ Processed data CSV not found. Please run Data Pre-processing script first.", 0, 0, 0

    df = pd.read_csv(PROCESSED_CSV)

    if selected_sources:
        df = df[df["source_key"].isin(selected_sources)]

    if df.empty:
        return "No records available for the selected data sources.", 0, 0, 0

    total_records = len(df)

    # Convert dataset to text format for prompt context
    feedback_text_list = []
    for idx, row in df.iterrows():
        entry = (
            f"--- Record #{idx+1} ---\n"
            f"Source: {row.get('source_name', 'Unknown')} | Platform: {row.get('platform', 'N/A')} | Author: {row.get('author', 'Anonymous')}\n"
            f"Text: {row.get('text', '')}"
        )
        feedback_text_list.append(entry)

    full_context_text = "\n\n".join(feedback_text_list)
    estimated_words = len(full_context_text.split())
    estimated_tokens = int(estimated_words * 1.3)

    system_prompt = (
        "You are an expert AI Discovery Engine with full access to the complete user feedback dataset provided below. "
        "Analyze the entire dataset thoroughly to answer the user's question with high accuracy, identifying overarching themes, patterns, statistics, or specific feedback as requested."
    )

    user_prompt = f"COMPLETE USER FEEDBACK DATASET ({total_records} Records):\n\n{full_context_text}\n\n====================\nQuestion: {query}\n\nComprehensive Direct Answer:"

    start_time = time.time()

    # Query LLM provider
    answer = query_llm(
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        prompt=user_prompt,
        system_prompt=system_prompt
    )

    elapsed_time = round(time.time() - start_time, 2)

    return answer, total_records, estimated_tokens, elapsed_time
