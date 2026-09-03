import os
import sys

# Prevent threading locks & segmentation faults in Streamlit / PyTorch / HuggingFace
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

try:
    import torch
    torch.set_num_threads(1)
    if hasattr(torch, "set_grad_enabled"):
        torch.set_grad_enabled(False)
except Exception:
    pass

try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except Exception:
    pass

from llm_provider import query_llm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")


def get_embedding_function():
    """Returns SentenceTransformer embedding function with single-thread lock."""
    from chromadb.utils import embedding_functions
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


def search_and_answer(query: str, selected_sources: list, provider: str, api_key: str, model_name: str, top_k: int = 5):
    """
    RAG Pipeline:
    1. Embed query & search ChromaDB vector store.
    2. Filter results by selected_sources.
    3. Pass retrieved contexts to LLM.
    4. Return AI answer + source references.
    """
    if not query.strip():
        return "Please enter a question.", []

    try:
        import chromadb

        if not os.path.exists(VECTOR_DB_DIR) or not os.listdir(VECTOR_DB_DIR):
            return "⚠️ Vector database not found. Please run the Data Pre-processing script first.", []

        chroma_client = chromadb.PersistentClient(path=VECTOR_DB_DIR)
        sentence_transformer_ef = get_embedding_function()

        collection = chroma_client.get_collection(
            name="user_feedback",
            embedding_function=sentence_transformer_ef
        )

        # Build metadata filter if specific sources are selected
        where_filter = None
        if selected_sources and len(selected_sources) < 8:
            if len(selected_sources) == 1:
                where_filter = {"source_key": selected_sources[0]}
            else:
                where_filter = {"source_key": {"$in": selected_sources}}

        # Perform similarity search
        results = collection.query(
            query_texts=[query],
            n_results=top_k * 2 if where_filter else top_k,  # fetch extra to ensure filter matches
            where=where_filter
        )

        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []

        if not documents:
            return "No matching feedback entries found for your selected data sources.", []

        # Trim to top_k
        documents = documents[:top_k]
        metadatas = metadatas[:top_k]

        # Format context for LLM
        context_blocks = []
        source_citations = []

        for idx, (doc, meta) in enumerate(zip(documents, metadatas), 1):
            source_info = f"[{idx}] Source: {meta.get('source_name', 'Unknown')} | Platform: {meta.get('platform', 'N/A')} | Author: {meta.get('author', 'Anonymous')}"
            context_blocks.append(f"{source_info}\nFeedback Text: {doc}")
            source_citations.append({
                "index": idx,
                "source": meta.get('source_name', 'Unknown'),
                "platform": meta.get('platform', 'N/A'),
                "author": meta.get('author', 'Anonymous'),
                "rating": meta.get('rating', 'N/A'),
                "url": meta.get('url', ''),
                "text": doc
            })

        full_context = "\n\n".join(context_blocks)
        system_prompt = (
            "You are an expert User Feedback Discovery Engine. Answer the user's question directly and concisely "
            "based strictly on the provided customer feedback snippets below. Cite the source numbers [1], [2] when referencing feedback."
        )
        user_prompt = f"Customer Feedback Snippets:\n{full_context}\n\nQuestion: {query}\n\nDirect Answer:"

        answer = query_llm(
            provider=provider,
            api_key=api_key,
            model_name=model_name,
            prompt=user_prompt,
            system_prompt=system_prompt
        )

        return answer, source_citations

    except Exception as e:
        return f"Error in RAG retrieval: {e}", []
