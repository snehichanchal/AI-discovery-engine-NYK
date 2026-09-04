"""Gemini access via the google-genai SDK.

The API key is supplied by the server (see app.py) and never originates from
the browser. Errors are returned as user-facing strings rather than raised, so
the Streamlit UI can display them inline.
"""

import threading

_CLIENT_LOCK = threading.Lock()
_CLIENTS = {}


def get_client(api_key: str):
    """Returns a memoized genai.Client for this key."""
    client = _CLIENTS.get(api_key)
    if client is not None:
        return client
    with _CLIENT_LOCK:
        if api_key not in _CLIENTS:
            from google import genai

            _CLIENTS[api_key] = genai.Client(api_key=api_key)
        return _CLIENTS[api_key]


def query_llm(provider: str, api_key: str, model_name: str, prompt: str, system_prompt: str = "You are a helpful AI discovery engine assistant.") -> str:
    """Sends a prompt to Gemini and returns the response text.

    Used by the RAG engine, whose prompts are small and need no cache. The
    `provider` argument is retained so callers keep a stable signature, but only
    "gemini" is supported.
    """
    if not api_key:
        return "⚠️ Error: GEMINI_API_KEY is not configured on the server."

    provider = provider.lower().strip()
    if provider not in ("gemini", "google gemini"):
        return f"⚠️ Error: Unsupported provider '{provider}'. This app is configured for Gemini only."

    try:
        from google.genai import types

        client = get_client(api_key)
        response = client.models.generate_content(
            model=model_name or "gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return response.text

    except Exception as e:
        return f"❌ Gemini API Error: {e}"


def generate_with_cache(api_key: str, model: str, cache_name: str, contents):
    """Answers against cached content.

    `contents` may be a single question or a list of prior conversation turns
    followed by the new question. Only those travel on the wire; the dataset is
    already resident in the cache. Returns (text, usage_metadata) and raises on
    failure so the caller can fall back to an uncached prompt.
    """
    from google.genai import types

    client = get_client(api_key)
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(cached_content=cache_name),
    )
    return response.text, getattr(response, "usage_metadata", None)


def generate_uncached(api_key: str, model: str, system_prompt: str, prompt: str):
    """Fallback path: sends the full prompt with no cache.

    Returns (text, usage_metadata). Used when cache creation is unavailable, so
    a caching failure degrades cost rather than breaking the app.
    """
    from google.genai import types

    client = get_client(api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return response.text, getattr(response, "usage_metadata", None)
