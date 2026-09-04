"""Shared fixtures for the end-to-end suite.

Tests drive a real Chromium instance against a running app. Nothing is stubbed:
the app talks to its real ChromaDB index and, for the tests marked `llm`, the
real Gemini API.

Configuration comes from the environment so no credential is ever committed:

    E2E_BASE_URL   default http://localhost:8501
    E2E_USERNAME   falls back to APP_USERNAME
    E2E_PASSWORD   falls back to APP_PASSWORD
    E2E_RUN_LLM    set to 1 to include tests that call Gemini and cost money
"""

import os

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8501").rstrip("/")
USERNAME = os.environ.get("E2E_USERNAME") or os.environ.get("APP_USERNAME", "")
PASSWORD = os.environ.get("E2E_PASSWORD") or os.environ.get("APP_PASSWORD", "")

STORAGE_KEY = "nykaa_discovery_chat_history_v1"

# Streamlit re-runs its script on every interaction; these are generous enough
# to cover a rerun without making a failing test slow to report.
SETTLE_MS = 2500
LOGIN_MS = 4000


def pytest_configure(config):
    config.addinivalue_line("markers", "llm: calls the Gemini API and spends real money")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("E2E_RUN_LLM") == "1":
        return
    skip = pytest.mark.skip(reason="needs E2E_RUN_LLM=1 (these tests spend real money)")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    browser = playwright_instance.chromium.launch()
    yield browser
    browser.close()


@pytest.fixture
def page(browser):
    """A fresh browser context per test, so localStorage never leaks between tests."""
    context = browser.new_context()
    page = context.new_page()
    page.console_errors = []
    page.on(
        "console",
        lambda m: page.console_errors.append(m.text) if m.type == "error" else None,
    )
    page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
    yield page
    context.close()


def do_login(page, username=None, password=None):
    """Signs in. Returns True if the app moved past the login gate."""
    if not page.locator('button:has-text("Sign in")').count():
        return True
    inputs = page.locator("input")
    inputs.nth(0).fill(username if username is not None else USERNAME)
    inputs.nth(1).fill(password if password is not None else PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_timeout(LOGIN_MS)
    return page.locator('button:has-text("Sign in")').count() == 0


@pytest.fixture
def app(page):
    """A page that is already signed in."""
    assert do_login(page), "could not sign in -- check E2E_USERNAME / E2E_PASSWORD"
    return page


def open_tab(page, index):
    """Opens a tab by position (0=RAG, 1=Massive Context, 2=Data Explorer)."""
    page.get_by_role("tab").nth(index).click()
    page.wait_for_timeout(SETTLE_MS)


def read_history(page):
    import json

    raw = page.evaluate("k => localStorage.getItem(k)", STORAGE_KEY)
    return json.loads(raw) if raw else []


def seed_history(page, history):
    page.evaluate(
        "([k, v]) => localStorage.setItem(k, JSON.stringify(v))", [STORAGE_KEY, history]
    )
