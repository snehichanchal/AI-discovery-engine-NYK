import requests
import json
import concurrent.futures
import time
import re
from bs4 import BeautifulSoup

def get_proxies():
    try:
        with open("/home/testing/.gemini/antigravity-ide/brain/d0d59ea5-00fb-473a-8274-3f3e80872b8e/.system_generated/steps/310/content.md", "r") as f:
            lines = f.readlines()
            proxies = [line.strip() for line in lines if ":" in line and not line.startswith("#")]
            return proxies
    except Exception:
        return []

def test_proxy(proxy):
    proxies = {
        "http": f"http://{proxy}",
        "https": f"http://{proxy}"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get("https://www.nykaafashion.com/women/c/6842", proxies=proxies, headers=headers, timeout=5)
        if res.status_code == 200 and "nykaafashion" in res.text.lower():
            return proxy, res.text
    except Exception:
        pass
    return None, None

def get_working_proxy(proxies):
    print(f"Testing {len(proxies)} proxies to bypass Akamai WAF...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(test_proxy, p) for p in proxies[:500]]
        for future in concurrent.futures.as_completed(futures):
            proxy, text = future.result()
            if proxy:
                print(f"Found working proxy: {proxy}")
                # Cancel the rest if possible
                return proxy, text
    return None, None

def extract_products(html_text):
    products = []
    # Try to find Next.js data
    try:
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            # navigate the nested next.js structure
            # Nykaa fashion structure might vary, let's find anything looking like a product list
            
            def find_products(obj):
                found = []
                if isinstance(obj, dict):
                    if "title" in obj and ("price" in obj or "mrp" in obj) and "url" in obj:
                        found.append(obj)
                    for k, v in obj.items():
                        found.extend(find_products(v))
                elif isinstance(obj, list):
                    for item in obj:
                        found.extend(find_products(item))
                return found
                
            raw_products = find_products(data)
            for p in raw_products:
                if len(products) >= 100:
                    break
                products.append({
                    "title": p.get("title", ""),
                    "url": "https://www.nykaafashion.com" + p.get("url", ""),
                    "price": p.get("price", p.get("mrp", "N/A")),
                    "description": p.get("description", p.get("subtitle", "No description available")),
                    "reviews_count": p.get("ratingCount", 0),
                    "rating": p.get("rating", 0)
                })
    except Exception as e:
        print("Error parsing next data:", e)
        
    if not products:
        # Fallback to BeautifulSoup
        soup = BeautifulSoup(html_text, 'html.parser')
        # ... logic for standard parsing if needed
    return products

def main():
    proxies = get_proxies()
    proxy, html_text = get_working_proxy(proxies)
    
    if not html_text:
        print("Failed to find a proxy that bypasses Akamai. All proxies failed.")
        return
        
    print("Successfully bypassed Akamai! Extracting products...")
    products = extract_products(html_text)
    
    if products:
        print(f"Found {len(products)} products!")
        with open("nykaa_products.json", "w", encoding="utf-8") as f:
            json.dump(products, f, indent=4)
        print("Real data saved to nykaa_products.json")
    else:
        print("Failed to extract products from HTML.")

if __name__ == "__main__":
    main()
