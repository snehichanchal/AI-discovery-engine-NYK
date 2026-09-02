import requests
import json
import csv
import datetime
import time

def scrape_community_discussions(query="Nykaa fashion", limit=100):
    # List of Indian fashion, beauty, and shopping communities on Reddit
    communities = [
        "IndianFashionAddicts",
        "InstaCelebsGossip",
        "IndianMakeupAddicts",
        "IndianSkincareAddicts",
        "TwoXIndia",
        "BeautyGuruChatter"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    all_discussions = []
    
    print(f"Searching for the latest {limit} discussions about '{query}' across multiple communities...\n")
    
    for community in communities:
        url = f"https://www.reddit.com/r/{community}/search.json"
        params = {
            "q": query,
            "restrict_sr": 1, # Restrict search to the specific subreddit
            "sort": "new",    # Get the latest posts
            "limit": limit    # Fetch up to 'limit' to ensure we have enough to sort globally
        }
        
        print(f"Fetching from r/{community}...")
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            children = data.get('data', {}).get('children', [])
            
            for child in children:
                post = child['data']
                all_discussions.append({
                    'community': f"r/{community}",
                    'title': post.get('title'),
                    'author': post.get('author'),
                    'score': post.get('score'),
                    'num_comments': post.get('num_comments'),
                    'url': f"https://www.reddit.com{post.get('permalink')}" if post.get('permalink') else post.get('url'),
                    'created_utc': post.get('created_utc', 0),
                    'created_at': datetime.datetime.fromtimestamp(post.get('created_utc')).strftime('%Y-%m-%d %H:%M:%S') if post.get('created_utc') else None,
                    'content': post.get('selftext', '')[:500] + '...' if len(post.get('selftext', '')) > 500 else post.get('selftext', '')
                })
            
            # Avoid rate limits by sleeping briefly between requests
            time.sleep(1.5)
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from r/{community}: {e}")
            if 'response' in locals() and hasattr(response, 'status_code') and response.status_code == 429:
                print("Rate limited by Reddit API. Try again later.")
    
    # Sort all gathered discussions globally by created time (newest first)
    all_discussions.sort(key=lambda x: x.get('created_utc', 0), reverse=True)
    
    # Slice to keep exactly the top `limit` globally latest discussions
    latest_discussions = all_discussions[:limit]
    
    # Clean up the temporary sorting key
    for discussion in latest_discussions:
        discussion.pop('created_utc', None)
        
    return latest_discussions

if __name__ == "__main__":
    target_limit = 100
    discussions = scrape_community_discussions(query="Nykaa fashion", limit=target_limit)
    
    if discussions:
        print(f"\nSuccessfully compiled the {len(discussions)} latest discussions.")
        
        # Save to JSON
        json_filename = 'latest_community_discussions.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(discussions, f, indent=4, ensure_ascii=False)
        print(f"Data saved to JSON: {json_filename}")
        
        # Save to CSV
        csv_filename = 'latest_community_discussions.csv'
        keys = discussions[0].keys()
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(discussions)
        print(f"Data saved to CSV: {csv_filename}")
    else:
        print("\nNo discussions found or scraping failed.")
