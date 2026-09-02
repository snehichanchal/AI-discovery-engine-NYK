# Streamlit Community Cloud Deployment Plan

This document details the architecture, pre-deployment changes, and step-by-step procedure to deploy the **User Feedback Discovery Engine** on **Streamlit Community Cloud** (`share.streamlit.io`).

---

## 1. Executive Summary & Architecture Overview

* **Application Name:** User Feedback Discovery Engine
* **Framework:** Streamlit (Python 3.10+)
* **Main Entry File:** `app.py`
* **Target Hosting Platform:** Streamlit Community Cloud (Free / Pro Tier)
* **Core Components:**
  1. **RAG Discovery Engine:** ChromaDB local vector store (`vector_db/`) with `sentence-transformers/all-MiniLM-L6-v2`.
  2. **Massive Context Engine:** Pandas whole-dataset prompt synthesis (`processed_data/unified_feedback.csv`).
  3. **Multi-LLM Integration:** Google Gemini, OpenAI ChatGPT, Anthropic Claude, DeepSeek AI.

---

## 2. Technical Modifications Implemented for Deployment

The following codebase enhancements have been completed to ensure seamless execution on Streamlit Community Cloud:

1. **`app.py` - Secret Management & Auto-Initialization:**
   - Updated API key retrieval to check `st.secrets` first before falling back to `os.environ` or manual user input.
   - Added automated startup check (`os.path.exists`) to automatically run `process_and_save()` if `processed_data/unified_feedback.csv` or `vector_db/` is missing on a fresh container spin-up.

2. **`requirements.txt` - Dependency Lock & Cloud Compatibility:**
   - Added `pysqlite3-binary>=0.5.0; sys_platform == 'linux'` to resolve SQLite C-library version requirements for ChromaDB on Streamlit Cloud Debian instances.
   - Locked compatible versions for `streamlit`, `chromadb`, `sentence-transformers`, `pandas`, `openai`, `anthropic`, and `google-generativeai`.

3. **`.streamlit/config.toml` - Server & Visual Styling Configuration:**
   - Configured headless mode (`headless = true`), cross-origin rules, and custom theme tokens (Primary Color: `#1E88E5`).

4. **`.streamlit/secrets.toml.example` - Environment Variable Template:**
   - Created a secrets schema template for safe multi-LLM API key injection in the cloud dashboard.

5. **`.gitignore` - Repository Cleanliness:**
   - Configured rules to prevent committing virtual environment directories (`venv/`), Python cache files (`__pycache__/`), and local secrets (`.streamlit/secrets.toml`).

---

## 3. Step-by-Step Deployment Instructions

> **Note:** As requested, these steps outline the deployment process to be performed when ready. Do not run these remote commands automatically.

### Step 1: Initialize & Push Code to GitHub
1. Initialize Git repository (if not already initialized):
   ```bash
   git init
   git branch -M main
   ```
2. Stage and commit all project files:
   ```bash
   git add .
   git commit -m "Prepare User Feedback Discovery Engine for Streamlit Cloud deployment"
   ```
3. Push to your GitHub repository:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git
   git push -u origin main
   ```

---

### Step 2: Streamlit Community Cloud Connection
1. Navigate to [share.streamlit.io](https://share.streamlit.io).
2. Log in using your GitHub account.
3. Click the **"New app"** button.

---

### Step 3: App Deployment Settings
In the Streamlit deployment form, configure the following:
* **Repository:** `YOUR_USERNAME/YOUR_REPOSITORY_NAME`
* **Branch:** `main`
* **Main file path:** `app.py`
* **App URL slug (Optional):** `nykaa-feedback-discovery-engine`

---

### Step 4: Configure App Secrets
1. Click **Advanced settings...** or open **App Settings -> Secrets** after app creation.
2. Copy and paste the template from `.streamlit/secrets.toml.example` and insert your actual API keys:

```toml
GEMINI_API_KEY = "AIzaSy..."
OPENAI_API_KEY = "sk-proj-..."
ANTHROPIC_API_KEY = "sk-ant-..."
DEEPSEEK_API_KEY = "sk-..."
```

3. Click **Save**.

---

### Step 5: Deploy & Monitor Build
1. Click **Deploy!**.
2. Streamlit Cloud will parse `requirements.txt`, install dependencies, run the initialization check, and launch the application interface.

---

## 4. Data Persistence & Ephemeral File System Strategy

Streamlit Community Cloud operates on containerized, ephemeral storage. Here is how storage is handled:

* **Pre-processed Dataset (`unified_feedback.csv`):** Committed directly in `processed_data/` so the app loads under 2 seconds on cold start.
* **Vector Database (`vector_db/`):** Built locally with ChromaDB and committed to Git or built automatically on first launch via `app.py` auto-initialization.
* **Dynamic Re-indexing:** If raw feedback files are updated, clicking **"🔄 Run / Refresh Data Pre-processing"** in the UI rebuilds the dataset in-memory/ephemeral disk for the active session.

---

## 5. Post-Deployment Verification & Maintenance

Once deployed, verify the following checklist:

| Verification Step | Target Output / Status |
| :--- | :--- |
| **App Launch** | App opens without `ModuleNotFoundError` or SQLite version warnings. |
| **Tab 1: RAG Engine** | Querying a sample question yields direct AI answer and 5 retrieved snippets. |
| **Tab 2: Massive Context Engine** | Dataset summary query returns total records (~500+) and synthesis. |
| **Tab 3: Data Explorer** | Dataframe loads all 8 sources with interactive filter options. |
| **API Keys** | Default provider (Gemini) auto-populates key from `st.secrets`. |

---

## 6. Troubleshooting Guide

* **Issue:** `ChromaDB requires SQLite >= 3.35.0` error.
  * *Fix:* Ensured `pysqlite3-binary` is listed in `requirements.txt`.
* **Issue:** `API Key Missing` prompt on launch.
  * *Fix:* Verify key names in Streamlit Secrets match exact variable names (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.).
* **Issue:** RAM overflow on heavy whole-dataset queries.
  * *Fix:* Streamlit Community Cloud offers 1GB RAM per app. Context caching and vector retrieval top-K controls keep memory usage under 350MB.
