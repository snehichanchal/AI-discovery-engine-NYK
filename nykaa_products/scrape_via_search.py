import requests
import json
import time
import re
import random

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
            
            # We only want nykaafashion product links
            if "nykaafashion.com/p/" not in url and "-pr-" not in url:
                continue

            # Extract title
            title_match = re.search(r'class="result__title">.*?<a[^>]+>(.*?)</a>', block, re.DOTALL)
            title = title_match.group(1) if title_match else ""
            title = re.sub(r'<[^>]+>', '', title).strip() # Strip HTML tags
            
            # Extract snippet
            snippet_match = re.search(r'class="result__snippet[^>]+>(.*?)</a>', block, re.DOTALL)
            snippet = snippet_match.group(1) if snippet_match else ""
            snippet = re.sub(r'<[^>]+>', '', snippet).strip() # Strip HTML tags
            
            if url and (title or snippet):
                # Try to extract price or rating from snippet if search engine indexed it
                price_match = re.search(r'(₹|Rs\.?)\s?(\d+[,.]?\d*)', snippet)
                price = price_match.group(0) if price_match else "N/A"
                
                results.append({
                    "title": title,
                    "url": url,
                    "description_and_reviews_snippet": snippet,
                    "price": price
                })
        except Exception as e:
            continue
    return results

def scrape_nykaa_via_ddg():
    print("Scraping Nykaa Fashion products via DuckDuckGo Cache...")
    products = []
    seen_urls = set()
    
    # Diverse queries to get 100 different products
    queries = [
        "site:nykaafashion.com/p/ saree reviews",
        "site:nykaafashion.com/p/ dress price",
        "site:nykaafashion.com/p/ shoes rating",
        "site:nykaafashion.com/p/ lipstick",
        "site:nykaafashion.com/p/ watch",
        "site:nykaafashion.com/p/ kurta set",
        "site:nykaafashion.com/p/ bag reviews",
        "site:nykaafashion.com/p/ heels",
        "site:nykaafashion.com/p/ tops",
        "site:nykaafashion.com/p/ jeans",
        "site:nykaafashion.com/p/ activewear",
        "site:nykaafashion.com/p/ lingerie",
        "site:nykaafashion.com/p/ jewelry",
        "site:nykaafashion.com/p/ menswear"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for query in queries:
        print(f"Searching DDG for: {query}")
        try:
            res = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=15)
            if res.status_code == 200:
                results = parse_ddg_html(res.text)
                for r in results:
                    url = r['url']
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    products.append(r)
            else:
                print(f"\n[ACTION REQUIRED] DDG returned status {res.status_code} (Anti-Bot Challenge).")
                print("Please open your web browser, navigate to https://duckduckgo.com, do a random search, and solve any CAPTCHAs.")
                input("Once you have proved you are human, press Enter to continue scraping...")
                # Retry the same query after they press Enter
                print("Retrying query...")
                res = requests.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers, timeout=15)
                if res.status_code == 200:
                    results = parse_ddg_html(res.text)
                    for r in results:
                        url = r['url']
                        if url not in seen_urls:
                            seen_urls.add(url)
                            products.append(r)
                
        except Exception as e:
            print(f"Error on {query}: {e}")
            
        time.sleep(3) # Polite delay
        
        if len(products) >= 100:
            break
            
    # Cap at 100 random products
    random.shuffle(products)
    products = products[:100]
    
    return products

def main():
    print("Starting search engine fallback scraper for Nykaa Fashion products...")
    all_products = scrape_nykaa_via_ddg()
    
    if all_products:
        print("-" * 50)
        print(f"Successfully collected {len(all_products)} products via search engine cache.")
        
        # Save to JSON
        json_filename = 'nykaa_products.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(all_products, f, indent=4, ensure_ascii=False)
        print(f"Data saved to {json_filename}")
    else:
        print("No products found or scraping failed.")

if __name__ == "__main__":
    main()
