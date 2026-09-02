#!/usr/bin/env python3
"""
Scrape YouTube comments & video discussions from the last 1 year (Aug 2025 - Aug 2026)
about Nykaa Fashion products, specifically focusing on the Wishlist feature
(wishlisting products, saved items, wishlist hauls, price drops, post-wishlisting feedback).

Stores only NEW data not already scraped in previous files.

Outputs:
  - youtube_nykaa/nykaa_youtube_wishlist_comments.json
  - youtube_nykaa/nykaa_youtube_wishlist_comments.csv
"""

import os
import json
import csv
import datetime
import re
import hashlib
import time
import concurrent.futures
from itertools import islice
import yt_dlp
from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT

# ──────────────────────────── Configuration ────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

OUTPUT_JSON = os.path.join(SCRIPT_DIR, "nykaa_youtube_wishlist_comments.json")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "nykaa_youtube_wishlist_comments.csv")

# Existing data files across workspace to deduplicate against
EXISTING_FILES = [
    os.path.join(SCRIPT_DIR, "nykaa_youtube_comments.json"),
    OUTPUT_JSON,
    os.path.join(PROJECT_DIR, "youtube_data", "youtube_comments.json"),
    os.path.join(PROJECT_DIR, "social_media", "social_media_discussions.json"),
    os.path.join(PROJECT_DIR, "social_media", "nykaa_wishlist_social_reviews.json"),
    os.path.join(PROJECT_DIR, "google_store", "nykaa_wishlist_reviews.json"),
    os.path.join(PROJECT_DIR, "app_store", "nykaa_app_store_wishlist_reviews_6months.json"),
    os.path.join(PROJECT_DIR, "community_discussions", "community_discussion_data.json"),
]

# Date Cutoff: Last 1 Year (365 days ago)
ONE_YEAR_AGO_TIMESTAMP = (datetime.datetime.now() - datetime.timedelta(days=365)).timestamp()

# Regex for Wishlist and related saved-item features
WISHLIST_REGEX = re.compile(
    r"\b(wishlist|wish-list|wish\s+list|wishlisted|wishlisting|save\s+for\s+later"
    r"|saved\s+items|saved\s+products|save\s+item|save\s+product|favorite|favourites|favourite|favorites"
    r"|bookmark|bookmarked|heart\s+button|like\s+button|shortlist|shortlisted|save\s+button"
    r"|saved\s+list|buy\s+later|add\s+to\s+wishlist|wishlist\s+feature|wishlist\s+bug"
    r"|wishlist\s+empty|wishlist\s+gone|wishlist\s+disappeared|wishlist\s+issue|wishlist\s+option)\b",
    re.IGNORECASE
)

NYKAA_REGEX = re.compile(r"\bnykaa\b", re.IGNORECASE)


# ──────────────────────────── Helpers ──────────────────────────────────

def make_id(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def load_existing_signatures():
    seen_urls = set()
    seen_ids = set()
    seen_contents = set()

    for path in EXISTING_FILES:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        if isinstance(item, dict):
                            if "url" in item and item["url"]:
                                seen_urls.add(item["url"])
                            if "video_url" in item and item["video_url"]:
                                seen_urls.add(item["video_url"])
                            if "id" in item and item["id"]:
                                seen_ids.add(str(item["id"]))
                            if "comment_id" in item and item["comment_id"]:
                                seen_ids.add(str(item["comment_id"]))
                            if "content" in item and item["content"]:
                                seen_contents.add(item["content"].strip().lower()[:80])
                            if "text" in item and item["text"]:
                                seen_contents.add(item["text"].strip().lower()[:80])
            except Exception as e:
                print(f"Note: Could not load {path}: {e}")

    return seen_urls, seen_ids, seen_contents


def is_wishlist_related(text):
    if not text:
        return False
    return bool(WISHLIST_REGEX.search(text))


def is_nykaa_related(text):
    if not text:
        return False
    return bool(NYKAA_REGEX.search(text))


def save_comments(comments):
    existing = []
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    seen = {c.get("comment_id") or c.get("id") or c.get("url") for c in existing}
    for c in comments:
        identifier = c.get("comment_id") or c.get("id") or c.get("url")
        if identifier not in seen:
            existing.append(c)
            seen.add(identifier)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4, ensure_ascii=False)

    if existing:
        keys = [
            "platform", "id", "comment_id", "author", "video_title", "video_url",
            "content", "likes", "time_parsed", "created_at", "video_transcript", "scraped_at"
        ]
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(existing)

    return len(existing)


