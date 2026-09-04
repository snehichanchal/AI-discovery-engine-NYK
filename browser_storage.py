"""Persists small pieces of state in the browser's localStorage.

Streamlit keeps session state on the server and discards it when the page is
reloaded, so without this a refresh would lose the Tab 2 conversation *and*
sign the user out. This wraps a zero-height custom component
(components/browser_storage/) that mirrors values into localStorage and reads
them back on load.

Two stores are backed by it:

  * the Tab 2 conversation history
  * the signed session token, so a refresh does not force a re-login

Both are per-browser: they never reach the server's disk, other viewers, or
other devices, and they can legitimately come back empty (private window,
cleared site data, storage disabled). Every path here treats empty as normal.

The session token is HMAC-signed and expires (see auth.py), so a stolen copy is
useless after it lapses -- but it is readable by anything running in the page,
which is the accepted trade-off for surviving a refresh.
"""

import os

import streamlit as st
import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "browser_storage")

_component = components.declare_component("browser_storage", path=_COMPONENT_DIR)

CHAT_STORAGE_KEY = "nykaa_discovery_chat_history_v1"
TOKEN_STORAGE_KEY = "nykaa_discovery_session_v1"

# Keys in st.session_state
HISTORY_KEY = "mc_history"
LOADED_KEY = "mc_history_loaded"
TOKEN_LOADED_KEY = "session_token_loaded"


def _sync(storage_key, widget_key, action="load", value=None):
    """Runs one exchange with the browser for a single storage key.

    Returns the stored value the browser reported, or None if it has not
    reported yet this page load.
    """
    payload = _component(
        storage_key=storage_key,
        action=action,
        value=value,
        # A stable widget key keeps the component mounted, preserving its
        # "report once per page load" contract across reruns.
        key=widget_key,
        default=None,
    )
    if isinstance(payload, dict) and payload.get("loaded"):
        return payload.get("value")
    return None


# Each bridge may be rendered at most ONCE per script run -- Streamlit raises
# StreamlitDuplicateElementKey otherwise. So writes are queued in session state
# and performed by the single sync call, which also avoids the race where a
# write issued immediately before st.rerun() is discarded before the browser
# commits it.

PENDING_CHAT = "_bs_pending_chat"
PENDING_TOKEN = "_bs_pending_token"


def _pending_action(slot):
    queued = st.session_state.pop(slot, None)
    if queued is None:
        return "load", None
    action, value = queued
    return action, value


# --- Tab 2 conversation history ------------------------------------------


def queue_save(history):
    st.session_state[PENDING_CHAT] = ("save", history)


def queue_clear():
    st.session_state[PENDING_CHAT] = ("clear", None)


def sync_chat():
    """The one chat-bridge render for this run. Call exactly once, in Tab 2."""
    action, value = _pending_action(PENDING_CHAT)
    stored = _sync(CHAT_STORAGE_KEY, "browser_storage_bridge", action, value)

    if action == "load" and stored is not None and not st.session_state.get(LOADED_KEY):
        if not st.session_state.get(HISTORY_KEY):
            st.session_state[HISTORY_KEY] = stored if isinstance(stored, list) else []
        st.session_state[LOADED_KEY] = True


# --- Session token --------------------------------------------------------


def queue_token_save(token):
    st.session_state[PENDING_TOKEN] = ("save", token)


def queue_token_clear():
    st.session_state[PENDING_TOKEN] = ("clear", None)


def sync_session_token():
    """The one token-bridge render for this run. Call exactly once, at the top.

    Returns the stored token, "" if there is none, or None while the browser
    has not reported yet this page load -- the caller should show the login
    form meanwhile rather than block, since it may never report (scripts
    disabled, storage blocked).
    """
    action, value = _pending_action(PENDING_TOKEN)
    stored = _sync(TOKEN_STORAGE_KEY, "session_token_bridge", action, value)
    if action != "load":
        return ""
    if stored is None:
        return None
    return stored if isinstance(stored, str) else ""
