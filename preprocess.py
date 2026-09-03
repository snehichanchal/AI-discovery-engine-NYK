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
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except Exception:
    pass

import json
import uuid
import pandas as pd
from datetime import datetime

# Root directory of the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(BASE_DIR, "processed_data")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")

# Mapping of file source keys to relative paths and display names
DATA_SOURCES = {
    "community_discussions": {
        "name": "Community Discussions (Mouthshut)",
        "paths": [
            os.path.join(BASE_DIR, "community_discussions", "community_discussion_data.json")
        ]
    },
    "app_store": {
        "name": "Apple App Store Reviews",
        "paths": [
            os.path.join(BASE_DIR, "app_store", "nykaa_app_store_reviews.json"),
            os.path.join(BASE_DIR, "app_store", "nykaa_app_store_wishlist_reviews_6months.json")
        ]
    },
    "google_store": {
        "name": "Google Play Store Reviews",
        "paths": [
            os.path.join(BASE_DIR, "google_store", "nykaa_google_store_reviews.json"),
            os.path.join(BASE_DIR, "google_store", "nykaa_wishlist_reviews.json")
        ]
    },
    "youtube_nykaa": {
        "name": "Nykaa YouTube Comments",
        "paths": [
            os.path.join(BASE_DIR, "youtube_nykaa", "nykaa_youtube_comments.json"),
            os.path.join(BASE_DIR, "youtube_nykaa", "nykaa_youtube_wishlist_comments.json")
        ]
    },
    "youtube_data": {
        "name": "General YouTube Comments",
        "paths": [
            os.path.join(BASE_DIR, "youtube_data", "youtube_comments.json")
        ]
    },
    "reddit_data": {
        "name": "Reddit Discussions",
        "paths": [
            os.path.join(BASE_DIR, "reddit_data", "nykaa_playwright_results.json")
        ]
    },
    "social_media": {
        "name": "Social Media Discussions",
        "paths": [
            os.path.join(BASE_DIR, "social_media", "social_media_discussions.json"),
            os.path.join(BASE_DIR, "social_media", "nykaa_wishlist_social_reviews.json")
        ]
    },
    "trustpilot": {
        "name": "Trustpilot Reviews",
        "paths": [
            os.path.join(BASE_DIR, "community_discussions", "trustpilot_data", "nykaa_trustpilot_wishlist_reviews.json")
        ]
    }
}


