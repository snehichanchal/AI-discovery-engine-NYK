# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Streamlit app ("User Feedback Discovery Engine") that ingests scraped Nykaa customer feedback from 8 public sources, normalizes it into one CSV + a ChromaDB vector store, and answers natural-language questions via two contrasting query strategies backed by four swappable LLM providers. There are no tests and no lint config.

## Commands

```bash
./run.sh                          # creates venv/ if missing, installs deps, runs streamlit
./venv/bin/streamlit run app.py   # run directly once venv exists
./venv/bin/python preprocess.py   # rebuild unified_feedback.csv + vector_db/ from raw JSON
```

Scrapers are standalone one-off scripts, run individually and not wired into the app:
- Python: `python <dir>/scrape*.py` (Playwright/PRAW/SerpAPI variants under `reddit_data/`)
- Node: `cd <dir> && npm install && node scrape*.js` (each of `app_store/`, `google_store/`, `nykaa_products/`, `community_discussions/`, `community_discussions/trustpilot_data/` has its own `package.json`)

Scrapers write raw JSON into their own directory; `preprocess.py` reads those files by hardcoded path.

## Architecture

Pipeline: **raw JSON per source → `preprocess.py` → `processed_data/unified_feedback.csv` + `vector_db/` (ChromaDB) → query engines → `llm_provider.py` → Streamlit UI**.

- `preprocess.py` is the single source of truth for data sources. **`DATA_SOURCES` insertion order drives the sidebar's checkbox order** — `user_interviews` is first deliberately. Most sources are JSON; `user_interviews` is plain speaker-labelled Hindi text, parsed by `parse_interview()` and short-circuited before the `json.load` in the file loop, with its directory globbed so new transcripts need no code change. `DATA_SOURCES` maps each `source_key` to a display name and a list of JSON file paths; `load_raw_data()` has a **per-source `if/elif` branch** that maps that source's idiosyncratic field names onto the unified record schema (`id, source_key, source_name, platform, author, rating, date, url, text`), de-duplicating by id via `seen_ids`. Adding a source means adding both a `DATA_SOURCES` entry and a normalization branch. `process_and_save()` then writes the CSV and re-indexes ChromaDB (collection `user_feedback`, batches of 200, deleting all existing ids first).
- `rag_engine.py` — Tab 1. Embedding similarity search over ChromaDB with a `source_key` metadata `where` filter, top-K snippets fed to the LLM with numbered citations returned to the UI. Note the filter is skipped when `len(selected_sources) >= 8`, which assumes exactly 8 sources exist.
- `context_engine.py` — Tab 2. No retrieval: reads the whole CSV, filters by `source_key`, and stuffs every record into one prompt. Returns `(answer, total_records, estimated_tokens, elapsed_time)` for the metrics row. The `enable_caching` flag is currently accepted but unused.
- `llm_provider.py` — Gemini access via the `google-genai` SDK (the legacy `google-generativeai` is end-of-life and cannot create caches). `query_llm()` keeps its original signature for the RAG path; `generate_with_cache()` answers against a cached dataset; `generate_uncached()` is the fallback. Errors are returned as user-facing strings, never raised.
- `gemini_cache.py` — owns ONE global Gemini context cache holding the whole dataset, so Tab 2 sends only the question instead of ~140k tokens. Created lazily under a `threading.Lock` (Streamlit serves sessions as threads in one process, so unsynchronized first-queries would build and bill for duplicate caches). Keyed on a SHA-256 fingerprint of the CSV, and rediscovered after a restart via `caches.list()` matching on `display_name` — Streamlit Cloud's disk is ephemeral, so a local state file would not survive. `invalidate()` is wired to the re-preprocess button.
- `app.py` — provider and model are hardcoded (`PROVIDER = "gemini"`, `MODEL_NAME = "gemini-flash-latest"`; note `PROVIDER` is the lowercase dispatch key `query_llm()` matches on, while `PROVIDER_LABEL` is for display). `GEMINI_API_KEY` is read from `os.environ` then `st.secrets`, and the app `st.stop()`s with a configuration error if it is absent. The sidebar offers only source checkboxes (all checked by default). Auto-runs `process_and_save()` on startup if the CSV or `vector_db/` is missing (first boot on Streamlit Cloud).

Both engines take `(query, selected_sources, provider, api_key, model_name)` — keep that shape when adding an engine.

## Deployment constraints (Streamlit Cloud)

The env-var preamble at the top of `app.py`, `preprocess.py`, and `rag_engine.py` is load-bearing, not boilerplate: single-threading BLAS/tokenizers avoids segfaults under Streamlit's threading model, and swapping `sqlite3` for `pysqlite3` satisfies ChromaDB's minimum SQLite version on Debian. Preserve this block, before any other imports, in any new module that touches Chroma.

