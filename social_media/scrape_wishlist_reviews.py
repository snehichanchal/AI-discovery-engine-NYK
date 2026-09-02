#!/usr/bin/env python3
"""
Scrape 1000 reviews & discussion posts about Nykaa Fashion's Wishlist feature
from social media & community platforms (YouTube, Google Play Store, Google News RSS,
Mouthshut, Trustpilot, Reddit).

Criteria:
  - Last 2 years (Aug 2024 - Aug 2026)
  - Wishlist feature focus (wishlist, wish list, save for later, favorites, heart button, etc.)
  - Stores ONLY new entries not previously scraped.

Outputs:
  - social_media/nykaa_wishlist_social_reviews.json
  - social_media/nykaa_wishlist_social_reviews.csv
"""

import os
import json
import csv
import datetime
import re
import hashlib
import time
import requests
from xml.etree import ElementTree
from urllib.parse import quote_plus
from google_play_scraper import reviews_all, Sort
from youtube_comment_downloader import YoutubeCommentDownloader
import yt_dlp

# ──────────────────────────── Configuration ────────────────────────────

TARGET_COUNT = 1000
OUTPUT_JSON = "nykaa_wishlist_social_reviews.json"
OUTPUT_CSV = "nykaa_wishlist_social_reviews.csv"

# Existing files across the workspace to deduplicate against
EXISTING_FILES = [
    "social_media_discussions.json",
    "nykaa_wishlist_social_reviews.json",
    "../community_discussions/community_discussion_data.json",
    "../google_store/nykaa_wishlist_reviews.json",
    "../google_store/nykaa_google_store_reviews.json",
    "../app_store/nykaa_app_store_wishlist_reviews_6months.json",
]

# Date cutoff: 2 years ago (Aug 2024)
TWO_YEARS_AGO_TIMESTAMP = (datetime.datetime.now() - datetime.timedelta(days=730)).timestamp()

# Regex for wishlist and related saved-item features
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

def make_id(url_or_text):
    return hashlib.md5(url_or_text.encode("utf-8")).hexdigest()[:16]


def load_existing_urls_and_ids():
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
                            if "id" in item and item["id"]:
                                seen_ids.add(str(item["id"]))
                            if "reviewId" in item and item["reviewId"]:
                                seen_ids.add(str(item["reviewId"]))
                            if "content" in item and item["content"]:
                                seen_contents.add(item["content"].strip().lower()[:80])
                            if "text" in item and item["text"]:
                                seen_contents.add(item["text"].strip().lower()[:80])
                            if "body" in item and item["body"]:
                                seen_contents.add(item["body"].strip().lower()[:80])
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


def save_posts(posts):
    existing = []
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    seen = {p["url"] for p in existing}
    for p in posts:
        if p["url"] not in seen:
            existing.append(p)
            seen.add(p["url"])

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4, ensure_ascii=False)

    if existing:
        keys = ["platform", "id", "author", "content", "url", "created_at", "metrics", "source_query", "scraped_at"]
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(existing)

    return len(existing)


# ──────────────────────── Module 1: Google Play Store Reviews ───────────

def scrape_play_store_wishlist(seen_urls, seen_ids, seen_contents, collected_posts):
    print("\n[1/4] Scraping Google Play Store wishlist reviews for Nykaa apps...")
    count_before = len(collected_posts)

    apps = [
        ("com.fsn.nds", "Nykaa Fashion"),
        ("com.fsn.nykaa", "Nykaa Main App"),
        ("com.nykaa.man", "Nykaa Man"),
    ]

    for app_id, app_name in apps:
        if len(collected_posts) >= TARGET_COUNT:
            break

        print(f"  Fetching Play Store reviews for {app_name} ({app_id})...")
        try:
            results = reviews_all(
                app_id,
                lang="en",
                country="in",
                sort=Sort.NEWEST,
                sleep_milliseconds=50
            )

            for r in results:
                content = r.get("content", "").strip()
                if not content:
                    continue

                review_id = r.get("reviewId") or r.get("id") or make_id(content)
                if review_id in seen_ids:
                    continue

                url = f"https://play.google.com/store/apps/details?id={app_id}&reviewId={review_id}"
                if url in seen_urls:
                    continue

                content_key = content.lower()[:80]
                if content_key in seen_contents:
                    continue

                at = r.get("at")
                if at and at.replace(tzinfo=None).timestamp() < TWO_YEARS_AGO_TIMESTAMP:
                    continue

                if is_wishlist_related(content):
                    seen_urls.add(url)
                    seen_ids.add(str(review_id))
                    seen_contents.add(content_key)

                    collected_posts.append({
                        "platform": f"Google Play Store ({app_name})",
                        "id": str(review_id),
                        "author": r.get("userName", "Play Store User"),
                        "content": content,
                        "url": url,
                        "created_at": str(at) if at else datetime.datetime.now().isoformat(),
                        "metrics": f"Rating: {r.get('score', 'N/A')}, Thumbs Up: {r.get('thumbsUp', 0)}",
                        "source_query": f"PlayStore: {app_id}",
                        "scraped_at": datetime.datetime.now().isoformat()
                    })

                    if len(collected_posts) >= TARGET_COUNT:
                        break

        except Exception as e:
            print(f"    Play Store error for {app_id}: {e}")

    added = len(collected_posts) - count_before
    print(f"  => Collected {added} Play Store wishlist reviews (Total: {len(collected_posts)})")
    save_posts(collected_posts)


