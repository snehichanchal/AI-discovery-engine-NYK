import requests
import json
import csv
import datetime
import time
from bs4 import BeautifulSoup

def scrape_trustpilot_reviews(domain="nykaafashion.com", pages=5):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    all_reviews = []
    
    print(f"Scraping Trustpilot reviews for {domain}...")
    
    for page in range(1, pages + 1):
        url = f"https://www.trustpilot.com/review/{domain}?page={page}"
        print(f"Fetching page {page}: {url}")
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Trustpilot embeds review data in application/ld+json scripts for SEO
            scripts = soup.find_all('script', type='application/ld+json')
            page_reviews = []
            
            for script in scripts:
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string)
                    # Data can be a list or a dict
                    if isinstance(data, list):
                        for item in data:
                            if item.get('@type') == 'LocalBusiness' and 'review' in item:
                                for review in item['review']:
                                    page_reviews.append(parse_ld_json_review(review))
                    elif isinstance(data, dict):
                        if data.get('@type') == 'LocalBusiness' and 'review' in data:
                            for review in data['review']:
                                page_reviews.append(parse_ld_json_review(review))
                except json.JSONDecodeError:
                    continue
            
            if page_reviews:
                all_reviews.extend(page_reviews)
                print(f"Found {len(page_reviews)} reviews on page {page}.")
            else:
                print(f"No reviews found on page {page}. (May have reached the end or blocked by anti-bot)")
                break
                
            time.sleep(1.5) # Be polite to the server
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page}: {e}")
            break
            
    return all_reviews

def parse_ld_json_review(review):
    return {
        'platform': 'Trustpilot',
        'author': review.get('author', {}).get('name', 'Unknown'),
        'rating': review.get('reviewRating', {}).get('ratingValue'),
        'headline': review.get('headline', ''),
        'content': review.get('reviewBody', ''),
        'date_published': review.get('datePublished', ''),
        'scraped_at': datetime.datetime.now().isoformat()
    }

if __name__ == "__main__":
    # We will scrape the first 5 pages as an example (20 reviews per page -> ~100 reviews)
    reviews = scrape_trustpilot_reviews("nykaafashion.com", pages=5)
    
    if reviews:
        print(f"\nSuccessfully scraped {len(reviews)} reviews.")
        
        # Save to JSON
        json_filename = 'nykaa_trustpilot_reviews.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(reviews, f, indent=4, ensure_ascii=False)
        print(f"Data saved to {json_filename}")
        
        # Save to CSV
        csv_filename = 'nykaa_trustpilot_reviews.csv'
        keys = reviews[0].keys()
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(reviews)
        print(f"Data saved to {csv_filename}")
    else:
        print("\nNo reviews found or scraping failed.")
