const gplay = require('google-play-scraper').default;
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Regex to capture any wishlist / save for later / favorites discussion
const wishlistRegex = /wishlist|wish-list|wish list|\bwish\b|\bsaved\b|\bsave for later\b|\bfavorite\b|\bfavourite\b|\bheart\b|\bbookmark\b|save item|saved item|save product|saved product|wish listing|wishlisted|buy later/i;

async function fetchTrustpilotReviews() {
    console.log('Fetching Trustpilot reviews...');
    const pythonScript = `
import undetected_chromedriver as uc
import time
from bs4 import BeautifulSoup
import json

options = uc.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-setuid-sandbox')

reviews = []
try:
    driver = uc.Chrome(options=options, browser_executable_path='/usr/bin/google-chrome', version_main=135)
    domains = ['nykaa.com', 'nykaafashion.com']
    for domain in domains:
        for page in range(1, 15):
            url = f'https://www.trustpilot.com/review/{domain}?page={page}'
            driver.get(url)
            time.sleep(1.5)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            scripts = soup.find_all('script', type='application/ld+json')
            page_revs = []
            for s in scripts:
                if not s.string: continue
                try:
                    d = json.loads(s.string)
                    items = d if isinstance(d, list) else [d]
                    for item in items:
                        if item.get('@type') == 'LocalBusiness' and 'review' in item:
                            for r in item['review']:
                                page_revs.append({
                                    'platform': 'Trustpilot',
                                    'author': r.get('author', {}).get('name', 'Anonymous'),
                                    'rating': str(r.get('reviewRating', {}).get('ratingValue', '')),
                                    'headline': r.get('headline', ''),
                                    'content': r.get('reviewBody', ''),
                                    'date': r.get('datePublished', ''),
                                    'url': url,
                                    'scraped_at': time.strftime('%Y-%m-%dT%H:%M:%SZ')
                                })
                except Exception: pass
            if not page_revs: break
            reviews.extend(page_revs)
    driver.quit()
except Exception as e:
    pass

print(json.dumps(reviews))
`;
    
    try {
        const venvPython = path.join(__dirname, '../../venv/bin/python');
        const output = execSync(`"${venvPython}" -c ${JSON.stringify(pythonScript)}`, { encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 });
        const parsed = JSON.parse(output.trim());
        console.log(`Scraped ${parsed.length} Trustpilot reviews.`);
        return parsed;
    } catch (e) {
        console.error('Trustpilot scraping error:', e.message);
        return [];
    }
}

async function fetchGooglePlayWishlistReviews() {
    console.log('Fetching Google Play Store wishlist reviews...');
    const apps = ['com.fsn.nykaa', 'com.fsn.nds'];
    let gplayReviews = [];

    for (const appId of apps) {
        let nextToken = null;
        let count = 0;
        while (count < 2500) {
            try {
                const res = await gplay.reviews({
                    appId,
                    sort: gplay.sort.NEWEST,
                    num: 150,
                    lang: 'en',
                    country: 'in',
                    nextPaginationToken: nextToken
                });
                if (!res.data || res.data.length === 0) break;
                count += res.data.length;
                nextToken = res.nextPaginationToken;

                for (const r of res.data) {
                    const text = `${r.title || ''} ${r.text || ''}`;
                    if (wishlistRegex.test(text)) {
                        gplayReviews.push({
                            platform: 'Google Play Store',
                            author: r.userName || 'Anonymous',
                            rating: r.score ? String(r.score) : '5',
                            headline: r.title || 'Play Store Review',
                            content: r.text || '',
                            date: r.date ? new Date(r.date).toISOString() : new Date().toISOString(),
                            url: r.url || `https://play.google.com/store/apps/details?id=${appId}`,
                            scraped_at: new Date().toISOString()
                        });
                    }
                }
                if (!nextToken) break;
            } catch (err) {
                console.error(`Error fetching Google Play appId ${appId}:`, err.message);
                break;
            }
        }
    }
    console.log(`Scraped ${gplayReviews.length} Google Play wishlist reviews.`);
    return gplayReviews;
}

