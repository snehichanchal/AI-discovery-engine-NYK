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

import glob
import json
import re
import uuid
import pandas as pd
from datetime import datetime

# Root directory of the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(BASE_DIR, "processed_data")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")

# Mapping of file source keys to relative paths and display names
# Ordering here drives the sidebar's "Data Source Selection" list. Primary
# research sits at the top, ahead of the scraped public sources.
DATA_SOURCES = {
    "user_interviews": {
        "name": "User Interviews (Primary Research)",
        # Globbed so newly added transcripts are picked up without a code edit.
        "paths": sorted(glob.glob(os.path.join(BASE_DIR, "user-interviews", "*.txt")))
    },
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


INTERVIEWER_PREFIX = "साक्षात्कारकर्ता:"
PARTICIPANT_PREFIX = "प्रतिभागी:"


def parse_interview(path):
    """Splits a transcript into (question, answer) turns.

    Transcripts are speaker-labelled Hindi text, one turn per line. Each
    participant answer becomes a record carrying the interviewer's preceding
    question, which keeps chunks small enough to embed and gives each one
    enough context to stand alone.
    """
    pairs, pending_question = [], ""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(INTERVIEWER_PREFIX):
                pending_question = line[len(INTERVIEWER_PREFIX):].strip()
            elif line.startswith(PARTICIPANT_PREFIX):
                answer = line[len(PARTICIPANT_PREFIX):].strip()
                if answer:
                    pairs.append((pending_question, answer))
                pending_question = ""
    return pairs


def load_raw_data():
    """Reads all raw JSON datasets (including newer scraped wishlist files) and normalizes them into a unified list of dicts."""
    records = []
    seen_ids = set()
    interview_seq = {}

    for source_key, info in DATA_SOURCES.items():
        source_paths = info.get("paths", [])
        source_name = info["name"]

        for file_path in source_paths:
            if not os.path.exists(file_path):
                print(f"Warning: File not found: {file_path}")
                continue

            try:
                if source_key == "user_interviews":
                    stem = os.path.splitext(os.path.basename(file_path))[0]
                    participant = f"Participant {interview_seq.setdefault(stem, len(interview_seq) + 1)}"
                    # The filename carries a millisecond epoch stamp.
                    try:
                        stamp = int(stem.rsplit("-", 1)[-1]) / 1000
                        recorded = datetime.fromtimestamp(stamp).isoformat(timespec="seconds")
                    except (ValueError, OverflowError, OSError):
                        recorded = ""
                    for turn_index, (question, answer) in enumerate(parse_interview(file_path), start=1):
                        # Deterministic id: keeps the CSV stable across re-runs.
                        rec_id = f"interview_{stem}_{turn_index}"
                        if rec_id in seen_ids:
                            continue
                        seen_ids.add(rec_id)
                        text = f"Q: {question}\nA: {answer}" if question else answer
                        records.append({
                            "id": rec_id,
                            "source_key": source_key,
                            "source_name": source_name,
                            "platform": "User Interview",
                            "author": participant,
                            "rating": "N/A",
                            "date": recorded,
                            "url": "",
                            "text": text
                        })
                    continue

                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if source_key == "user_interviews":
                    # Handled before the JSON decode below; see the guard above.
                    pass

                elif source_key == "community_discussions":
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


# --- Cleaning rules applied after normalization -------------------------------

# Sources scraped by broad keyword search, so they can contain whole threads
# that have nothing to do with Nykaa. Review sources (app stores, Trustpilot,
# Mouthshut, Nykaa's own YouTube channel) are on-topic by construction and are
# exempt from the relevance filter.
THREAD_SOURCES = {"reddit_data", "social_media", "youtube_data"}

RELEVANCE_PATTERN = re.compile(
    r"nykaa|beauty|makeup|cosmetic|skincare|skin care|lipstick|foundation|serum|"
    r"shampoo|fragrance|perfume|nail|hair|cream|lotion|order|refund|return|deliver|"
    r"shipping|courier|product|app\b|website|customer care|customer support|checkout|"
    r"cart|wishlist|coupon|discount|price|fashion|brand|purchase|buy|bought|seller|"
    r"packaging|damaged|fake|authentic|counterfeit|quality|service|experience|payment|"
    r"invoice|cancel|complaint|review|store|shop",
    re.IGNORECASE,
)

MIN_WORDS = 3


def clean_records(records):
    """Drops exact duplicates, near-empty rows, and off-topic thread chatter.

    Returns (kept_records, stats). Duplicate detection normalizes whitespace and
    case, so the same review scraped twice with different spacing collapses to one.
    """
    kept, seen_text = [], set()
    stats = {"duplicate": 0, "too_short": 0, "off_topic": 0}

    for rec in records:
        text = (rec.get("text") or "").strip()
        normalized = " ".join(text.lower().split())

        if normalized in seen_text:
            stats["duplicate"] += 1
            continue
        if len(text.split()) < MIN_WORDS:
            stats["too_short"] += 1
            continue
        if rec["source_key"] in THREAD_SOURCES and not RELEVANCE_PATTERN.search(normalized):
            stats["off_topic"] += 1
            continue

        seen_text.add(normalized)
        kept.append(rec)

    return kept, stats


def process_and_save():
    """Runs data preprocessing, outputs unified CSV, and builds ChromaDB vector store."""
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(VECTOR_DB_DIR, exist_ok=True)

    print(f"Loading raw feedback from {len(DATA_SOURCES)} sources...")
    records = load_raw_data()
    print(f"Successfully normalized {len(records)} feedback records.")

    records, drop_stats = clean_records(records)
    print(
        "Cleaning: dropped {duplicate} duplicates, {too_short} near-empty, "
        "{off_topic} off-topic.".format(**drop_stats)
    )
    print(f"Retained {len(records)} records after cleaning.")

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

        # Shared with rag_engine via embeddings.py so the two cannot diverge.
        from embeddings import embedder_id, get_embedding_function

        sentence_transformer_ef = get_embedding_function()
        active_embedder = embedder_id()
        print(f"Embedding model: {active_embedder}")

        # Get or create collection
        # Changing embedder changes vector dimensionality, so the old collection
        # cannot be reused -- drop and rebuild rather than fail on a dim mismatch.
        try:
            existing = chroma_client.get_collection(name="user_feedback")
            if (existing.metadata or {}).get("embedder_id") != active_embedder:
                print("Embedder changed; dropping the old collection.")
                chroma_client.delete_collection(name="user_feedback")
        except Exception:
            pass

        collection = chroma_client.get_or_create_collection(
            name="user_feedback",
            embedding_function=sentence_transformer_ef,
            metadata={"embedder_id": active_embedder},
        )

        # Reset/re-populate
        existing_ids = collection.get()["ids"]
        if existing_ids:
            print(f"Clearing {len(existing_ids)} existing vector entries...")
            collection.delete(ids=existing_ids)

        print("Indexing documents into ChromaDB...")
        batch_size = 100  # each batch is an embedding API call
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

        # Dropping a collection leaves its HNSW directory behind. These are
        # committed to the repo, so prune anything no longer referenced by a
        # live segment rather than carrying dead megabytes forever.
        try:
            import shutil
            import sqlite3

            db = sqlite3.connect(os.path.join(VECTOR_DB_DIR, "chroma.sqlite3"))
            live = {row[0] for row in db.execute("select id from segments")}
            db.close()
            for entry in os.listdir(VECTOR_DB_DIR):
                path = os.path.join(VECTOR_DB_DIR, entry)
                if os.path.isdir(path) and entry not in live:
                    shutil.rmtree(path)
                    print(f"Pruned orphaned index directory: {entry}")
        except Exception as e:
            print(f"Index cleanup skipped: {e}")
    except Exception as e:
        print(f"ChromaDB indexing warning: {e}")

    return csv_path


if __name__ == "__main__":
    process_and_save()