`runtime.txt` pins Python 3.11 for Streamlit Cloud. Embeddings use ChromaDB's bundled ONNX `DefaultEmbeddingFunction` (all-MiniLM-L6-v2) — torch and `sentence-transformers` are deliberately **not** dependencies, which keeps the install ~300 MB and steady-state RSS under ~300 MB. `preprocess.py` and `rag_engine.get_embedding_function()` must always use the same embedder; changing one without re-running `preprocess.py` silently corrupts retrieval. The ONNX weights (~80 MB) download to `~/.cache/chroma` on first use.

`vector_db/` and `processed_data/` are committed so a fresh container can serve queries without re-embedding.

Further background: `docs/docs/readme.md` (architecture), `docs/docs/deployment_plan.md`, `docs/docs/implementation_plan.md`.

## API key handling

The key is read server-side and passed straight to `query_llm()`, which makes the outbound call from the server. **Never bind it to a Streamlit widget.** Widget values are serialized to the browser, so prefilling a `text_input` with the key — even `type="password"`, which only masks characters visually — leaks the plaintext to every visitor via the DOM or WebSocket frames. This was the previous behavior and was deliberately removed.

## Gemini context caching

Tab 2's dataset is cached server-side by Gemini and reused across all users and sessions. Two invariants:

- **The cached prefix must not vary per user.** Source checkboxes narrow Tab 2 by *instructing* the model (`_source_instruction()`), never by filtering the cached content — filtering would need a separate cache per combination.
- **A caching failure must degrade cost, not availability.** `query_massive_context()` falls back to the full uncached prompt and reports the reason; never let a cache error surface as a broken app.

Caches are always TTL-bound (no permanent cache exists). Refreshes are driven by the dataset fingerprint; expiry is healed transparently. `GEMINI_MODEL` overrides the model — pin a concrete cacheable ID if the alias is rejected — and `GEMINI_CACHE_TTL_SECONDS` tunes the 24h default.

## Gotchas

- **Never count sources with a literal.** `rag_engine` previously used `len(selected_sources) < 8`; adding a 9th source meant selecting 8 of 9 silently searched *all* of them. It now compares against `len(DATA_SOURCES)`.
- **`embeddings.py` is the only place the embedding model is chosen.** `preprocess.py` and `rag_engine.py` both import from it; never construct an embedding function anywhere else. Default is multilingual `gemini-embedding-001` (768-dim) because the interview transcripts are Hindi — the old English-only MiniLM scored 0/20 on English queries against Hindi records, Gemini 17/20, and transliteration also scored 0/20. There is **no local fallback embedder** and that is deliberate: the app cannot start without the key anyway, and a fallback would quietly build or query an index whose vectors are incompatible. It also keeps ChromaDB's bundled ONNX model from ever downloading (~80 MB) or loading — `onnxruntime` never enters the process.
- **The collection stores `embedder_id` in its metadata.** `check_index_matches()` compares it at query time and Tab 1 refuses with a warning on a mismatch, rather than returning nonsense. `preprocess.py` drops and rebuilds the collection when the embedder changes, since dimensionality changes too.
- **`EXPECTED_RECORDS` in `tests/e2e/test_04_tabs_1_and_3.py` must be updated after any re-index.** The failure is a deliberate tripwire.

## Hot paths

Streamlit re-runs the entire script on every interaction, so anything constructed at module scope in a request path is rebuilt constantly. Three things are cached per process; keep it that way:

- `rag_engine.get_collection()` — the ChromaDB client and collection cost ~100ms to construct and were previously rebuilt on every query. `reset_collection()` drops the handle after a re-index.
- `embeddings.get_embedding_function()` and `llm_provider.get_client()` — memoized module-level singletons.
- `app.load_feedback_table()` — `@st.cache_data` keyed on the CSV's mtime, so Tab 3 does not re-parse the file on every rerun.

`gemini_cache` reads the CSV with the stdlib `csv` module rather than pandas: it only concatenates strings, so materializing a DataFrame of the whole dataset was wasted work.

## Browser storage bridge

`components/browser_storage/` backs two stores via `browser_storage.py`: the Tab 2 chat history and the session token (so a refresh does not sign the user out — `st.session_state` is per page load).

Two rules, both learned from failures:

- **Each bridge may be rendered at most once per script run.** Rendering the same component key twice raises `StreamlitDuplicateElementKey`. Writes are therefore *queued* (`queue_save`, `queue_token_clear`, …) and performed by the single `sync_chat()` / `sync_session_token()` call.
- **Never issue a write immediately before `st.rerun()`** — the rerun replaces the component's pending args before the browser commits them. Queue it and let the next run perform it.

The restored token is re-verified through `verify_session_token()`, so an expired or tampered copy is rejected rather than trusted.
