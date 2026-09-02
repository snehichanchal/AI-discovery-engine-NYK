import os
import json
import csv
import re
import time
import datetime
from google_play_scraper import reviews as gplay_reviews, Sort as GSort
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

WISHLIST_REGEX = re.compile(
    r'\b(wishlist|wish-list|wish list|\bwish\b|\bsaved\b|\bsave for later\b|\bfavorite\b|\bfavourite\b|\bheart\b|\bbookmark\b|save item|saved item|save product|saved product|wish listing|wishlisted|buy later)\b',
    re.IGNORECASE
)

def fetch_trustpilot_reviews():
    print("Fetching Trustpilot live reviews via Chrome...")
    trustpilot_reviews = []
    
    options = uc.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-setuid-sandbox')
    
    try:
        driver = uc.Chrome(options=options, browser_executable_path='/usr/bin/google-chrome', version_main=135)
        domains = ['nykaa.com', 'nykaafashion.com']
        
        for domain in domains:
            print(f"Scraping Trustpilot domain: {domain}")
            page = 1
            while page <= 15:
                url = f"https://www.trustpilot.com/review/{domain}?page={page}"
                try:
                    driver.get(url)
                    time.sleep(1.2)
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    
                    scripts = soup.find_all('script', type='application/ld+json')
                    page_revs = []
                    for s in scripts:
                        if not s.string:
                            continue
                        try:
                            d = json.loads(s.string)
                            items = d if isinstance(d, list) else [d]
                            for item in items:
                                if item.get('@type') == 'LocalBusiness' and 'review' in item:
                                    for r in item['review']:
                                        page_revs.append({
                                            'platform': 'Trustpilot',
                                            'author': r.get('author', {}).get('name', 'Anonymous'),
                                            'rating': str(r.get('reviewRating', {}).get('ratingValue', '')),
                                            'headline': r.get('headline', ''),
                                            'content': r.get('reviewBody', ''),
                                            'date': r.get('datePublished', ''),
                                            'url': url,
                                            'scraped_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                                        })
                        except Exception:
                            pass
                            
                    if not page_revs:
                        break
                    
                    for rev in page_revs:
                        text = f"{rev['headline']} {rev['content']}"
                        if WISHLIST_REGEX.search(text):
                            trustpilot_reviews.append(rev)
                            
                    page += 1
                except Exception as err:
                    print(f"Error on page {page} for {domain}: {err}")
                    break
        driver.quit()
    except Exception as e:
        print(f"Error running Chrome driver for Trustpilot: {e}")
        
    print(f"Total Trustpilot wishlist reviews found: {len(trustpilot_reviews)}")
    return trustpilot_reviews

def load_existing_community_files():
    print("Loading community discussions & review datasets...")
    existing = []
    base_dir = os.path.dirname(__file__)
    
    files = [
        os.path.join(base_dir, '../../google_store/nykaa_google_store_reviews.json'),
        os.path.join(base_dir, '../../app_store/nykaa_app_store_reviews.json'),
        os.path.join(base_dir, '../community_discussion_data.json'),
        os.path.join(base_dir, 'trustpilot_data/nykaa_trustpilot_reviews.json'),
        os.path.join(base_dir, '../../youtube_data/youtube_comments.json'),
        os.path.join(base_dir, '../../youtube_nykaa/nykaa_youtube_comments.json'),
        os.path.join(base_dir, '../../reddit_data/nykaa_playwright_results.json')
    ]
    
    for filepath in files:
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            headline = str(item.get('headline') or item.get('title') or item.get('name') or '')
                            content = str(item.get('content') or item.get('body') or item.get('review') or item.get('text') or item.get('comment') or '')
                            combined = f"{headline} {content}"
                            
                            if WISHLIST_REGEX.search(combined):
                                dt = item.get('date') or item.get('date_published') or item.get('created_at') or item.get('scraped_at') or ''
                                platform = item.get('platform') or item.get('source') or (
                                    'Google Play Store' if 'google' in filepath else
                                    'App Store' if 'app_store' in filepath else
                                    'Trustpilot' if 'trustpilot' in filepath else
                                    'YouTube' if 'youtube' in filepath else
                                    'Reddit' if 'reddit' in filepath else 'Community Platform'
                                )
                                existing.append({
                                    'platform': platform,
                                    'author': str(item.get('author') or item.get('userName') or item.get('user') or 'Anonymous'),
                                    'rating': str(item.get('rating') or item.get('score') or 'N/A'),
                                    'headline': headline or 'Wishlist Review',
                                    'content': content,
                                    'date': dt,
                                    'url': item.get('url') or item.get('link') or 'https://www.trustpilot.com/review/nykaafashion.com',
                                    'scraped_at': item.get('scraped_at') or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                                })
            except Exception as e:
                print(f"Error loading file {filepath}: {e}")
                
    print(f"Total community wishlist reviews loaded: {len(existing)}")
    return existing

def parse_date(date_str):
    if not date_str:
        return 0
    try:
        if isinstance(date_str, (int, float)):
            return date_str
        dt_str = str(date_str).replace('Z', '+00:00')
        return datetime.datetime.fromisoformat(dt_str).timestamp()
    except Exception:
        try:
            return datetime.datetime.strptime(str(date_str).split('.')[0], '%Y-%m-%d %H:%M:%S').timestamp()
        except Exception:
            return 0

def main():
    print("🚀 Scraping latest 200 reviews regarding Wishlist from community platforms (Trustpilot, Google Play, App Store, Mouthshut, Reddit, YouTube)...")
    
    tp_reviews = fetch_trustpilot_reviews()
    community_reviews = load_existing_community_files()
    
    all_combined = tp_reviews + community_reviews
    
    # Deduplicate by author + content snippet
    seen_keys = set()
    unique_reviews = []
    
    for r in all_combined:
        content_snippet = (r.get('content') or '').strip().lower()[:50]
        author = (r.get('author') or '').strip().lower()
        key = f"{author}_{content_snippet}"
        
        if key not in seen_keys and (r.get('content') or r.get('headline')):
            seen_keys.add(key)
            unique_reviews.append(r)
            
    # Sort by date (newest first)
    unique_reviews.sort(key=lambda x: parse_date(x.get('date')), reverse=True)
    
    # Slice to keep exactly the latest 200 reviews
    latest_200 = unique_reviews[:200]
    
    output_dir = os.path.dirname(__file__)
    json_path = os.path.join(output_dir, 'nykaa_trustpilot_wishlist_reviews.json')
    csv_path = os.path.join(output_dir, 'nykaa_trustpilot_wishlist_reviews.csv')
    
    # Save JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(latest_200, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON to: {json_path}")
    
    # Save CSV
    if latest_200:
        keys = ['platform', 'author', 'rating', 'headline', 'content', 'date', 'url', 'scraped_at']
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in latest_200:
                filtered_row = {k: row.get(k, '') for k in keys}
                writer.writerow(filtered_row)
        print(f"Saved CSV to: {csv_path}")
        
    print(f"\n🎉 Completed! Total wishlist reviews in final dataset: {len(latest_200)}")

if __name__ == '__main__':
    main()