def fetch_comments_for_video(vid, downloader, seen_urls, seen_ids, seen_contents):
    results = []
    video_url = vid["url"]
    video_title = vid["title"]
    video_is_wishlist = is_wishlist_related(video_title)

    def _get():
        c_list = []
        try:
            gen = downloader.get_comments_from_url(video_url, sort_by=SORT_BY_RECENT)
            for c in gen:
                c_list.append(c)
                if len(c_list) >= 200:
                    break
        except Exception:
            pass
        return c_list

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_get)
        try:
            raw_comments = future.result(timeout=6)
        except Exception:
            raw_comments = []

    for comment in raw_comments:
        cid = comment.get("cid", "")
        if cid and cid in seen_ids:
            continue

        text = comment.get("text", "").strip()
        if not text:
            continue

        content_key = text.lower()[:80]
        if content_key in seen_contents:
            continue

        comment_url = f"{video_url}&lc={cid}" if cid else video_url
        if comment_url in seen_urls:
            continue

        time_parsed = comment.get("time_parsed")
        if time_parsed and time_parsed < ONE_YEAR_AGO_TIMESTAMP:
            continue

        is_rel = is_wishlist_related(text)
        if not is_rel and video_is_wishlist:
            if len(text) >= 10:
                is_rel = True

        if is_rel:
            created_str = (
                datetime.datetime.fromtimestamp(time_parsed).isoformat()
                if time_parsed
                else datetime.datetime.now().isoformat()
            )

            results.append({
                "platform": "YouTube",
                "id": cid or make_id(comment_url),
                "comment_id": cid or make_id(comment_url),
                "author": comment.get("author", "Unknown"),
                "video_title": video_title,
                "video_url": video_url,
                "content": text,
                "likes": comment.get("votes", 0),
                "time_parsed": time_parsed,
                "created_at": created_str,
                "video_transcript": "Transcript not available",
                "scraped_at": datetime.datetime.now().isoformat()
            })

    return results


# ──────────────────────── Search & Scrape Engine ────────────────────────

def get_channel_and_search_videos():
    search_queries = [
        "Nykaa fashion wishlist 2025",
        "Nykaa fashion wishlist 2026",
        "Nykaa fashion save for later",
        "Nykaa wishlist haul 2025",
        "Nykaa wishlist haul 2026",
        "Nykaa fashion wishlisted products",
        "Nykaa fashion wishlist items try on",
        "Nykaa fashion wishlist bug empty",
        "Nykaa fashion saved items",
        "Nykaa fashion wishlist outfit review",
        "Nykaa wishlist sale price drop",
        "Nykaa fashion wishlist recommendations",
        "Nykaa fashion saree wishlist haul",
        "Nykaa fashion kurti wishlist haul",
        "Nykaa fashion dress wishlist haul",
        "Nykaa fashion shopping vlog wishlist",
        "Nykaa fashion app features wishlist",
    ]

    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "no_warnings": True,
    }

    video_list = []
    seen_video_ids = set()

    for q in search_queries:
        print(f"Searching YouTube for query: '{q}'...")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch35:{q}", download=False)
                if "entries" in info:
                    for entry in info["entries"]:
                        if entry and "id" in entry:
                            vid = entry["id"]
                            if vid not in seen_video_ids:
                                seen_video_ids.add(vid)
                                video_list.append({
                                    "id": vid,
                                    "title": entry.get("title", "Unknown Title"),
                                    "url": f"https://www.youtube.com/watch?v={vid}"
                                })
        except Exception as e:
            print(f"Note: Search error for '{q}': {e}")

    print(f"Found total {len(video_list)} unique YouTube videos/shorts to scan.")
    return video_list


def scrape_youtube_wishlist_comments():
    print("=" * 75)
    print("Nykaa Fashion YouTube Wishlist Scraper (Last 1 Year)")
    print(f"Output JSON: {OUTPUT_JSON}")
    print(f"Date Cutoff: Last 1 Year (since {datetime.datetime.fromtimestamp(ONE_YEAR_AGO_TIMESTAMP).strftime('%Y-%m-%d')})")
    print("=" * 75)

    seen_urls, seen_ids, seen_contents = load_existing_signatures()
    print(f"Loaded {len(seen_urls)} seen URLs, {len(seen_ids)} seen IDs, {len(seen_contents)} content hashes for deduplication.")

    videos = get_channel_and_search_videos()
    downloader = YoutubeCommentDownloader()

    collected = []

    print(f"\nStarting parallel scan across {len(videos)} videos with 6 workers...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_vid = {
            executor.submit(fetch_comments_for_video, vid, downloader, seen_urls, seen_ids, seen_contents): vid
            for vid in videos
        }

        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_vid):
            completed_count += 1
            vid = future_to_vid[future]
            try:
                comments = future.result()
                if comments:
                    for c in comments:
                        identifier = c.get("comment_id") or c.get("id")
                        content_key = c.get("content", "").strip().lower()[:80]
                        seen_ids.add(identifier)
                        seen_contents.add(content_key)
                        seen_urls.add(c["video_url"])
                    collected.extend(comments)
                    print(f"[{completed_count}/{len(videos)}] + {len(comments)} comments from: {vid['title'][:50]}")
                    save_comments(collected)
                else:
                    if completed_count % 25 == 0:
                        print(f"[{completed_count}/{len(videos)}] Scanned {completed_count} videos...")
            except Exception as e:
                pass

    total_saved = save_comments(collected)
    print("\n" + "=" * 75)
    print(f"SUCCESS: Collected and saved {total_saved} wishlist comments from YouTube (last 1 year).")
    print(f"JSON Output: {OUTPUT_JSON}")
    print(f"CSV Output:  {OUTPUT_CSV}")
    print("=" * 75)


if __name__ == "__main__":
    scrape_youtube_wishlist_comments()
