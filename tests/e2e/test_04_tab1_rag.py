"""Tab 1 (RAG) renders and reflects the indexed data."""

import pytest

from conftest import open_tab


def test_tab1_rag_renders_controls(app):
    open_tab(app, 0)
    body = app.content()
    assert "RAG Discovery Engine" in body
    assert "Top-K Snippets to Retrieve" in body
    assert app.get_by_role("button", name="Ask RAG Engine").count() == 1


def test_tab1_rejects_an_empty_question(app):
    open_tab(app, 0)
    app.get_by_role("button", name="Ask RAG Engine").click()
    app.wait_for_timeout(2500)
    assert "Please enter a question" in app.content()


def test_no_console_errors_across_tabs(app):
    for i in (0, 1):
        open_tab(app, i)
    ignorable = ("favicon", "manifest")
    real = [e for e in app.console_errors if not any(w in e.lower() for w in ignorable)]
    assert not real, f"console errors: {real[:3]}"


@pytest.mark.llm
def test_rag_retrieves_hindi_interviews_from_an_english_question(app):
    """Regression guard for the multilingual embedder.

    With the previous English-centric model this returned zero interview
    snippets; see embeddings.py for the measurements.
    """
    from conftest import open_tab

    open_tab(app, 0)
    app.wait_for_timeout(800)
    app.keyboard.type("wishlist used as a bookmark rather than buying")
    app.get_by_role("button", name="Ask RAG Engine").click()
    app.wait_for_selector("text=Retrieved Context Snippets", timeout=120000)
    assert "User Interviews (Primary Research)" in app.content(), (
        "an English question did not retrieve any Hindi interview records"
    )
