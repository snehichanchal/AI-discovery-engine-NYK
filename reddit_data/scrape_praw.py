import praw
import json
import csv

# ---------------------------------------------------------
# OPTION 1: PRAW (Official API)
# ---------------------------------------------------------
# PREREQUISITES:
# 1. Run: pip install praw
# 2. Get credentials from https://www.reddit.com/prefs/apps
# ---------------------------------------------------------

def scrape_with_praw():
    # Replace these with your actual Reddit App credentials
    CLIENT_ID = "YOUR_CLIENT_ID"
    CLIENT_SECRET = "YOUR_CLIENT_SECRET"
    USER_AGENT = "script:nykaa_scraper:v1.0 (by /u/YOUR_REDDIT_USERNAME)"

    print("Authenticating with Reddit...")
    try:
        reddit = praw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT,
            # If your app requires login (script type), you might also need:
            # username="YOUR_USERNAME",
            # password="YOUR_PASSWORD"
        )
        
        # Verify read-only access
        print(f"Authenticated as Read-Only: {reddit.read_only}")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    print("Searching for 'Nykaa fashion'...")
    posts = []
    try:
        # Search across all subreddits
        for submission in reddit.subreddit("all").search("Nykaa fashion", limit=100):
            posts.append({
                'title': submission.title,
                'author': str(submission.author) if submission.author else "Deleted",
                'subreddit': str(submission.subreddit),
                'score': submission.score,
                'url': submission.url,
                'created_utc': submission.created_utc,
                'selftext': submission.selftext[:500] + "..." if len(submission.selftext) > 500 else submission.selftext
            })
            
        print(f"Successfully fetched {len(posts)} posts using PRAW.")
        
        # Save to JSON
        with open('nykaa_praw_results.json', 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        print(f"Error during scraping: {e}")

if __name__ == "__main__":
    scrape_with_praw()
