"""Persists Tab 2 conversation history in the browser's localStorage.

Streamlit keeps session state on the server and discards it when the page is
reloaded, so a refresh would otherwise wipe the conversation. This wraps a
zero-height custom component (components/browser_storage/) that mirrors the
history into localStorage and reads it back on load.

History is per-browser: it never reaches the server's disk, other viewers, or
other devices, and it can legitimately come back empty (private window, cleared
site data, storage disabled). Every path here treats empty as normal.
"""

import os

import streamlit as st
import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "browser_storage")

_component = components.declare_component("browser_storage", path=_COMPONENT_DIR)

# Keys in st.session_state
HISTORY_KEY = "mc_history"
LOADED_KEY = "mc_history_loaded"


def sync(action: str = "load", history=None):
    """Runs one exchange with the browser.

    action="load"  -> read localStorage (used once per page load)
    action="save"  -> write `history` to localStorage
    action="clear" -> remove the stored history

    Returns the stored history the browser reported, or None if it has not
    reported yet this page load.
    """
    payload = _component(
        action=action,
        history=history or [],
        # A changing key would remount the component and re-report on every
        # rerun; a stable one keeps the "report once per page load" contract.
        key="browser_storage_bridge",
        default=None,
    )
    if isinstance(payload, dict) and payload.get("loaded"):
        stored = payload.get("history")
        return stored if isinstance(stored, list) else []
    return None


def load_once():
    """Restores history from the browser the first time it reports.

    Safe to call on every rerun; it only writes to session state once.
    """
    if st.session_state.get(LOADED_KEY):
        return

    stored = sync("load")
    if stored is not None:
        # Only adopt the browser copy if this session has nothing yet, so a
        # conversation started before the browser reported is never clobbered.
        if not st.session_state.get(HISTORY_KEY):
            st.session_state[HISTORY_KEY] = stored
        st.session_state[LOADED_KEY] = True


def save(history):
    sync("save", history)


def clear():
    """Removes the stored history.

    Prefer save([]) from a normal render; a clear issued immediately before
    st.rerun() can be discarded before the browser commits it.
    """
    sync("clear")
