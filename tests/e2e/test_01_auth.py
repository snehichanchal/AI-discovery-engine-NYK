"""The login gate and session handling."""

from conftest import do_login


def test_login_gate_blocks_unauthenticated_visitors(page):
    body = page.content()
    assert "Sign in" in body
    # The app must not leak its contents before authentication.
    assert "Data Explorer" not in body
    assert page.get_by_role("tab").count() == 0


def test_wrong_password_is_rejected(page):
    assert not do_login(page, password="definitely-not-the-password")
    assert "Invalid username or password" in page.content()


def test_wrong_username_is_rejected(page):
    assert not do_login(page, username="not-a-user")
    assert "Invalid username or password" in page.content()


def test_valid_credentials_sign_in(app):
    body = app.content()
    assert "Engine Configuration" in body
    assert app.get_by_role("tab").count() == 3


def test_sidebar_reports_session_expiry(app):
    assert "Session expires in" in app.content()


def test_sign_out_returns_to_the_login_gate(app):
    app.get_by_role("button", name="Sign out").click()
    app.wait_for_timeout(3000)
    assert app.locator('button:has-text("Sign in")').count() == 1
    assert app.get_by_role("tab").count() == 0
