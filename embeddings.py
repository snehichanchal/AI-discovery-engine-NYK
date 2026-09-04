"""The one place the embedding model is chosen.

`preprocess.py` (which builds the index) and `rag_engine.py` (which queries it)
must use the *same* embedder. A mismatch does not raise -- it silently returns
irrelevant results -- so both import from here rather than constructing their
own, and the index records which embedder built it (see EMBEDDER_ID) so a
mismatch can be detected instead of quietly degrading retrieval.

Default is Gemini's multilingual `gemini-embedding-001`, because the
user-interview transcripts are Hindi. Measured on 60 interview records against
60 English ones with English queries: the previous English-centric
all-MiniLM-L6-v2 retrieved 0/20 interview records, Gemini 17/20.

GEMINI_API_KEY is required. There is deliberately no local fallback: the app
refuses to start without the key anyway, and a fallback embedder would quietly
build or query an index whose vectors are incompatible with the real one. That
also keeps ChromaDB's bundled ONNX model from ever being downloaded (~80 MB) or
loaded, so onnxruntime stays out of memory.
"""

import os

# 768 keeps the index compact; the model supports 128-3072.
GEMINI_EMBED_MODEL = "gemini-embedding-001"
EMBED_DIMENSIONS = 768

# Stored in the collection metadata and compared at query time.
EMBEDDER_ID = f"{GEMINI_EMBED_MODEL}:{EMBED_DIMENSIONS}"

_EMBEDDER = None


def embedder_id() -> str:
    return EMBEDDER_ID


def get_embedding_function():
    """Returns the shared embedding function, constructed once per process."""
    global _EMBEDDER
    if _EMBEDDER is not None:
        return _EMBEDDER

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError(
            "GEMINI_API_KEY is required to embed or query the vector index."
        )

    from chromadb.utils import embedding_functions

    _EMBEDDER = embedding_functions.GoogleGenaiEmbeddingFunction(
        model_name=GEMINI_EMBED_MODEL,
        dimension=EMBED_DIMENSIONS,
        api_key_env_var="GEMINI_API_KEY",
    )
    return _EMBEDDER


def check_index_matches(collection):
    """Returns a warning string if the index was built by a different embedder.

    Turns a silent retrieval failure into something the caller can surface.
    """
    try:
        stored = (collection.metadata or {}).get("embedder_id")
    except Exception:
        return ""
    current = embedder_id()
    if stored and stored != current:
        return (
            f"The vector index was built with '{stored}' but this app is querying with "
            f"'{current}'. Results will be unreliable until you re-run preprocess.py."
        )
    return ""
