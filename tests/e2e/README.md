# End-to-end tests

Browser tests that drive a **running** instance of the app with Playwright and
Chromium. Nothing is mocked: the app uses its real ChromaDB index, and the
tests marked `llm` call the real Gemini API.

## Setup

```bash
../../venv/bin/pip install -r ../../requirements-dev.txt
../../venv/bin/playwright install chromium
```

## Running

Start the app in one terminal, then from the repository root:

```bash
export E2E_USERNAME="$APP_USERNAME"
export E2E_PASSWORD="$APP_PASSWORD"

# Everything except the tests that spend money
./venv/bin/pytest tests/e2e

# Including the live Gemini tests
E2E_RUN_LLM=1 ./venv/bin/pytest tests/e2e
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `E2E_BASE_URL` | `http://localhost:8501` | App under test |
| `E2E_USERNAME` | `$APP_USERNAME` | Login username |
| `E2E_PASSWORD` | `$APP_PASSWORD` | Login password |
| `E2E_RUN_LLM` | unset | `1` includes tests that call Gemini |

No credential is stored in this directory; everything comes from the
environment.

## Files

| File | Covers |
|---|---|
| `test_01_auth.py` | Login gate, bad credentials, sign-out, session display |
| `test_02_config.py` | Server-side provider/model, no API-key widget, source checkboxes |
| `test_03_tab2_chat.py` | Chat transcript, bottom-pinned input, localStorage persistence, clear, per-browser isolation |
| `test_04_tabs_1_and_3.py` | RAG controls and validation, Data Explorer counts, console errors |
| `test_05_llm_live.py` | Live Gemini calls — answers, **cache-hit acceptance test**, follow-up context, RAG citations |

## The test that matters most

`test_05_llm_live.py::test_second_query_hits_the_cache` asserts that a second
question reports a non-trivial `cached_tokens`. If that fails, the global
context cache is not working and every query is paying full price for the whole
dataset, regardless of what the metrics tiles display.
