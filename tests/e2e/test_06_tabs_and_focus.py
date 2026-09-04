"""Tab titles and typing straight into the active tab's text box."""

from conftest import open_tab


def active_element(page):
    return page.evaluate(
        "() => { const a = document.activeElement;"
        " return a ? a.tagName : 'NONE'; }"
    )


def test_tab_titles_have_no_approach_qualifiers(app):
    titles = app.get_by_role("tab").all_inner_texts()
    joined = " ".join(titles)
    assert "Approaches 1 & 3" not in joined
    assert "5th Approach" not in joined
    assert "RAG Discovery Engine" in joined
    assert "Massive Context Engine" in joined


def test_tab1_question_box_is_focused_on_select(app):
    open_tab(app, 0)
    app.wait_for_timeout(800)
    assert active_element(app) == "INPUT"


def test_tab1_accepts_typing_without_clicking(app):
    open_tab(app, 0)
    app.wait_for_timeout(800)
    app.keyboard.type("refund complaints")
    assert app.evaluate("() => document.activeElement.value") == "refund complaints"


def test_tab2_chat_box_is_focused_on_select(app):
    open_tab(app, 1)
    app.wait_for_timeout(800)
    assert active_element(app) == "TEXTAREA"


def test_tab2_accepts_typing_without_clicking(app):
    open_tab(app, 1)
    app.wait_for_timeout(800)
    app.keyboard.type("hello there")
    assert app.evaluate("() => document.activeElement.value") == "hello there"


def test_tab3_does_not_hijack_focus(app):
    """Tab 3 has no free-text box; focusing its multiselect would pop a dropdown."""
    open_tab(app, 2)
    app.wait_for_timeout(800)
    assert active_element(app) not in ("INPUT", "TEXTAREA")
