"""Massive Context Engine: answers questions against the whole dataset.

The dataset lives in a single global Gemini context cache (see gemini_cache.py),
so a query sends only the question rather than ~99k tokens of feedback. If the
cache is unavailable for any reason, the engine falls back to sending the full
prompt uncached -- a caching failure costs money, never availability.
"""

import os
import time
from dataclasses import dataclass, field

import gemini_cache
from auth import AuthError, verify_session_token
from llm_provider import generate_uncached, generate_with_cache

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_CSV = gemini_cache.PROCESSED_CSV


@dataclass
class MassiveContextResult:
    """Outcome of one whole-dataset query."""

    answer: str = ""
    total_records: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    elapsed_seconds: float = 0.0
    cache_created: bool = False
    cache_error: str = ""
    sources_note: str = ""


def _source_instruction(selected_sources, all_sources) -> str:
    """Instruction restricting the answer to a subset of sources.

    The cache holds every record, so narrowing is expressed to the model rather
    than by filtering the content -- filtering would change the cached prefix
    and require a separate cache per combination.
    """
    if not selected_sources or not all_sources:
        return ""
    if set(selected_sources) >= set(all_sources):
        return ""
    names = ", ".join(sorted(selected_sources))
    return (
        "IMPORTANT: Consider ONLY records whose source_key is one of: "
        f"{names}. Ignore every record from any other source, and say so if "
        "that leaves nothing relevant.\n\n"
    )


# Prior turns replayed for follow-up questions. Capped because every turn is
# fresh (uncached) input on each request, unlike the dataset itself.
MAX_HISTORY_TURNS = 6


def _build_contents(history, question):
    """Renders prior turns plus the new question for the Gemini contents list."""
    from google.genai import types

    turns = []
    for entry in (history or [])[-MAX_HISTORY_TURNS:]:
        q = (entry.get("question") or "").strip()
        a = (entry.get("answer") or "").strip()
        if not q or not a:
            continue
        turns.append(types.Content(role="user", parts=[types.Part(text=q)]))
        turns.append(types.Content(role="model", parts=[types.Part(text=a)]))
    turns.append(types.Content(role="user", parts=[types.Part(text=question)]))
    return turns


def query_massive_context(query: str, selected_sources: list, provider: str, api_key: str,
                          model_name: str, session_token: str = "",
                          all_sources: list = None, history: list = None) -> MassiveContextResult:
    """Requires a valid session token; refused without one."""
    try:
        verify_session_token(session_token)
    except AuthError as e:
        return MassiveContextResult(answer=f"🔒 {e}")

    if not query.strip():
        return MassiveContextResult(answer="Please enter a question.")

    if not api_key:
        return MassiveContextResult(answer="⚠️ Error: GEMINI_API_KEY is not configured on the server.")

    if not os.path.exists(PROCESSED_CSV):
        return MassiveContextResult(
            answer="⚠️ Processed data CSV not found. Please run Data Pre-processing script first."
        )

    result = MassiveContextResult()
    instruction = _source_instruction(selected_sources, all_sources)
    if instruction:
        result.sources_note = "Narrowed to selected sources by instruction."
    question = f"{instruction}Question: {query}\n\nComprehensive Direct Answer:"

    start_time = time.time()
    try:
        from llm_provider import get_client

        cache = gemini_cache.get_or_create_cache(get_client(api_key), model_name)
        result.cache_created = cache.was_created
        result.total_records = cache.record_count
        text, usage = generate_with_cache(
            api_key, model_name, cache.name, _build_contents(history, question)
        )
    except Exception as cache_exc:
        # Caching unavailable (model not cacheable, quota, API error): fall back
        # to the full uncached prompt so the app keeps working.
        result.cache_error = str(cache_exc)
        try:
            dataset_text, record_count = gemini_cache.build_dataset_text()
            result.total_records = record_count
            transcript = ""
            for entry in (history or [])[-MAX_HISTORY_TURNS:]:
                if entry.get("question") and entry.get("answer"):
                    transcript += f"Previous question: {entry['question']}\nPrevious answer: {entry['answer']}\n\n"
            prompt = (
                f"COMPLETE USER FEEDBACK DATASET ({record_count} Records):\n\n"
                f"{dataset_text}\n\n====================\n{transcript}{question}"
            )
            text, usage = generate_uncached(
                api_key, model_name, gemini_cache.SYSTEM_INSTRUCTION, prompt
            )
        except Exception as e:
            result.answer = f"❌ Gemini API Error: {e}"
            result.elapsed_seconds = round(time.time() - start_time, 2)
            return result

    result.elapsed_seconds = round(time.time() - start_time, 2)
    result.answer = text or ""

    if usage is not None:
        result.prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        result.cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0

    return result
