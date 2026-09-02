import requests
import json
import csv
import datetime
import time
import re
from xml.etree import ElementTree

def parse_ddg_html(html_text):
    """Simple regex based parser for DuckDuckGo HTML results"""
    results = []
    # Find all result blocks
    blocks = html_text.split('class="result ')
    for block in blocks[1:]:
        try:
            # Extract URL
            url_match = re.search(r'href="([^"]+)"', block)
            url = url_match.group(1) if url_match else ""
            
            # DDG redirects links, decode them
            if "uddg=" in url:
                import urllib.parse
                url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
            
            # Extract title
            title_match = re.search(r'class="result__title">.*?<a[^>]+>(.*?)</a>', block, re.DOTALL)
            title = title_match.group(1) if title_match else ""
            title = re.sub(r'<[^>]+>', '', title).strip() # Strip HTML tags
            
            # Extract snippet
            snippet_match = re.search(r'class="result__snippet[^>]+>(.*?)</a>', block, re.DOTALL)
            snippet = snippet_match.group(1) if snippet_match else ""
            snippet = re.sub(r'<[^>]+>', '', snippet).strip() # Strip HTML tags
            
            if url and (title or snippet):
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet
                })
        except Exception as e:
            continue
    return results

def scrape_social_via_ddg():
    print("Scraping actual discussions using search engine HTML...")
    posts = []
    seen_urls = set()
    
    # 10 queries to hit ~100 unique real results
    queries = [
        "site:reddit.com Nykaa fashion",
        "site:twitter.com Nykaa fashion",
        "site:instagram.com Nykaa fashion",
        "site:quora.com Nykaa fashion",
        "Nykaa fashion haul site:reddit.com",
        "Nykaa fashion sale site:twitter.com",
        "Nykaa fashion review site:quora.com",
        "site:facebook.com Nykaa fashion",
        "site:pinterest.com Nykaa fashion",
        "Nykaa fashion quality site:reddit.com",
        "Nykaa fashion size site:twitter.com"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for query in queries:
        print(f"Searching DDG for: {query}")
        try:
            res = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers)
            if res.status_code == 200:
                results = parse_ddg_html(res.text)
                for r in results:
                    url = r['url']
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    # Detect platform
                    platform = "Web"
                    if "reddit.com" in url: platform = "Reddit"
                    elif "twitter.com" in url or "x.com" in url: platform = "Twitter"
                    elif "quora.com" in url: platform = "Quora"
                    elif "instagram.com" in url: platform = "Instagram"
                    elif "facebook.com" in url: platform = "Facebook"
                    elif "pinterest.com" in url: platform = "Pinterest"
                    
                    posts.append({
                        'platform': platform,
                        'id': url.split('/')[-1][:30] if '/' in url else "unknown",
                        'author': "User", # Author isn't easily parsed from search snippets
                        'content': f"{r['title']} - {r['snippet']}",
                        'url': url,
                        'created_at': datetime.datetime.now().isoformat(),
                        'metrics': "N/A"
                    })
        except Exception as e:
            print(f"Error on {query}: {e}")
            
        time.sleep(2) # Be polite to avoid rate limits
        
    return posts

def scrape_google_news():
    print("Scraping Google News RSS for Nykaa Fashion...")
    posts = []
    url = "https://news.google.com/rss/search?q=Nykaa+fashion&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            root = ElementTree.fromstring(res.content)
            for item in root.findall('./channel/item'):
                title = item.find('title').text
                link = item.find('link').text
                pub_date = item.find('pubDate').text
                source = item.find('source').text if item.find('source') is not None else "Google News"
                
                posts.append({
                    'platform': f"News ({source})",
                    'id': link.split('/')[-1][:30] if '/' in link else "news",
                    'author': source,
                    'content': title,
                    'url': link,
                    'created_at': pub_date,
                    'metrics': "N/A"
                })
    except Exception as e:
        print(f"Error fetching Google News: {e}")
    return posts

def main():
    print("Starting actual social media scraper for 'Nykaa fashion'...")
    all_posts = scrape_social_via_ddg()
    
    # If DDG doesn't yield 100, supplement with Google News which has real discussions/articles
    if len(all_posts) < 100:
        print(f"Only found {len(all_posts)} social media posts. Supplementing with News RSS...")
        news_posts = scrape_google_news()
        all_posts.extend(news_posts)
        
    # Cap at exactly 100
    all_posts = all_posts[:100]
    
    if all_posts:
        print("-" * 50)
        print(f"Successfully collected {len(all_posts)} REAL discussions across platforms.")
        
        # Save to JSON
        json_filename = 'social_media_discussions.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(all_posts, f, indent=4, ensure_ascii=False)
        print(f"Data saved to {json_filename}")
        
        # Save to CSV
        csv_filename = 'social_media_discussions.csv'
        keys = ['platform', 'id', 'author', 'content', 'url', 'created_at', 'metrics']
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(all_posts)
        print(f"Data saved to {csv_filename}")
    else:
        print("No posts found or scraping failed entirely.")

if __name__ == "__main__":
    main()
