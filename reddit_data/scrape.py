import requests
import json
import csv
import datetime

def scrape_reddit_posts(query="Nykaa fashion", limit=100):
    url = "https://www.reddit.com/search.json"
    headers = {
        # Reddit requires a custom User-Agent for its API
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    params = {
        "q": query,
        "limit": limit,
        "type": "link", # Search for posts
        "sort": "new"
    }

    print(f"Fetching posts for query: '{query}'...")
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
                'created_at': datetime.datetime.fromtimestamp(post.get('created_utc')).strftime('%Y-%m-%d %H:%M:%S') if post.get('created_utc') else None,
                'selftext': post.get('selftext', '')[:500] + '...' if len(post.get('selftext', '')) > 500 else post.get('selftext', '')
            })
            
        return posts
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Reddit: {e}")
        if response.status_code == 429:
            print("Rate limited by Reddit. You may need to use the official Reddit API (PRAW) with authentication.")
        return []

if __name__ == "__main__":
    posts = scrape_reddit_posts(query="Nykaa fashion", limit=100)
    
    if posts:
        print(f"Successfully scraped {len(posts)} posts.")
        
        # Save to JSON
        json_filename = 'nykaa_reddit_posts.json'
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=4, ensure_ascii=False)
        print(f"Data saved to {json_filename}")
        
        # Save to CSV
        csv_filename = 'nykaa_reddit_posts.csv'
        keys = posts[0].keys()
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(posts)
        print(f"Data saved to {csv_filename}")
    else:
        print("No posts found or scraping failed.")