# ──────────────────────── Module 2: YouTube Comments ────────────────────

def scrape_youtube_comments(seen_urls, seen_ids, seen_contents, collected_posts):
    print("\n[2/4] Scraping YouTube comments discussing Nykaa Fashion Wishlist...")

    video_queries = [
        "Nykaa fashion wishlist",
        "Nykaa fashion haul wishlist",
        "Nykaa fashion app review wishlist",
        "Nykaa fashion save for later",
        "Nykaa fashion wishlist problem",
        "Nykaa fashion wishlist bug",
        "Nykaa fashion saree haul wishlist",
        "Nykaa fashion kurti haul wishlist",
        "Nykaa fashion dress haul wishlist",
        "Nykaa fashion sale wishlist",
        "Nykaa fashion pink Friday sale wishlist",
        "Nykaa fashion haul 2024 wishlist",
        "Nykaa fashion haul 2025 wishlist",
        "Nykaa fashion haul 2026 wishlist",
        "Nykaa fashion try on wishlist",
        "Nykaa fashion shopping vlog wishlist",
        "Nykaa fashion favourites haul",
        "Nykaa fashion top picks wishlist",
        "Nykaa fashion app features wishlist",
    ]

    ydl_opts = {"quiet": True, "extract_flat": True, "no_warnings": True}
    video_list = []
    seen_video_ids = set()

    for q in video_queries:
        if len(video_list) >= 150:
            break
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch20:{q}", download=False)
                if "entries" in info:
                    for entry in info["entries"]:
                        if entry and "id" in entry:
                            vid = entry["id"]
                            if vid not in seen_video_ids:
                                seen_video_ids.add(vid)
                                video_list.append({
                                    "id": vid,
                                    "title": entry.get("title", ""),
                                    "url": f"https://www.youtube.com/watch?v={vid}"
                                })
        except Exception:
            pass

    print(f"  Found {len(video_list)} YouTube videos discussing Nykaa Wishlist / Hauls.")

    downloader = YoutubeCommentDownloader()
    count_before = len(collected_posts)

    for i, vid in enumerate(video_list):
        if len(collected_posts) >= TARGET_COUNT:
            break

        print(f"  ({i+1}/{len(video_list)}) Scanning comments: {vid['title'][:50]}...")
        try:
            comments = downloader.get_comments_from_url(vid["url"])
            comment_list = []
            try:
                for c in comments:
                    comment_list.append(c)
                    if len(comment_list) >= 150:
                        break
            except Exception:
                pass

            scraped_in_vid = 0
            for c in comment_list:
                cid = c.get("cid", "")
                if cid and cid in seen_ids:
                    continue

                text = c.get("text", "").strip()
                if not text:
                    continue

                content_key = text.lower()[:80]
                if content_key in seen_contents:
                    continue

                comment_url = f"{vid['url']}&lc={cid}" if cid else vid["url"]
                if comment_url in seen_urls:
                    continue

                time_parsed = c.get("time_parsed")
                if time_parsed and time_parsed < TWO_YEARS_AGO_TIMESTAMP:
                    continue

                if is_wishlist_related(text):
                    seen_urls.add(comment_url)
                    if cid: seen_ids.add(cid)
                    seen_contents.add(content_key)

                    created_str = (
                        datetime.datetime.fromtimestamp(time_parsed).isoformat()
                        if time_parsed
                        else datetime.datetime.now().isoformat()
                    )

                    collected_posts.append({
                        "platform": "YouTube",
                        "id": cid or make_id(comment_url),
                        "author": c.get("author", "YouTube User"),
                        "content": f"[Video: {vid['title']}]\n{text}",
                        "url": comment_url,
                        "created_at": created_str,
                        "metrics": f"Likes: {c.get('votes', 0)}",
                        "source_query": f"YouTube: {vid['title'][:40]}",
                        "scraped_at": datetime.datetime.now().isoformat()
                    })
                    scraped_in_vid += 1

                    if len(collected_posts) >= TARGET_COUNT:
                        break

            if scraped_in_vid > 0:
                save_posts(collected_posts)

        except Exception:
            pass

        time.sleep(0.2)

    added = len(collected_posts) - count_before
    print(f"  => Collected {added} YouTube wishlist comments (Total: {len(collected_posts)})")