def load_raw_data():
    """Reads all raw JSON datasets (including newer scraped wishlist files) and normalizes them into a unified list of dicts."""
    records = []
    seen_ids = set()

    for source_key, info in DATA_SOURCES.items():
        source_paths = info.get("paths", [])
        source_name = info["name"]

        for file_path in source_paths:
            if not os.path.exists(file_path):
                print(f"Warning: File not found: {file_path}")
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if source_key == "community_discussions":
                    for item in data:
                        text = f"{item.get('headline', '')}\n{item.get('content', '')}".strip()
                        rec_id = item.get("id") or str(uuid.uuid4())
                        if rec_id in seen_ids:
                            continue
                        if text:
                            seen_ids.add(rec_id)
                            records.append({
                                "id": rec_id,
                                "source_key": source_key,
                                "source_name": source_name,
                                "platform": item.get("platform", "Mouthshut"),
                                "author": item.get("author", "Anonymous"),
                                "rating": "N/A",
                                "date": item.get("scraped_at", ""),
                                "url": item.get("url", ""),
                                "text": text
                            })

                elif source_key == "app_store":
                    for item in data:
                        title = item.get("title", "")
                        body = item.get("body", "")
                        text = f"{title}\n{body}".strip()
                        rec_id = item.get("id") or f"appstore_{item.get('author')}_{item.get('date')}_{hash(text)}"
                        if rec_id in seen_ids:
                            continue
                        if text:
                            seen_ids.add(rec_id)
                            records.append({
                                "id": str(uuid.uuid4()),
                                "source_key": source_key,
                                "source_name": source_name,
                                "platform": "Apple App Store",
                                "author": item.get("author", "Anonymous"),
                                "rating": str(item.get("rating", "N/A")),
                                "date": item.get("date", ""),
                                "url": item.get("url", ""),
                                "text": text
                            })

                elif source_key == "google_store":
                    for item in data:
                        rec_id = item.get("id") or str(uuid.uuid4())
                        if rec_id in seen_ids:
                            continue
                        text = item.get("text", "") or ""
                        if text.strip():
                            seen_ids.add(rec_id)
                            records.append({
                                "id": rec_id,
                                "source_key": source_key,
                                "source_name": source_name,
                                "platform": "Google Play Store",
                                "author": item.get("userName", "Anonymous"),
                                "rating": str(item.get("score", "N/A")),
                                "date": item.get("date", ""),
                                "url": item.get("url", ""),
                                "text": text.strip()
                            })

                elif source_key in ["youtube_nykaa", "youtube_data"]:
                    for item in data:
                        title = item.get("video_title", "")
                        content = item.get("content", "")
                        text = f"[Video: {title}]\n{content}".strip() if title else content.strip()
                        rec_id = item.get("comment_id") or item.get("id") or str(uuid.uuid4())
                        if rec_id in seen_ids:
                            continue
                        if text:
                            seen_ids.add(rec_id)
                            records.append({
                                "id": rec_id,
                                "source_key": source_key,
                                "source_name": source_name,
                                "platform": item.get("platform", "YouTube"),
                                "author": item.get("author", "Anonymous"),
                                "rating": "N/A",
                                "date": item.get("scraped_at", "") or item.get("created_at", ""),
                                "url": item.get("video_url", "") or item.get("url", ""),
                                "text": text
                            })

                elif source_key == "reddit_data":
                    for item in data:
                        title = item.get("title", "")
                        content = item.get("content", "")
                        text = f"{title}\n{content}".strip()
                        subreddit = item.get("subreddit", "Reddit")
                        rec_id = item.get("id") or str(uuid.uuid4())
                        if rec_id not in seen_ids and text:
                            seen_ids.add(rec_id)
                            records.append({
                                "id": rec_id,
                                "source_key": source_key,
                                "source_name": source_name,
                                "platform": f"Reddit (r/{subreddit})",
                                "author": item.get("author", "Anonymous"),
                                "rating": f"Score: {item.get('score', 0)}",
                                "date": str(item.get("created_utc", "")),
                                "url": item.get("url", ""),
                                "text": text
                            })
                        # Process comments if any
                        for comment in item.get("comments", []):
                            c_body = comment.get("body", "")
                            c_id = comment.get("id") or str(uuid.uuid4())
                            if c_id not in seen_ids and c_body.strip():
                                seen_ids.add(c_id)
                                records.append({
                                    "id": c_id,
                                    "source_key": source_key,
                                    "source_name": source_name,
                                    "platform": f"Reddit (r/{subreddit} Comment)",
                                    "author": comment.get("author", "Anonymous"),
                                    "rating": f"Score: {comment.get('score', 0)}",
                                    "date": str(comment.get("created_utc", "")),
                                    "url": item.get("url", ""),
                                    "text": f"[In thread: {title}]\n{c_body}".strip()
                                })

                elif source_key == "social_media":
                    for item in data:
                        text = item.get("content", "") or ""
                        rec_id = item.get("id") or str(uuid.uuid4())
                        if rec_id in seen_ids:
                            continue
                        if text.strip():
                            seen_ids.add(rec_id)
                            records.append({
                                "id": rec_id,
                                "source_key": source_key,
                                "source_name": source_name,
                                "platform": item.get("platform", "Social Media"),
                                "author": item.get("author", "User"),
                                "rating": "N/A",
                                "date": item.get("created_at", "") or item.get("scraped_at", ""),
                                "url": item.get("url", ""),
                                "text": text.strip()
                            })

                elif source_key == "trustpilot":
                    for item in data:
                        headline = item.get("headline", "")
                        content = item.get("content", "")
                        text = f"{headline}\n{content}".strip()
                        rec_id = item.get("id") or f"trustpilot_{item.get('author')}_{hash(text)}"
                        if rec_id in seen_ids:
                            continue
                        if text:
                            seen_ids.add(rec_id)
                            records.append({
                                "id": rec_id,
                                "source_key": source_key,
                                "source_name": source_name,
                                "platform": item.get("platform", "Trustpilot"),
                                "author": item.get("author", "Anonymous"),
                                "rating": str(item.get("rating", "N/A")),
                                "date": item.get("date", "") or item.get("scraped_at", ""),
                                "url": item.get("url", ""),
                                "text": text
                            })
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

    return records


def process_and_save():
    """Runs data preprocessing, outputs unified CSV, and builds ChromaDB vector store."""
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(VECTOR_DB_DIR, exist_ok=True)

    print("Loading raw feedback from 8 sources...")
    records = load_raw_data()
    print(f"Successfully normalized {len(records)} feedback records.")

    df = pd.DataFrame(records)
    csv_path = os.path.join(PROCESSED_DIR, "unified_feedback.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"Saved unified CSV to: {csv_path}")

    # Build ChromaDB vector database
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        print("Initializing ChromaDB vector store...")
        chroma_client = chromadb.PersistentClient(path=VECTOR_DB_DIR)

        # SentenceTransformer embedding function with single-thread lock
        sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        # Get or create collection
        collection = chroma_client.get_or_create_collection(
            name="user_feedback",
            embedding_function=sentence_transformer_ef
        )

        # Reset/re-populate
        existing_ids = collection.get()["ids"]
        if existing_ids:
            print(f"Clearing {len(existing_ids)} existing vector entries...")
            collection.delete(ids=existing_ids)

        print("Indexing documents into ChromaDB...")
        batch_size = 200
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            documents = [r["text"] for r in batch]
            ids = [r["id"] for r in batch]
            metadatas = [{
                "source_key": r["source_key"],
                "source_name": r["source_name"],
                "platform": r["platform"],
                "author": r["author"],
                "rating": r["rating"],
                "url": r["url"]
            } for r in batch]

            collection.add(
                documents=documents,
                ids=ids,
                metadatas=metadatas
            )

        print(f"Successfully indexed {len(records)} records into ChromaDB vector database.")
    except Exception as e:
        print(f"ChromaDB indexing warning: {e}")

    return csv_path


if __name__ == "__main__":
    process_and_save()
