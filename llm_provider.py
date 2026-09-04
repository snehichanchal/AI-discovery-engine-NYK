def query_llm(provider: str, api_key: str, model_name: str, prompt: str, system_prompt: str = "You are a helpful AI discovery engine assistant.") -> str:
    """
    Sends a prompt to Google Gemini and returns the response text.

    The `provider` argument is retained so callers keep a stable signature, but
    only "gemini" is supported. The API key is supplied by the server (see
    app.py) and never originates from the browser.

    Errors are returned as user-facing strings rather than raised, so the
    Streamlit UI can display them inline.
    """
    if not api_key:
        return "⚠️ Error: GEMINI_API_KEY is not configured on the server."

    provider = provider.lower().strip()
    if provider not in ("gemini", "google gemini"):
        return f"⚠️ Error: Unsupported provider '{provider}'. This app is configured for Gemini only."

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name or "gemini-flash-latest",
            system_instruction=system_prompt
        )
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"❌ Gemini API Error: {e}"