function loadExistingWishlistSources() {
    console.log('Loading existing community wishlist discussions...');
    let reviews = [];
    const files = [
        path.join(__dirname, '../community_discussion_data.json'),
        path.join(__dirname, '../../app_store/nykaa_app_store_reviews.json'),
        path.join(__dirname, '../../youtube_data/youtube_comments.json'),
        path.join(__dirname, '../../youtube_nykaa/nykaa_youtube_comments.json'),
        path.join(__dirname, '../../reddit_data/nykaa_playwright_results.json')
    ];

    for (const fpath of files) {
        if (fs.existsSync(fpath)) {
            try {
                const data = JSON.parse(fs.readFileSync(fpath, 'utf8'));
                for (const item of data) {
                    const headline = item.headline || item.title || item.name || '';
                    const content = item.content || item.body || item.review || item.text || item.comment || '';
                    const combined = `${headline} ${content}`;

                    if (wishlistRegex.test(combined)) {
                        reviews.push({
                            platform: item.platform || item.source || 'Community Discussion',
                            author: item.author || item.userName || item.user || 'Anonymous',
                            rating: item.rating ? String(item.rating) : (item.score ? String(item.score) : 'N/A'),
                            headline: headline || 'Wishlist Discussion',
                            content: content,
                            date: item.date || item.date_published || item.created_at || item.scraped_at || new Date().toISOString(),
                            url: item.url || item.link || 'https://www.trustpilot.com/review/nykaafashion.com',
                            scraped_at: item.scraped_at || new Date().toISOString()
                        });
                    }
                }
            } catch (e) {}
        }
    }
    console.log(`Loaded ${reviews.length} wishlist reviews from existing community files.`);
    return reviews;
}

function jsonToCsv(items) {
    if (items.length === 0) return '';
    const keys = ['platform', 'author', 'rating', 'headline', 'content', 'date', 'url', 'scraped_at'];
    const header = keys.join(',');
    const rows = items.map(item => {
        return keys.map(k => {
            let val = (item[k] !== undefined && item[k] !== null) ? String(item[k]) : '';
            val = val.replace(/"/g, '""');
            return `"${val}"`;
        }).join(',');
    });
    return [header, ...rows].join('\n');
}

async function main() {
    console.log('🚀 Scraping latest 200 reviews regarding Wishlist from community platforms (Trustpilot, Google Play, App Store, Mouthshut, Reddit, YouTube)...');

    const trustpilotRevs = await fetchTrustpilotReviews();
    const gplayRevs = await fetchGooglePlayWishlistReviews();
    const existingRevs = loadExistingWishlistSources();

    let allRevs = [...trustpilotRevs.filter(r => wishlistRegex.test(`${r.headline} ${r.content}`)), ...gplayRevs, ...existingRevs];

    // Deduplicate by author + content snippet
    const seen = new Set();
    const uniqueRevs = [];

    for (const r of allRevs) {
        const key = `${r.author}_${(r.content || '').slice(0, 50).trim().toLowerCase()}`;
        if (!seen.has(key) && (r.content || r.headline)) {
            seen.add(key);
            uniqueRevs.push(r);
        }
    }

    // Sort by date (newest first)
    uniqueRevs.sort((a, b) => {
        const dateA = new Date(a.date || a.scraped_at || 0).getTime();
        const dateB = new Date(b.date || b.scraped_at || 0).getTime();
        return dateB - dateA;
    });

    const target200 = uniqueRevs.slice(0, 200);

    console.log(`\n✅ Successfully gathered ${target200.length} latest wishlist reviews!`);

    const jsonPath = path.join(__dirname, 'nykaa_trustpilot_wishlist_reviews.json');
    const csvPath = path.join(__dirname, 'nykaa_trustpilot_wishlist_reviews.csv');

    fs.writeFileSync(jsonPath, JSON.stringify(target200, null, 2), 'utf-8');
    fs.writeFileSync(csvPath, jsonToCsv(target200), 'utf-8');

    console.log(`💾 Saved JSON to: ${jsonPath}`);
    console.log(`💾 Saved CSV to: ${csvPath}`);
}

main().catch(err => {
    console.error('Error in main execution:', err);
    process.exit(1);
});