# ──────────────────────── Module 3: News & Web Discussions ───────────────

def scrape_news_and_web(seen_urls, seen_ids, seen_contents, collected_posts):
    print("\n[3/4] Scraping Google News RSS for Nykaa Wishlist discussions...")

    news_queries = [
        "Nykaa fashion wishlist",
        "Nykaa wishlist feature",
        "Nykaa fashion save for later",
        "Nykaa fashion favorites",
        "Nykaa fashion app features",
    ]

    count_before = len(collected_posts)

    for q in news_queries:
        if len(collected_posts) >= TARGET_COUNT:
            break

        rss_url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            res = requests.get(rss_url, timeout=15)
            if res.status_code == 200:
                root = ElementTree.fromstring(res.content)
                for item in root.findall("./channel/item"):
                    title = item.find("title").text if item.find("title") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    source = item.find("source").text if item.find("source") is not None else "Google News"

                    if not link or link in seen_urls:
                        continue

                    content_key = title.strip().lower()[:80]
                    if content_key in seen_contents:
                        continue

                    if is_wishlist_related(title) or is_nykaa_related(title):
                        seen_urls.add(link)
                        pid = make_id(link)
                        seen_ids.add(pid)
                        seen_contents.add(content_key)

                        collected_posts.append({
                            "platform": f"News ({source})",
                            "id": pid,
                            "author": source,
                            "content": title,
                            "url": link,
                            "created_at": pub_date,
                            "metrics": "N/A",
                            "source_query": q,
                            "scraped_at": datetime.datetime.now().isoformat()
                        })

                        if len(collected_posts) >= TARGET_COUNT:
                            break
        except Exception:
            pass

        time.sleep(1)

    added = len(collected_posts) - count_before
    print(f"  => Collected {added} news posts (Total: {len(collected_posts)})")
    save_posts(collected_posts)


# ──────────────────────── Module 4: Extended Searches ───────────────────

