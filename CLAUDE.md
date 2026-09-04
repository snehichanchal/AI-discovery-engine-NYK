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

- `preprocess.py` is the single source of truth for data sources. `DATA_SOURCES` maps each `source_key` to a display name and a list of JSON file paths; `load_raw_data()` has a **per-source `if/elif` branch** that maps that source's idiosyncratic field names onto the unified record schema (`id, source_key, source_name, platform, author, rating, date, url, text`), de-duplicating by id via `seen_ids`. Adding a source means adding both a `DATA_SOURCES` entry and a normalization branch. `process_and_save()` then writes the CSV and re-indexes ChromaDB (collection `user_feedback`, batches of 200, deleting all existing ids first).
- `rag_engine.py` — Tab 1. Embedding similarity search over ChromaDB with a `source_key` metadata `where` filter, top-K snippets fed to the LLM with numbered citations returned to the UI. Note the filter is skipped when `len(selected_sources) >= 8`, which assumes exactly 8 sources exist.
- `context_engine.py` — Tab 2. No retrieval: reads the whole CSV, filters by `source_key`, and stuffs every record into one prompt. Returns `(answer, total_records, estimated_tokens, elapsed_time)` for the metrics row. The `enable_caching` flag is currently accepted but unused.
- `llm_provider.py` — one `query_llm()` dispatching on a provider string to Gemini / OpenAI / Anthropic / DeepSeek (DeepSeek via the OpenAI client with a custom `base_url`). Provider SDKs are imported lazily inside each branch. Errors are returned as user-facing strings, never raised — callers do not check for failure.
- `app.py` — sidebar picks provider + model + source checkboxes (all checked by default) and reads keys from `st.secrets` then `os.environ`; auto-runs `process_and_save()` on startup if the CSV or `vector_db/` is missing (first boot on Streamlit Cloud).

Both engines take `(query, selected_sources, provider, api_key, model_name)` — keep that shape when adding an engine.

## Deployment constraints (Streamlit Cloud)

The env-var preamble at the top of `app.py`, `preprocess.py`, and `rag_engine.py` is load-bearing, not boilerplate: single-threading BLAS/tokenizers and pinning `torch` to one thread with autograd off works around Python 3.14 segfaults, and swapping `sqlite3` for `pysqlite3` satisfies ChromaDB's minimum SQLite version on Debian. Preserve this block, before any other imports, in any new module that touches Chroma or torch.

`vector_db/` and `processed_data/` are committed so a fresh container can serve queries without re-embedding.

Note: recent commit messages describe migrating to a lightweight ONNX `DefaultEmbeddingFunction`, but the code still uses `SentenceTransformerEmbeddingFunction("all-MiniLM-L6-v2")` in both `preprocess.py` and `rag_engine.py`. If you change one, change both — the index and the query path must use the same embedding model.

Further background: `docs/docs/readme.md` (architecture), `docs/docs/deployment_plan.md`, `docs/docs/implementation_plan.md`.
