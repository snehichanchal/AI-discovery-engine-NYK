# User Feedback Discovery Engine

A Streamlit app that ingests first-party user-interview transcripts plus scraped Nykaa customer feedback from 8 public sources, normalizes it into a single dataset, indexes it in a local ChromaDB vector store, and lets you ask natural-language questions about it using Google Gemini (`gemini-flash-latest`).

It offers two contrasting query strategies side by side:

- **Tab 1 — RAG Discovery Engine**: semantic search retrieves the top-K most relevant feedback snippets, and only those go to the LLM. Cheap, fast, cites its sources.
- **Tab 2 — Massive Context Engine**: a conversational view over the *entire* dataset (2,193 records, ~211k tokens). The dataset is uploaded once to a shared Gemini context cache, so each question costs only ~20 fresh tokens instead of re-sending everything. Answers holistic "rank every complaint by frequency" questions that retrieval would miss. Chat history is kept in your browser.
Selecting a tab focuses its text box, so you can start typing immediately.

- **Tab 3 — Data Explorer**: record counts per source and a filterable table of everything ingested.

The repository ships with the scraped data, the processed CSV, and a prebuilt vector index, so it runs immediately after clone — no scraping or re-indexing required.

---

## 1. Prerequisites

- Python 3.11 (recommended; see `runtime.txt`). 3.12–3.14 also work.
- A Google Gemini API key ([get one here](https://aistudio.google.com/apikey)).
- Node.js 18+ **only** if you intend to run the scrapers.

The app is behind a login, and both the credentials and the API key come from the server environment (Section 3).

## 2. Run it locally

```bash
git clone <your-repo-url>
cd AI-discovery-engine-NYK
export GEMINI_API_KEY="your-key-here"
export APP_USERNAME="pick-a-username"
export APP_PASSWORD="pick-a-password"
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
./run.sh
```

`run.sh` creates `venv/`, installs `requirements.txt`, and starts Streamlit at http://localhost:8501.

If a venv already exists, you can skip straight to:

```bash
./venv/bin/streamlit run app.py
```

On the very first RAG query, ChromaDB downloads its ONNX embedding model (~80 MB) to `~/.cache/chroma`. This happens once.

## 3. Configuration

Everything is read from the **server environment**; nothing sensitive is ever entered in the UI (see Section 8). `run.sh` refuses to start the server if a required variable is missing.

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes | Gemini API key ([get one](https://aistudio.google.com/apikey)) |
| `APP_USERNAME` | yes | Login username |
| `APP_PASSWORD` | yes | Login password |
| `APP_SECRET_KEY` | strongly recommended | Signs session tokens. 64 hex chars: `python3 -c 'import secrets; print(secrets.token_hex(32))'` |
| `GEMINI_MODEL` | no | Overrides `gemini-flash-latest` — use it if a model is ever rejected for caching |
| `GEMINI_CACHE_TTL_SECONDS` | no | Cache lifetime, default 24h |

**Set `APP_SECRET_KEY`.** Without it a random key is generated per process, so every restart invalidates all sessions and signs everyone out. It is not the login password — nobody ever types it.

Alternatively, put the same keys in a local secrets file (consulted only when the environment variable is unset):

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

`.streamlit/secrets.toml` is gitignored and will not be committed.

Sessions last 72 hours, after which the app asks for the password again.

## 4. Using the app

1. Leave all 9 data sources checked, or uncheck sources to narrow the search.
2. Ask a question in Tab 1 or Tab 2.

The provider and model are fixed (`gemini-flash-latest`) and shown in the sidebar for reference.

Tab 2 is a chat: ask follow-up questions and it carries the previous turns. The transcript is stored in **your browser** (`localStorage`), so it survives a page reload but is never sent to the server, shared with other viewers, or synced across devices. "Clear chat" wipes it.

Costs: Tab 1 sends a handful of snippets. Tab 2 serves the dataset from a shared Gemini cache — the first query after a data change uploads ~211k tokens once, and every question after that costs roughly 20 fresh tokens. The metrics under each answer show cached vs fresh tokens for that turn.

---

## 5. Adding new data and re-indexing

**Never edit `processed_data/unified_feedback.csv` by hand.** It is generated, and `preprocess.py` overwrites it completely — manual edits are lost on the next run. Add data as raw JSON and regenerate.

Data flows one way: **raw JSON → `preprocess.py` → `processed_data/unified_feedback.csv` + `vector_db/` → the app**.

### The user-interview source

`user-interviews/*.txt` holds first-party research transcripts and is listed **first** in the sidebar. Unlike every other source it is plain text, not JSON: speaker-labelled Hindi, one turn per line (`साक्षात्कारकर्ता:` / `प्रतिभागी:`). `parse_interview()` in `preprocess.py` splits each file into one record per participant answer, carrying the preceding question for context, with a deterministic id so the CSV stays stable across re-runs. The directory is globbed, so **dropping in another `.txt` needs no code change** — just re-run Step 3.

Because the transcripts are Hindi, the vector index uses Gemini's multilingual `gemini-embedding-001` (768 dimensions) rather than an English-only model, so English questions in Tab 1 retrieve Hindi answers. Measured on 60 interview records against 60 English ones: the previous `all-MiniLM-L6-v2` returned **0/20** interview records for English queries, Gemini **17/20**. Transliterating the Hindi to Latin script was tested too and scored **0/20** — phonetic transliteration produces `vishalista`, not `wishlist`, so it does not help.

The embedder is chosen in one place, `embeddings.py`, imported by both `preprocess.py` and `rag_engine.py` so they cannot drift apart. The index records which embedder built it, and Tab 1 refuses to answer with a clear warning if that no longer matches — a mismatch would otherwise return plausible-looking nonsense. `GEMINI_API_KEY` is required — there is no local fallback embedder, which also means ChromaDB's bundled ONNX model is never downloaded or loaded.

Trade-off: query embedding is now a network call, adding roughly 500 ms to a Tab 1 search, and RAG depends on Gemini being reachable.

### Step 1 — Produce the raw JSON

Scrapers are standalone and are not run by the app. Each writes JSON into its own directory:

```bash
# Node scrapers (app_store, google_store, nykaa_products,
# community_discussions, community_discussions/trustpilot_data)
cd app_store && npm install && node scrape.js

# Python scrapers (reddit_data, youtube_data, youtube_nykaa, social_media)
./venv/bin/python reddit_data/scrape_playwright.py
```

You can also simply drop a new JSON file into the relevant directory.

### Step 2 — Make sure `preprocess.py` knows about the file

If you only added records to a file **already listed** in `DATA_SOURCES`, skip to Step 3.

For a new file or platform, two edits are required:

1. Add the path to the relevant `DATA_SOURCES` entry (or add a new entry with its own `source_key` and display `name`).
2. Add a matching branch in `load_raw_data()` mapping that source's field names onto the unified schema: `id, source_key, source_name, platform, author, rating, date, url, text`.

The second is easy to forget — without it the file is read and then **silently ignored**, with no error.

### Step 3 — Re-index

```bash
./venv/bin/python preprocess.py
```

This rewrites the CSV and rebuilds the ChromaDB collection from scratch (it clears existing vectors first, so it is safe to re-run). Expect a minute or two.

A cleaning pass runs first, so the retained total is lower than the raw count:

```
Cleaning: dropped 83 duplicates, 18 near-empty, 262 off-topic.
Retained 2193 records after cleaning.
Successfully indexed 2193 records into ChromaDB vector database.
```

Duplicates are compared on normalized text; near-empty means fewer than 3 words; the off-topic filter applies **only** to the broad-search sources (`reddit_data`, `social_media`, `youtube_data`), since the review sources are on-topic by construction. Tune the rules via `THREAD_SOURCES`, `RELEVANCE_PATTERN`, and `MIN_WORDS` at the top of `preprocess.py`.

### Step 4 — Update the expected record count in the tests

`tests/e2e/test_04_tabs_1_and_3.py` asserts the count shown in Tab 3:

```python
EXPECTED_RECORDS = "2,193"   # <- set this to your new total
```

That test failing after a re-index is intentional — it is a tripwire proving the data actually changed.

### Step 5 — Verify

With the app running (see Section 2), from the repository root:

```bash
./venv/bin/pip install -r requirements-dev.txt   # first time only
./venv/bin/playwright install chromium           # first time only

export E2E_USERNAME="$APP_USERNAME" E2E_PASSWORD="$APP_PASSWORD"
./venv/bin/pytest tests/e2e
```

That run is free. Add `E2E_RUN_LLM=1` to include the tests that call Gemini and cost money. See `tests/e2e/README.md`.

### Step 6 — Commit the regenerated artifacts

The CSV and the vector store are committed on purpose, so the deployed app never re-embeds on startup:

```bash
git add <your new raw json> processed_data/unified_feedback.csv vector_db/ tests/e2e/
git commit -m "Add <source> data and re-index"
git push
```

Use `git add vector_db/` as a **directory**. The HNSW index lives in a UUID-named subdirectory that gets a **new name** on every rebuild, so staging individual files would leave a stale index committed. Expect to see one directory deleted and another added.

### What happens automatically after the push

Streamlit Cloud redeploys. Because the CSV changed, its fingerprint changes, so the first Tab 2 query builds a **new** Gemini context cache — one ~211k-token upload, a few seconds — and every question after that is cheap again. Tab 1 uses the committed vector index immediately, with no re-embedding on the server. Nothing else needs touching.

Two caveats:

- The **old cache keeps billing storage until its TTL expires** (24h by default). Gemini has no delete-on-replace.
- A **code-only push rebuilds nothing.** The container restarts and its in-memory cache pointer is lost, but the app rediscovers the live cache through `caches.list()` and reuses it. Only a dataset change forces a rebuild.

> **The rule that matters:** `preprocess.py` and `rag_engine.get_embedding_function()` must always use the same embedding model. Change one without re-running `preprocess.py` and retrieval silently returns irrelevant results — no error is raised.

Locally, the sidebar's **🔄 Run / Refresh Data Pre-processing** button does Step 3 and drops the cache pointer in one click. Avoid it in production: it re-indexes into an ephemeral filesystem that is discarded on the next restart.

## 6. Deploying to Streamlit Community Cloud

Deploying from a fresh repo:

1. Push the repo to GitHub (public, or private if you have a Streamlit account tier that allows it).
2. At [share.streamlit.io](https://share.streamlit.io), click **New app** and select the repo and branch.
3. Set **Main file path** to `app.py`.
4. Under **Advanced settings**, confirm the Python version is **3.11**. `runtime.txt` pins this; do not select 3.14, which has known segfault issues with this stack.
5. Add **all** the required variables under **Secrets** (Streamlit Cloud injects them as environment variables):

   ```toml
   GEMINI_API_KEY = "your-gemini-key"
   APP_USERNAME   = "pick-a-username"
   APP_PASSWORD   = "pick-a-password"
   APP_SECRET_KEY = "64-hex-chars-from-secrets.token_hex(32)"
   ```

   Your local shell exports are **not** visible to Streamlit Cloud. Omitting `APP_SECRET_KEY` here signs every user out on each redeploy. Note that `run.sh` is not used on Cloud — it runs `app.py` directly — so a missing variable surfaces as a crashed app rather than a startup message.
6. Deploy. The first build takes a few minutes while dependencies install.

**Resource footprint** — this fits the free tier comfortably: roughly 300 MB of dependencies and under 300 MB of RAM in steady state. Embeddings use ChromaDB's bundled ONNX model rather than PyTorch specifically to keep it that way, so **do not add `sentence-transformers` or `torch` back to `requirements.txt`** — doing so pushes install size past 2 GB and RAM past 1 GB, and reintroduces the segfaults.

### Updating the deployed app with new data

Streamlit Cloud redeploys automatically on every push to the tracked branch. So once you have committed a re-index (Section 5), pushing is all that is needed:

```bash
git push
```

Because `processed_data/` and `vector_db/` are in the repo, the new container serves the updated data immediately without re-embedding. `app.py` only regenerates them if they are missing entirely.

Avoid the sidebar's **🔄 Run / Refresh Data Pre-processing** button in production. It re-indexes inside the container, which is slow, memory-hungry, and — because Streamlit Cloud's filesystem is ephemeral — thrown away on the next restart. Re-index locally and push instead.

---

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Everyone is signed out after a redeploy | `APP_SECRET_KEY` is unset, so the signing key is random per process. Set it in Secrets. |
| Tab 2 warns "Context caching unavailable" | The model was rejected for caching or the API errored. The app falls back to sending the dataset uncached (correct answers, higher cost). Try pinning `GEMINI_MODEL` to a concrete model ID. |
| Chat history vanished | It lives in the browser's `localStorage` — a different browser, a private window, or cleared site data all start empty. It is per-browser by design. |
| `EXPECTED_RECORDS` assertion fails | You re-indexed; update the constant in `tests/e2e/test_04_tabs_1_and_3.py` to the new total. |
| `⚠️ Vector database not found` | `vector_db/` is missing or empty. Run `./venv/bin/python preprocess.py`. |
| RAG returns irrelevant snippets | The index and query path are using different embedders. Re-run `preprocess.py`. |
| `sqlite3` version error from ChromaDB | System SQLite is too old. `pysqlite3-binary` in `requirements.txt` handles this on Linux; make sure it installed. |
| Segfault on startup or first query | Running on Python 3.14. Use 3.11 (`runtime.txt`). |
| Tab 2 errors about context length | The dataset exceeds the selected model's context window. Use a large-context model, or uncheck sources in the sidebar. |
| `GEMINI_API_KEY is not set` | The server environment has no key. Export it and restart, or add it to Streamlit Cloud Secrets. |

## 8. A note on API key handling

The key is read server-side in `app.py` and passed to `llm_provider.query_llm()`, which makes the outbound HTTPS call from the server. It is never bound to a Streamlit widget.

This matters: Streamlit sends widget values to the browser, so prefilling a `text_input` with a secret — even one marked `type="password"` — hands the plaintext key to every visitor, who can read it out of the DOM or the WebSocket frames. Masking is a display attribute, not a transport control. Keep the key out of widgets.

The app is also behind a login (`APP_USERNAME` / `APP_PASSWORD`), with sessions carried by HMAC-signed tokens that expire after 72 hours. The token is verified inside the query engines themselves, not only in the UI, so calling them without a valid session is refused.

The practical consequence is still that **anyone who can sign in spends your Gemini quota**. Caching makes each question cheap (~20 fresh tokens), but the first query after a data change uploads the full dataset. If you deploy publicly, restrict viewer access via Streamlit Cloud's app settings and monitor usage in Google AI Studio.

## 9. Further reading

- `tests/e2e/README.md` — the browser test suite and how to run it
- `CLAUDE.md` — architecture notes and conventions
- `docs/docs/readme.md` — full system architecture with diagrams
- `docs/docs/deployment_plan.md`, `docs/docs/implementation_plan.md`
