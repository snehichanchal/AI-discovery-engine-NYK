"""Server-side configuration surfaced in the sidebar."""

import re


def test_provider_and_model_are_fixed_server_side(app):
    body = app.content()
    assert "Google Gemini" in body
    assert "gemini-flash-latest" in body or re.search(r"gemini[\w.\-]*", body)


def test_no_api_key_input_is_exposed(app):
    """The key must never be bound to a widget -- see auth notes in CLAUDE.md."""
    body = app.content()
    assert "Enter Google Gemini API Key" not in body
    assert "API key loaded from the server environment" in body
    # Only the sign-out control and data-source checkboxes should remain; no
    # password-typed field is present once signed in.
    assert app.locator('input[type="password"]').count() == 0


def test_all_sources_listed_and_checked(app):
    checkboxes = app.locator('[data-testid="stSidebar"] input[type="checkbox"]')
    assert checkboxes.count() == 9
    for i in range(9):
        assert checkboxes.nth(i).is_checked()


def test_primary_research_is_listed_first(app):
    labels = [t.strip() for t in app.locator('[data-testid="stSidebar"] label').all_inner_texts() if t.strip()]
    assert labels[0] == "User Interviews (Primary Research)"
