import asyncio
import json
import requests
import time
import random
from playwright.async_api import async_playwright

async def get_reddit_cookies():
    print("Starting Playwright to get authenticated browser cookies...")
    async with async_playwright() as p:
        try:
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir="./playwright_profile",
                channel="chrome",
                headless=False,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        except Exception as e:
            print("Falling back to bundled chromium...")
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir="./playwright_profile",
                headless=False,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        
        page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()

        print("Navigating to Reddit to establish a valid session...")
        await page.goto("https://www.reddit.com/", wait_until="domcontentloaded")
        
        print("Waiting 15 seconds. If you see a CAPTCHA, please solve it!")
        await page.wait_for_timeout(15000)
        
        playwright_cookies = await browser_context.cookies()
        await browser_context.close()
        
        cookie_dict = {}
        for cookie in playwright_cookies:
            cookie_dict[cookie['name']] = cookie['value']
            
        return cookie_dict

def parse_comments(comment_list, max_comments=10):
    comments_data = []
    for comment_item in comment_list:
        if comment_item.get('kind') == 't1':  # 't1' indicates a comment
            comment = comment_item.get('data', {})
            
            # Skip deleted or removed comments
            if comment.get('body') in ['[deleted]', '[removed]']:
                continue
                
            parsed = {
                'id': comment.get('id'),
                'author': comment.get('author'),
                'body': comment.get('body'),
                'score': comment.get('score'), # Upvotes
                'created_utc': comment.get('created_utc')
            }
            
            # Recursively fetch replies
            replies_data = comment.get('replies')
            if replies_data and isinstance(replies_data, dict):
                replies_list = replies_data.get('data', {}).get('children', [])
                # Let's limit replies so we don't blow up the JSON size
                parsed['replies'] = parse_comments(replies_list, max_comments=3)
            else:
                parsed['replies'] = []
                
            comments_data.append(parsed)
            
            if len(comments_data) >= max_comments:
                break
    return comments_data

def scrape_json_with_cookies(cookies):
    print("\nUsing valid browser session cookies to hit Reddit's JSON API...")
    url = "https://www.reddit.com/search.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    params = {
        "q": "Nykaa fashion",
        "limit": 100,
        "type": "link",
        "sort": "new"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, cookies=cookies)
        response.raise_for_status()
        data = response.json()
        
        posts = []
        children = data.get('data', {}).get('children', [])
        
        print(f"Found {len(children)} posts. Fetching nested comments for each post (this will take ~{len(children)} seconds to avoid rate limits)...")
        
        for i, child in enumerate(children):
            post = child['data']
            post_id = post.get('id')
            permalink = post.get('permalink')
            
            post_obj = {
                'id': post_id,
                'title': post.get('title'),
                'author': post.get('author'),
                'content': post.get('selftext'),
                'score': post.get('score'),
                'upvote_ratio': post.get('upvote_ratio'),
                'num_comments': post.get('num_comments'),
                'created_utc': post.get('created_utc'),
                'url': f"https://www.reddit.com{permalink}" if permalink else post.get('url'),
                'subreddit': post.get('subreddit'),
                'comments': []
            }
            
            # Fetch comments using the permalink JSON endpoint
            if permalink:
                post_json_url = f"https://www.reddit.com{permalink[:-1]}.json" # Remove trailing slash and append .json
                try:
                    # Random human-like delay between requests
                    sleep_time = random.uniform(2.5, 6.5)
                    time.sleep(sleep_time)
                    
                    post_res = requests.get(post_json_url, headers=headers, cookies=cookies)
                    
                    if post_res.status_code == 200:
                        post_data = post_res.json()
                        # Reddit post JSON structure: [0] is the post itself, [1] is the comments
                        if isinstance(post_data, list) and len(post_data) > 1:
                            comments_list = post_data[1].get('data', {}).get('children', [])
                            # Extract top 15 comments per post for sentiment analysis
                            post_obj['comments'] = parse_comments(comments_list, max_comments=15)
                    else:
                        print(f"Failed to fetch comments for {post_id}. Status: {post_res.status_code}")
                except Exception as e:
                    print(f"Error fetching comments for {post_id}: {e}")
                    
            posts.append(post_obj)
            
            if (i + 1) % 10 == 0:
                print(f"Processed {i + 1}/{len(children)} posts...")
            
        print(f"Successfully fetched {len(posts)} posts with nested comments!")
        
        with open('nykaa_playwright_results.json', 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=4, ensure_ascii=False)
        print("Saved to nykaa_playwright_results.json")
        
    except Exception as e:
        print(f"Failed to fetch JSON data: {e}")
        if 'response' in locals():
            print(f"Status Code: {response.status_code}")

if __name__ == "__main__":
    cookies = asyncio.run(get_reddit_cookies())
    scrape_json_with_cookies(cookies)
