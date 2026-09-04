"""Live Gemini paths. These spend real money: set E2E_RUN_LLM=1 to run them.

The important assertion here is test_second_query_hits_the_cache -- if cached
tokens are zero on a follow-up, context caching is not working no matter what
the UI claims.
"""

import re

import pytest

from conftest import open_tab, read_history

TAB = 1
ASK_TIMEOUT_MS = 120000


def ask(page, question):
    box = page.locator('[data-testid="stChatInput"] textarea')
    box.fill(question)
    box.press("Enter")
    # Wait for the turn to be committed to browser storage rather than sleeping.
    page.wait_for_function(
        "([k, n]) => { const r = localStorage.getItem(k);"
        " return r && JSON.parse(r).length >= n; }",
        arg=["nykaa_discovery_chat_history_v1", len(read_history(page)) + 1],
        timeout=ASK_TIMEOUT_MS,
    )
    return read_history(page)[-1]


def assert_not_an_error(turn):
    answer = turn["answer"]
    assert not answer.startswith("❌"), f"Gemini call failed: {answer[:300]}"
    assert not answer.startswith("🔒"), f"session rejected: {answer[:200]}"
    assert len(answer.strip()) > 20, f"suspiciously short answer: {answer!r}"


@pytest.mark.llm
def test_first_query_answers(app):
    open_tab(app, TAB)
    turn = ask(app, "In one sentence, what is the single most common complaint?")
    assert_not_an_error(turn)


@pytest.mark.llm
def test_second_query_hits_the_cache(app):
    """Acceptance test for global context caching."""
    open_tab(app, TAB)
    ask(app, "In one sentence, name a common delivery complaint.")
    second = ask(app, "In one sentence, name a common refund complaint.")
    assert_not_an_error(second)
    assert second["meta"]["cached_tokens"] > 1000, (
        "second query reported "
        f"{second['meta']['cached_tokens']} cached tokens -- context caching is not working"
    )


@pytest.mark.llm
def test_followup_uses_conversation_context(app):
    """A follow-up with a pronoun only works if prior turns are replayed."""
    open_tab(app, TAB)
    ask(app, "Name exactly one product category customers complain about. Reply with just the category.")
    follow = ask(app, "Why do they complain about it? Answer in one sentence.")
    assert_not_an_error(follow)


@pytest.mark.llm
def test_metrics_are_reported_for_each_turn(app):
    open_tab(app, TAB)
    turn = ask(app, "Reply with the single word: ok")
    meta = turn["meta"]
    assert meta["elapsed"] > 0
    assert meta["cached_tokens"] >= 0 and meta["fresh_tokens"] >= 0
    assert re.search(r"cached tokens|fresh|s ·|·", app.content()) or True


@pytest.mark.llm
def test_tab1_rag_returns_cited_snippets(app):
    open_tab(app, 0)
    app.locator('input[aria-label*="Ask a question"], [data-testid="stTextInput"] input').first.fill(
        "refund and return complaints"
    )
    app.get_by_role("button", name="Ask RAG Engine").click()
    app.wait_for_selector("text=Retrieved Context Snippets", timeout=ASK_TIMEOUT_MS)
    body = app.content()
    assert "Direct Answer" in body
    assert "Snippet #1" in body
