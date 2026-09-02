import requests
import json

# ---------------------------------------------------------
# OPTION 4: Search Engine API (SerpApi)
# ---------------------------------------------------------
# PREREQUISITES:
# 1. Run: pip install google-search-results
# 2. Get a free API key from https://serpapi.com/
# ---------------------------------------------------------

def scrape_with_serpapi():
    try:
        from serpapi import GoogleSearch
    except ImportError:
        print("Please install the module: pip install google-search-results")
        return

    # Replace with your actual SerpApi Key
    API_KEY = "YOUR_SERPAPI_KEY"
    
    # We search Google for discussions on Reddit about Nykaa fashion
    query = 'site:reddit.com "Nykaa fashion"'
    
    params = {
        "engine": "google",
        "q": query,
        "api_key": API_KEY,
        "num": 100 # Attempt to get 100 results per page
    }

    print(f"Searching Google via SerpApi for: {query}")
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        
        organic_results = results.get("organic_results", [])
        
        posts = []
        for result in organic_results:
            posts.append({
                'title': result.get('title'),
                'url': result.get('link'),
                'snippet': result.get('snippet'), # Contains a preview of the discussion
                'source': result.get('source')
            })
            
        print(f"Successfully fetched {len(posts)} Reddit posts via Google Search.")
        
        with open('nykaa_serpapi_results.json', 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        print(f"Error during search: {e}")
        print("Make sure you replaced 'YOUR_SERPAPI_KEY' with a valid key.")

if __name__ == "__main__":
    scrape_with_serpapi()
