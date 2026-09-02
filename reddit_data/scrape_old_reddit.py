import requests
import json
import time

# ---------------------------------------------------------
# OPTION 3: Old Reddit API
# ---------------------------------------------------------
# PREREQUISITES:
# 1. Run: pip install requests
# ---------------------------------------------------------

def scrape_with_old_reddit():
    # Hit the old.reddit.com JSON endpoint which sometimes has looser protections
    url = "https://old.reddit.com/search.json"
    
    # Needs a highly specific but obscure User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    params = {
        "q": "Nykaa fashion",
        "limit": 100,
        "sort": "new",
        "type": "link"
    }

    print("Fetching posts from old.reddit.com...")
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        posts = []
        children = data.get('data', {}).get('children', [])
        
        for child in children:
            post = child['data']
            posts.append({
                'title': post.get('title'),
                'author': post.get('author'),
                'subreddit': post.get('subreddit'),
                'score': post.get('score'),
                'url': f"https://www.reddit.com{post.get('permalink')}" if post.get('permalink') else post.get('url'),
            })
            
        print(f"Successfully fetched {len(posts)} posts using Old Reddit.")
        
        with open('nykaa_old_reddit_results.json', 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=4, ensure_ascii=False)
            
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if response.status_code == 403 or response.status_code == 429:
            print("Reddit blocked the request or rate limited it. This method is highly unstable.")
    except json.JSONDecodeError:
        print("Reddit did not return JSON. They likely returned an HTML error page (blocked).")

if __name__ == "__main__":
    scrape_with_old_reddit()
