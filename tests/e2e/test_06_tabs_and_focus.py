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


def test_only_two_tabs_remain(app):
    titles = app.get_by_role("tab").all_inner_texts()
    assert len(titles) == 2
    assert not any("Data Explorer" in t for t in titles)