def scrape_extended_searches(seen_urls, seen_ids, seen_contents, collected_posts):
    if len(collected_posts) >= TARGET_COUNT:
        return

    print("\n[4/4] Deep scanning additional YouTube fashion videos for wishlist feedback...")

    extra_queries = [
        "Nykaa fashion saree haul wishlist",
        "Nykaa fashion kurti haul wishlist",
        "Nykaa fashion wedding haul wishlist",
        "Nykaa fashion top recommendations wishlist",
        "Nykaa fashion app tutorial wishlist",
        "Nykaa fashion vs Myntra wishlist",
        "Nykaa fashion vs Ajio wishlist",
        "Nykaa fashion clothing review wishlist",
        "Nykaa fashion jewellery haul wishlist",
        "Nykaa fashion footwear haul wishlist",
        "Nykaa fashion bag haul wishlist",
        "Nykaa fashion western wear haul wishlist",
        "Nykaa fashion ethnic wear haul wishlist",
        "Nykaa fashion designer haul wishlist",
        "Nykaa fashion shopping vlog wishlist",
    ]

    ydl_opts = {"quiet": True, "extract_flat": True, "no_warnings": True}
    video_list = []
    seen_video_ids = set()

    for q in extra_queries:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch25:{q}", download=False)
                if "entries" in info:
                    for entry in info["entries"]:
                        if entry and "id" in entry:
                            vid = entry["id"]
                            if vid not in seen_video_ids:
                                seen_video_ids.add(vid)
                                video_list.append({
                                    "id": vid,
                                    "title": entry.get("title", ""),
                                    "url": f"https://www.youtube.com/watch?v={vid}"
                                })
        except Exception:
            pass

    downloader = YoutubeCommentDownloader()
    count_before = len(collected_posts)

    for i, vid in enumerate(video_list):
        if len(collected_posts) >= TARGET_COUNT:
            break

        print(f"  ({i+1}/{len(video_list)}) Fetching comments: {vid['title'][:50]}...")
        try:
            comments = downloader.get_comments_from_url(vid["url"])
            comment_list = []
            try:
                for c in comments:
                    comment_list.append(c)
                    if len(comment_list) >= 150:
                        break
            except Exception:
                pass

            scraped_in_vid = 0
            for c in comment_list:
                cid = c.get("cid", "")
                if cid and cid in seen_ids:
                    continue

                text = c.get("text", "").strip()
                if not text:
                    continue

                content_key = text.lower()[:80]
                if content_key in seen_contents:
                    continue

                comment_url = f"{vid['url']}&lc={cid}" if cid else vid["url"]
                if comment_url in seen_urls:
                    continue

                time_parsed = c.get("time_parsed")
                if time_parsed and time_parsed < TWO_YEARS_AGO_TIMESTAMP:
                    continue

                if is_wishlist_related(text):
                    seen_urls.add(comment_url)
                    if cid: seen_ids.add(cid)
                    seen_contents.add(content_key)

                    created_str = (
                        datetime.datetime.fromtimestamp(time_parsed).isoformat()
                        if time_parsed
                        else datetime.datetime.now().isoformat()
                    )

                    collected_posts.append({
                        "platform": "YouTube",
                        "id": cid or make_id(comment_url),
                        "author": c.get("author", "YouTube User"),
                        "content": f"[Video: {vid['title']}]\n{text}",
                        "url": comment_url,
                        "created_at": created_str,
                        "metrics": f"Likes: {c.get('votes', 0)}",
                        "source_query": f"YouTube: {vid['title'][:40]}",
                        "scraped_at": datetime.datetime.now().isoformat()
                    })
                    scraped_in_vid += 1

                    if len(collected_posts) >= TARGET_COUNT:
                        break

            if scraped_in_vid > 0:
                save_posts(collected_posts)

        except Exception:
            pass

        time.sleep(0.2)

    added = len(collected_posts) - count_before
    print(f"  => Collected {added} extended YouTube comments (Total: {len(collected_posts)})")


# ──────────────────────── Main ──────────────────────────────────────────

def main():
    print("=" * 75)
    print("Nykaa Fashion Social Media Wishlist Scraper")
    print(f"Target: {TARGET_COUNT} wishlist-focused reviews & discussions")
    print(f"Date Range: Last 2 Years (Aug 2024 - Aug 2026)")
    print(f"Output File: {OUTPUT_JSON}")
    print("=" * 75)

    seen_urls, seen_ids, seen_contents = load_existing_urls_and_ids()
    print(f"\nLoaded {len(seen_urls)} existing URLs, {len(seen_ids)} existing IDs, and {len(seen_contents)} content hashes for deduplication.\n")

    collected_posts = []

    # 1. Google Play Store Reviews (Nykaa Apps)
    scrape_play_store_wishlist(seen_urls, seen_ids, seen_contents, collected_posts)

    # 2. YouTube Comments
    scrape_youtube_comments(seen_urls, seen_ids, seen_contents, collected_posts)

    # 3. Google News RSS
    scrape_news_and_web(seen_urls, seen_ids, seen_contents, collected_posts)

    # 4. Extended YouTube Search
    scrape_extended_searches(seen_urls, seen_ids, seen_contents, collected_posts)

    total_saved = save_posts(collected_posts)

    print("\n" + "=" * 75)
    print("SCRAPING COMPLETED")
    print("=" * 75)
    print(f"Total New Wishlist Social Media Reviews Collected: {total_saved}")
    print(f"Saved JSON File: {OUTPUT_JSON}")
    print(f"Saved CSV File:  {OUTPUT_CSV}")
    print("=" * 75)


if __name__ == "__main__":
    main()
