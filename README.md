# User Feedback Discovery Engine

A Streamlit app that ingests scraped Nykaa customer feedback from 8 public sources, normalizes it into a single dataset, indexes it in a local ChromaDB vector store, and lets you ask natural-language questions about it using Google Gemini (`gemini-flash-latest`).

It offers two contrasting query strategies side by side:

- **Tab 1 — RAG Discovery Engine**: semantic search retrieves the top-K most relevant feedback snippets, and only those go to the LLM. Cheap, fast, cites its sources.
- **Tab 2 — Massive Context Engine**: the entire filtered dataset (~2,300 records, roughly 120k tokens) is placed into a single prompt. Slower and far more expensive per question, but can answer holistic "rank every complaint by frequency" questions that retrieval would miss.
- **Tab 3 — Data Explorer**: record counts per source and a filterable table of everything ingested.

The repository ships with the scraped data, the processed CSV, and a prebuilt vector index, so it runs immediately after clone — no scraping or re-indexing required.

---

## 1. Prerequisites

- Python 3.11 (recommended; see `runtime.txt`). 3.12–3.14 also work.
- A Google Gemini API key ([get one here](https://aistudio.google.com/apikey)).
- Node.js 18+ **only** if you intend to run the scrapers.

## 2. Run it locally

```bash
git clone <your-repo-url>
cd AI-discovery-engine-NYK
export GEMINI_API_KEY="your-key-here"
./run.sh
```

`run.sh` creates `venv/`, installs `requirements.txt`, and starts Streamlit at http://localhost:8501.

If a venv already exists, you can skip straight to:

```bash
./venv/bin/streamlit run app.py
```

On the very first RAG query, ChromaDB downloads its ONNX embedding model (~80 MB) to `~/.cache/chroma`. This happens once.

## 3. Provide the API key

The app takes the Gemini key from the **server environment** and refuses to start without it. There is no key input in the UI — this is deliberate, see Section 8.

```bash
export GEMINI_API_KEY="your-key-here"
```

Alternatively, create a local secrets file (checked only if the env var is unset):

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

`.streamlit/secrets.toml` is gitignored and will not be committed.

If the key is missing, the app stops immediately with instructions rather than rendering a broken UI.

## 4. Using the app

1. Leave all 8 data sources checked, or uncheck sources to narrow the search.
2. Ask a question in Tab 1 or Tab 2.

The provider and model are fixed (`gemini-flash-latest`) and shown in the sidebar for reference.

Costs are worth knowing before you click: **Tab 1 sends a handful of snippets; Tab 2 sends the whole dataset on every single query**, around 120k tokens. Start with Tab 1 and reach for Tab 2 only for genuinely dataset-wide questions.

---

## 5. Adding new data and re-indexing

Data flows in one direction: **raw JSON → `preprocess.py` → `processed_data/unified_feedback.csv` + `vector_db/`**. Re-indexing is what makes new data visible to the app.

### Step 1 — Produce the raw JSON

Scrapers are standalone and are not run by the app. Each writes JSON into its own directory:

```bash
# Node scrapers (app_store, google_store, nykaa_products,
# community_discussions, community_discussions/trustpilot_data)
cd app_store && npm install && node scrape.js

# Python scrapers (reddit_data, youtube_data, youtube_nykaa, social_media)
./venv/bin/python reddit_data/scrape_playwright.py
```

### Step 2 — Make sure `preprocess.py` knows about the file

If you added records to a file that is **already listed** in `DATA_SOURCES` at the top of `preprocess.py`, skip to Step 3.

For a genuinely new file or platform, two edits are required:

1. Add the path to the relevant `DATA_SOURCES` entry (or add a new entry with its own `source_key` and display `name`).
2. Add a matching branch in `load_raw_data()` mapping that source's field names onto the unified schema: `id, source_key, source_name, platform, author, rating, date, url, text`.

The second step is easy to forget — without it, the file is loaded and then silently ignored.

### Step 3 — Re-index

```bash
./venv/bin/python preprocess.py
```

This rewrites the CSV and rebuilds the ChromaDB collection from scratch (it clears existing vectors first, so it is safe to re-run). Expect a minute or two. It should end with:

```
Successfully indexed NNNN records into ChromaDB vector database.
```

Confirm the count went up as you expected. You can also just launch the app and check Tab 3.

### Step 4 — Commit the regenerated artifacts

Both the CSV and the vector store are committed on purpose, so the deployed app never has to re-embed on startup:

```bash
git add <your new raw json> processed_data/unified_feedback.csv vector_db/
git commit -m "Add <source> data and re-index"
git push
```

`vector_db/` includes `chroma.sqlite3` **and** the UUID-named subdirectory holding the HNSW index files. Commit the whole directory — the subdirectory name changes each time the collection is rebuilt, so `git add vector_db/` (not individual files) is what you want, and you will see the old subdirectory deleted and a new one added.

> **The one rule that matters:** `preprocess.py` and `rag_engine.get_embedding_function()` must always use the same embedding model. If you change the embedder in one place, change it in the other and re-run `preprocess.py`. A mismatch does not raise an error — it silently returns irrelevant search results.

---

## 6. Deploying to Streamlit Community Cloud

Deploying from a fresh repo:

1. Push the repo to GitHub (public, or private if you have a Streamlit account tier that allows it).
2. At [share.streamlit.io](https://share.streamlit.io), click **New app** and select the repo and branch.
3. Set **Main file path** to `app.py`.
4. Under **Advanced settings**, confirm the Python version is **3.11**. `runtime.txt` pins this; do not select 3.14, which has known segfault issues with this stack.
5. Add your key under **Secrets** as `GEMINI_API_KEY = "your-key-here"` (see `.streamlit/secrets.toml.example`). Without it the app will start but show a configuration error.
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
| `⚠️ Vector database not found` | `vector_db/` is missing or empty. Run `./venv/bin/python preprocess.py`. |
| RAG returns irrelevant snippets | The index and query path are using different embedders. Re-run `preprocess.py`. |
| `sqlite3` version error from ChromaDB | System SQLite is too old. `pysqlite3-binary` in `requirements.txt` handles this on Linux; make sure it installed. |
| Segfault on startup or first query | Running on Python 3.14. Use 3.11 (`runtime.txt`). |
| Tab 2 errors about context length | The dataset exceeds the selected model's context window. Use a large-context model, or uncheck sources in the sidebar. |
| `GEMINI_API_KEY is not set` | The server environment has no key. Export it and restart, or add it to Streamlit Cloud Secrets. |

## 8. A note on API key handling

The key is read server-side in `app.py` and passed to `llm_provider.query_llm()`, which makes the outbound HTTPS call from the server. It is never bound to a Streamlit widget.

This matters: Streamlit sends widget values to the browser, so prefilling a `text_input` with a secret — even one marked `type="password"` — hands the plaintext key to every visitor, who can read it out of the DOM or the WebSocket frames. Masking is a display attribute, not a transport control. Keep the key out of widgets.

The practical consequence is that **anyone who can open the deployed app spends your Gemini quota**. Tab 2 sends roughly 120k tokens per question. If you deploy publicly, restrict viewer access via Streamlit Cloud's app settings, and monitor usage in Google AI Studio.

## 9. Further reading

- `CLAUDE.md` — architecture notes and conventions
- `docs/docs/readme.md` — full system architecture with diagrams
- `docs/docs/deployment_plan.md`, `docs/docs/implementation_plan.md`
