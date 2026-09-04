"""Single global Gemini context cache for the feedback dataset.

The whole dataset (~211k tokens) is uploaded to Gemini exactly once and reused by
every query from every user. Cached input tokens bill at a fraction of fresh
input tokens, and since the dataset is identical for everyone, one cache serves
the entire app.

Lifecycle:
  * The cache is created lazily -- the first query that finds no live cache
    builds it, then runs.
  * It is keyed to a fingerprint of the CSV contents, so re-indexing the data
    produces a new cache while an unchanged re-run reuses the existing one.
  * Gemini caches always expire server-side, so an expired or deleted cache is
    rebuilt transparently rather than surfaced as an error.

Deliberately free of Streamlit imports so it can be exercised from a script.
"""

import hashlib
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_CSV = os.path.join(BASE_DIR, "processed_data", "unified_feedback.csv")

# Bumped when the rendered dataset text format changes, so old caches are not
# reused for a prompt shape they were not built for.
CACHE_PREFIX = "nykaa-feedback-v1"

# Caches must carry a TTL; Gemini offers no permanent cache. This is long enough
# that time-based rebuilds are invisible in practice -- refreshes are driven by
# the dataset fingerprint instead.
DEFAULT_TTL_SECONDS = 24 * 60 * 60

SYSTEM_INSTRUCTION = (
    "You are an expert AI Discovery Engine with full access to the complete user "
    "feedback dataset provided in your cached context. Analyze the entire dataset "
    "thoroughly to answer the user's question with high accuracy, identifying "
    "overarching themes, patterns, statistics, or specific feedback as requested."
)

_LOCK = threading.Lock()
_MEMO = {"cache_name": None, "fingerprint": None, "record_count": 0}


class CacheInfo:
    """Describes the cache backing a query."""

    def __init__(self, name, fingerprint, record_count, was_created=False):
        self.name = name
        self.fingerprint = fingerprint
        self.record_count = record_count
        self.was_created = was_created


def ttl_seconds() -> int:
    raw = os.environ.get("GEMINI_CACHE_TTL_SECONDS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_TTL_SECONDS


def dataset_fingerprint() -> str:
    """SHA-256 over the CSV contents, truncated.

    Keyed on content rather than mtime so that re-running preprocessing without
    changing the data reuses the existing cache instead of paying to rebuild it.
    """
    digest = hashlib.sha256()
    with open(PROCESSED_CSV, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _read_rows():
    """Streams the CSV with the stdlib reader.

    pandas would materialize a DataFrame of the whole dataset purely to
    concatenate strings; this keeps the cache-build path lean.
    """
    import csv

    csv.field_size_limit(10 ** 7)
    with open(PROCESSED_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield row


def record_count() -> int:
    return sum(1 for _ in _read_rows())


def build_dataset_text():
    """Renders every record as a text block. Returns (text, record_count)."""
    blocks = []
    for position, row in enumerate(_read_rows(), start=1):
        blocks.append(
            f"--- Record #{position} ---\n"
            f"Source: {row.get('source_name') or 'Unknown'} | "
            f"Platform: {row.get('platform') or 'N/A'} | "
            f"Author: {row.get('author') or 'Anonymous'}\n"
            f"Text: {row.get('text') or ''}"
        )
    return "\n\n".join(blocks), len(blocks)


def _display_name(fingerprint: str) -> str:
    return f"{CACHE_PREFIX}-{fingerprint}"


def _find_existing(client, fingerprint):
    """Looks for a live cache for this fingerprint.

    Discovery by display_name is what lets a restarted container reuse a cache
    that is still alive on Gemini's side -- important because Streamlit Cloud's
    filesystem is ephemeral, so a local state file would not survive.
    """
    wanted = _display_name(fingerprint)
    try:
        for cache in client.caches.list():
            if getattr(cache, "display_name", None) == wanted:
                return cache.name
    except Exception:
        # Listing is an optimization; failing it just means we create a cache.
        return None
    return None


def invalidate():
    """Drops the in-process memo, forcing a re-check on the next query."""
    with _LOCK:
        _MEMO["cache_name"] = None
        _MEMO["fingerprint"] = None
        _MEMO["record_count"] = 0


def get_or_create_cache(client, model: str) -> CacheInfo:
    """Returns the global cache, creating it if necessary.

    Raises on failure so the caller can fall back to an uncached prompt.
    """
    fingerprint = dataset_fingerprint()

    # Fast path: memo already holds a cache for this exact dataset.
    memo_name = _MEMO["cache_name"]
    if memo_name and _MEMO["fingerprint"] == fingerprint:
        return CacheInfo(memo_name, fingerprint, _MEMO["record_count"])

    # Streamlit serves each session on its own thread inside one process, so
    # without this lock two simultaneous first-queries would each create (and
    # bill for) a separate cache.
    with _LOCK:
        if _MEMO["cache_name"] and _MEMO["fingerprint"] == fingerprint:
            return CacheInfo(_MEMO["cache_name"], fingerprint, _MEMO["record_count"])

        from google.genai import types

        count = _MEMO["record_count"]
        existing = _find_existing(client, fingerprint)
        if existing:
            if not count:
                count = record_count()
            _MEMO.update(
                {"cache_name": existing, "fingerprint": fingerprint, "record_count": count}
            )
            return CacheInfo(existing, fingerprint, count)

        dataset_text, count = build_dataset_text()
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                display_name=_display_name(fingerprint),
                system_instruction=SYSTEM_INSTRUCTION,
                contents=[dataset_text],
                ttl=f"{ttl_seconds()}s",
            ),
        )
        _MEMO.update(
            {"cache_name": cache.name, "fingerprint": fingerprint, "record_count": count}
        )
        return CacheInfo(cache.name, fingerprint, count, was_created=True)


def cache_status() -> dict:
    """Best-effort view of the in-process memo, for display."""
    return {
        "cache_name": _MEMO["cache_name"],
        "fingerprint": _MEMO["fingerprint"],
        "record_count": _MEMO["record_count"],
        "ttl_seconds": ttl_seconds(),
    }
