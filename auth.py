"""Session authentication for the User Feedback Discovery Engine.

Credentials come from the server environment; nothing is hardcoded here.
Successful login mints a signed, expiring session token. Every query engine
verifies that token before doing any work, so calling the engines directly --
bypassing the Streamlit UI -- gets you nothing without a valid token.

Required environment variables:
    APP_USERNAME       login username
    APP_PASSWORD       login password
    APP_SECRET_KEY     key used to sign session tokens

Streamlit Community Cloud injects entries from App settings -> Secrets into the
environment, so the same names work there.
"""

import base64
import hmac
import json
import os
import secrets
import time
from hashlib import sha256

# A session stays valid for 72 hours, after which the user must sign in again.
SESSION_TTL_SECONDS = 72 * 60 * 60


class AuthError(Exception):
    """Raised when credentials or a session token are invalid or expired."""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def get_signing_key() -> bytes:
    """Returns the token signing key.

    Falls back to a per-process random key when APP_SECRET_KEY is unset, which
    keeps the app working but invalidates every session on restart.
    """
    configured = _env("APP_SECRET_KEY")
    if configured:
        return configured.encode("utf-8")
    global _EPHEMERAL_KEY
    if _EPHEMERAL_KEY is None:
        _EPHEMERAL_KEY = secrets.token_bytes(32)
    return _EPHEMERAL_KEY


_EPHEMERAL_KEY = None


def credentials_configured() -> bool:
    return bool(_env("APP_USERNAME") and _env("APP_PASSWORD"))


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time credential check against the configured environment."""
    expected_user = _env("APP_USERNAME")
    expected_pass = _env("APP_PASSWORD")
    if not expected_user or not expected_pass:
        return False
    # Evaluate both comparisons so timing does not reveal which field failed.
    user_ok = hmac.compare_digest((username or "").strip(), expected_user)
    pass_ok = hmac.compare_digest(password or "", expected_pass)
    return user_ok and pass_ok


def _sign(payload: bytes) -> str:
    return hmac.new(get_signing_key(), payload, sha256).hexdigest()


def issue_session_token(username: str) -> str:
    """Mints a signed token that expires SESSION_TTL_SECONDS from now."""
    now = int(time.time())
    payload = json.dumps(
        {"sub": username, "iat": now, "exp": now + SESSION_TTL_SECONDS, "jti": secrets.token_hex(8)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{body}.{_sign(payload)}"


def verify_session_token(token: str) -> dict:
    """Validates signature and expiry, returning the token claims.

    Raises AuthError for anything malformed, tampered with, or expired.
    """
    if not token or not isinstance(token, str) or token.count(".") != 1:
        raise AuthError("No active session. Please sign in.")

    body, signature = token.split(".")
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        claims = json.loads(payload)
    except Exception:
        raise AuthError("Invalid session token. Please sign in again.")

    if not hmac.compare_digest(signature, _sign(payload)):
        raise AuthError("Invalid session token. Please sign in again.")

    if int(claims.get("exp", 0)) <= int(time.time()):
        raise AuthError("Your 72-hour session has expired. Please sign in again.")

    return claims


def session_expires_at(token: str) -> int:
    return int(verify_session_token(token).get("exp", 0))
