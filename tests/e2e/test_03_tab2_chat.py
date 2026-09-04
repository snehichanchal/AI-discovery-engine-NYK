"""Tab 2: conversational UI, bottom-pinned input, browser-side history."""

from conftest import STORAGE_KEY, open_tab, read_history, seed_history

TAB = 1  # Massive Context Engine


def test_heading_has_no_approach_qualifier(app):
    open_tab(app, TAB)
    body = app.content()
    assert "Massive Context Engine" in body
    assert "Whole Dataset Prompting" not in body


def test_chat_input_present_and_pinned_with_empty_transcript(app):
    open_tab(app, TAB)
    assert app.locator('[data-testid="stChatInput"]').count() == 1
    gap = app.evaluate(
        "() => Math.round(window.innerHeight -"
        " document.querySelector('[data-testid=\"stChatInput\"]').getBoundingClientRect().bottom)"
    )
    assert gap < 60, f"chat input not pinned to the viewport bottom (gap {gap}px)"


def test_chat_input_stays_pinned_while_scrolling_a_long_transcript(app):
    seed_history(app, [{"question": f"Q{i}", "answer": "filler " * 150, "meta": {}} for i in range(10)])
    app.reload(wait_until="networkidle", timeout=60000)
    from conftest import do_login

    do_login(app)
    open_tab(app, TAB)

    def gap():
        return app.evaluate(
            "() => Math.round(window.innerHeight -"
            " document.querySelector('[data-testid=\"stChatInput\"]').getBoundingClientRect().bottom)"
        )

    assert gap() < 60
    app.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
    app.wait_for_timeout(600)
    assert gap() < 60, "input came unpinned mid-scroll"


def test_history_restores_after_page_reload(app):
    seed_history(app, [{"question": "SEEDED QUESTION", "answer": "SEEDED ANSWER", "meta": {}}])
    app.reload(wait_until="networkidle", timeout=60000)
    from conftest import do_login

    do_login(app)
    open_tab(app, TAB)
    body = app.content()
    assert "SEEDED QUESTION" in body
    assert "SEEDED ANSWER" in body
    assert "saved in your browser" in body


def test_reload_does_not_clobber_stored_history(app):
    seed_history(app, [{"question": "KEEP ME", "answer": "A", "meta": {}}])
    app.reload(wait_until="networkidle", timeout=60000)
    from conftest import do_login

    do_login(app)
    open_tab(app, TAB)
    assert read_history(app)[0]["question"] == "KEEP ME"


def test_clear_chat_empties_transcript_and_storage(app):
    seed_history(app, [{"question": "TO BE CLEARED", "answer": "A", "meta": {}}])
    app.reload(wait_until="networkidle", timeout=60000)
    from conftest import do_login

    do_login(app)
    open_tab(app, TAB)
    app.get_by_role("button", name="Clear chat").click()
    app.wait_for_timeout(3000)
    assert "TO BE CLEARED" not in app.content()
    assert read_history(app) == []


def test_history_is_private_to_the_browser_profile(browser, app):
    seed_history(app, [{"question": "PRIVATE TO PROFILE ONE", "answer": "A", "meta": {}}])
    other = browser.new_context()
    try:
        page2 = other.new_page()
        from conftest import BASE_URL, do_login

        page2.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        do_login(page2)
        open_tab(page2, TAB)
        assert "PRIVATE TO PROFILE ONE" not in page2.content()
    finally:
        other.close()


def test_storage_bridge_component_loads(app):
    open_tab(app, TAB)
    assert any("component" in f.url for f in app.frames), "localStorage bridge iframe missing"
