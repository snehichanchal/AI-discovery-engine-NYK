# Implementation Plan - LLM User Feedback Discovery Engine

This directory contains the implementation plan for building a non-technical, file-based Discovery Engine web application to ingest and query user feedback across 8 public domain sources.

---

## 1. Data Sources Included

The pre-processing pipeline will ingest and unify data from all 8 JSON feedback files:
1. `community_discussions/community_discussion_data.json` (Mouthshut discussions)
2. `app_store/nykaa_app_store_reviews.json` (Apple App Store reviews)
3. `google_store/nykaa_google_store_reviews.json` (Google Play reviews)
4. `youtube_nykaa/nykaa_youtube_comments.json` (Nykaa official YouTube channel comments)
5. `youtube_data/youtube_comments.json` (General YouTube comments)
6. `reddit_data/nykaa_playwright_results.json` (Reddit threads/comments)
7. `social_media/social_media_discussions.json` (Twitter/Social media posts)
8. `community_discussions/trustpilot_data/trustpilot_data/nykaa_trustpilot_reviews.json` (Trustpilot reviews)

---

## 2. Pre-processing Script (`preprocess.py`)
- Standardizes all raw JSON records into a unified structure: `{ id, source_file, platform, author, headline/title, content, rating, date, url }`.
- Exports a clean, consolidated CSV file: `processed_data/unified_feedback.csv`.
- Builds an embedded, file-based vector database using **ChromaDB** stored locally in `./vector_db/`.

---

## 3. Multi-LLM Provider Integration (`llm_provider.py`)
Supports API key entry via the UI for 4 major providers:
- **Google Gemini** (`gemini-1.5-pro`, `gemini-1.5-flash`) with Context Caching support.
- **OpenAI ChatGPT** (`gpt-4o`, `gpt-4o-mini`).
- **Anthropic Claude** (`claude-3-5-sonnet`, `claude-3-haiku`) with Prompt Caching support.
- **DeepSeek** (`deepseek-chat`, `deepseek-reasoner`) via OpenAI-compatible endpoint.

---

## 4. UI Architecture & Features (`app.py`)
Built with **Streamlit** (100% Python, non-technical, single command launcher `streamlit run app.py`):
- **Sidebar**:
  - LLM Provider Selection dropdown & API Key text input.
  - Data Source Checkboxes for all 8 files (**All checked by default**).
  - One-click "Run / Refresh Data Ingestion" button.
- **Tab 1: RAG Discovery Engine (Approaches 1 & 3)**:
  - Natural language search box.
  - Semantic vector search against ChromaDB filtered by selected sources.
  - Direct AI answer output with expandable source citations.
- **Tab 2: Massive Context Engine (5th Approach)**:
  - Separate UI tab for querying the full CSV context directly.
  - Context Caching toggle to optimize cost and latency for Gemini & Claude.
  - Token count and performance metrics.
- **Tab 3: Raw Data Explorer**:
  - Interactive table to filter, search, and inspect rows across all 8 sources.

---

## 5. Zero-Infrastructure & File-Based Storage
- No Docker, Redis, PostgreSQL, or cloud services needed.
- Uses `ChromaDB` (file-based vector DB in `./vector_db`) and `Pandas` (file-based CSV/Parquet in `./processed_data`).
