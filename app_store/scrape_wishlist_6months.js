const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const sleep = ms => new Promise(r => setTimeout(r, ms));

/**
 * Scrape wishlist-related reviews from the Apple App Store for Nykaa Fashion.
 * 
 * Strategy:
 *   1. Navigate to the app page on apps.apple.com
 *   2. Extract the authorization token from the page
 *   3. Use the internal API with proper auth to fetch reviews
 *   4. Filter for wishlist-related reviews from the last 6 months
 *   5. Deduplicate against existing data
 *
 * Output: nykaa_app_store_wishlist_reviews_6months.json
 */
async function scrapeWishlistReviews() {
    console.log('🚀 Starting Apple App Store wishlist reviews scraper (last 6 months, target: 500)...\n');

    // ── Config ──────────────────────────────────────────────────────────
    const TARGET_COUNT    = 500;
    const MONTHS_WINDOW   = 6;
    const OUTPUT_FILE     = path.join(__dirname, 'nykaa_app_store_wishlist_reviews_6months.json');
    const EXISTING_FILE   = path.join(__dirname, 'nykaa_app_store_reviews.json');
    const APP_ID          = '1439872423';
    const APP_URL         = `https://apps.apple.com/in/app/nykaa-fashion-shopping-app/id${APP_ID}`;
    const REVIEW_PAGE_URL = `${APP_URL}?see-all=reviews`;

    // Date boundary
    const now        = new Date();
    const cutoffDate = new Date(now);
    cutoffDate.setMonth(cutoffDate.getMonth() - MONTHS_WINDOW);
    console.log(`📅 Date window: ${cutoffDate.toISOString().split('T')[0]}  →  ${now.toISOString().split('T')[0]}\n`);

    // ── Wishlist detection ──────────────────────────────────────────────
    const primaryRegex = /wishlist|wish-list|wish list|wishlisted|wish listing|add to wishlist|wishlist feature|wishlist bug|wishlist items|wishlist disappear|wishlist cleared|wishlist empty|wishlist loading|wishlist sync|wishlist not working|wishlist section|wishlist server|wishlist filter|remove from wishlist|move to wishlist|wishlist category/i;
    const secondaryRegex = /\bsaved items?\b|\bsave for later\b|\bfavorite\b|\bfavourite\b|\bheart icon\b|\bheart button\b|\bbookmark\b|save item|save product|saved product|buy later|\bsaved\b.*\blist\b|\blist\b.*\bsaved\b|\bheart\b.*\bfilled\b|\bfilled\b.*\bheart\b/i;
    const wishComplaintRegex = /\bi wish\b.*\b(could|i could|there was|they|you|can)\b|\bi wish\b.*\bstar|\bwish you\b|\bwish her\b|\bwish him\b|\bwish them\b|\bbest wish|\bgood wish|\bwish the best\b|\bwish life\b|\bwish.*\brated?\b/i;

    function isWishlistRelevant(text) {
        if (primaryRegex.test(text)) return true;
        if (secondaryRegex.test(text)) return true;
        if (/\bwish\b/i.test(text) && !wishComplaintRegex.test(text)) return true;
        return false;
    }

    // ── Dedup setup ─────────────────────────────────────────────────────
    const seenKeys = new Set();
    function makeKey(r) {
        return `${r.author || ''}_${r.date || ''}_${r.title || ''}_${(r.body || '').slice(0, 40)}`;
    }

    if (fs.existsSync(EXISTING_FILE)) {
        try {
            const existing = JSON.parse(fs.readFileSync(EXISTING_FILE, 'utf8'));
            if (Array.isArray(existing)) {
                for (const r of existing) seenKeys.add(makeKey(r));
                console.log(`📂 Loaded ${existing.length} reviews from existing file for dedup.`);
            }
        } catch (e) { console.warn('⚠️  Could not parse existing file:', e.message); }
    }

    let wishlistReviews = [];
    if (fs.existsSync(OUTPUT_FILE)) {
        try {
            const prev = JSON.parse(fs.readFileSync(OUTPUT_FILE, 'utf8'));
            if (Array.isArray(prev)) {
                wishlistReviews = prev;
                for (const r of prev) seenKeys.add(makeKey(r));
                console.log(`📂 Loaded ${prev.length} pre-existing wishlist reviews from output file.`);
            }
        } catch (e) { console.warn('⚠️  Could not parse output file:', e.message); }
    }

    if (wishlistReviews.length >= TARGET_COUNT) {
        console.log(`\n✅ Target already reached (${wishlistReviews.length}). Exiting.`);
        return;
    }

    // ── Launch browser ──────────────────────────────────────────────────
    const browser = await puppeteer.launch({
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled'
        ]
    });

    const page = await browser.newPage();
    await page.setUserAgent(
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15'
    );

    // ── Step 1: Navigate to the app page and extract the auth token ─────
    console.log('🌐 Loading app page to extract authorization token...');
    
    let authToken = null;
    
    // Intercept network requests to capture the authorization token
    await page.setRequestInterception(true);
    page.on('request', request => {
        const headers = request.headers();
        if (headers['authorization'] && headers['authorization'].startsWith('Bearer')) {
            authToken = headers['authorization'];
        }
        request.continue();
    });

    try {
        await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
        await sleep(5000);
    } catch (e) {
        console.warn('⚠️  Page load partial, continuing...');
    }

    // Also try extracting token from meta tags or script tags
    if (!authToken) {
        authToken = await page.evaluate(() => {
            // Try to find the token in meta tags
            const meta = document.querySelector('meta[name="web-experience-app/config/environment"]');
            if (meta) {
                try {
                    const config = JSON.parse(decodeURIComponent(meta.content));
                    if (config.MEDIA_API && config.MEDIA_API.token) {
                        return `Bearer ${config.MEDIA_API.token}`;
                    }
                } catch(e) {}
            }
            return null;
        });
    }

    // Try to trigger a review load to capture the token
    if (!authToken) {
        console.log('🔄 Scrolling page to trigger review requests...');
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await sleep(3000);
        
        // Try navigating to the reviews page directly
        try {
            await page.goto(REVIEW_PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
            await sleep(5000);
        } catch(e) {}
    }

    if (authToken) {
        console.log(`🔑 Got auth token: ${authToken.slice(0, 30)}...`);
    } else {
        console.log('⚠️  No auth token found. Will try direct API calls from page context.');
    }

    // ── Step 2: Fetch reviews using the captured token ───────────────────
    const sortModes = ['mostRecent', 'mostHelpful'];
    const PAGE_SIZE = 20;
    const MAX_OFFSET = 15000;
    const MAX_CONSECUTIVE_EMPTY = 15;
    let totalScanned = 0;

    for (const sortMode of sortModes) {
        if (wishlistReviews.length >= TARGET_COUNT) break;

        console.log(`\n🔍 Scanning with sortMode="${sortMode}"...`);
        let offset = 0;
        let consecutiveEmpty = 0;
        let consecutiveOld = 0;

        while (wishlistReviews.length < TARGET_COUNT && consecutiveEmpty < MAX_CONSECUTIVE_EMPTY && offset < MAX_OFFSET) {
            const apiUrl = `https://amp-api.apps.apple.com/v1/catalog/in/apps/${APP_ID}/reviews?l=en-GB&limit=${PAGE_SIZE}&offset=${offset}&sort=${sortMode}&platform=iphone`;

            let reviewData = [];
            let success = false;

            for (let attempt = 1; attempt <= 10 && !success; attempt++) {
                // Try fetching from the page context (has the right cookies/origin)
                const result = await page.evaluate(async (url, token) => {
                    try {
                        const headers = {
                            'Accept': 'application/json',
                            'Content-Type': 'application/json',
                        };
                        if (token) {
                            headers['Authorization'] = token;
                        }
                        const resp = await fetch(url, { headers });
                        if (resp.status === 429) {
                            return { status: 429, data: [] };
                        }
                        if (resp.status !== 200) {
                            return { status: resp.status, data: [], text: await resp.text().catch(() => '') };
                        }
                        const json = await resp.json();
                        return { status: 200, data: json.data || [] };
                    } catch (err) {
                        return { status: 500, data: [], error: err.message };
                    }
                }, apiUrl, authToken);

                if (result.status === 200) {
                    reviewData = result.data;
                    success = true;
                } else if (result.status === 429) {
                    const wait = 5000 + (5000 * attempt) + Math.random() * 3000;
                    console.log(`⏳ Rate-limited (429) at offset ${offset}. Waiting ${(wait/1000).toFixed(0)}s (${attempt}/10)...`);
                    await sleep(wait);
                } else {
                    // Try falling back to the apps.apple.com domain API
                    const fallbackResult = await page.evaluate(async (off, sort) => {
                        try {
                            const url = `https://apps.apple.com/api/apps/v1/catalog/in/apps/1439872423/reviews?l=en-GB&limit=20&offset=${off}&sort=${sort}&platform=iphone`;
                            const resp = await fetch(url);
                            if (resp.status !== 200) return { status: resp.status, data: [] };
                            const json = await resp.json();
                            return { status: 200, data: json.data || [] };
                        } catch(e) {
                            return { status: 500, data: [] };
                        }
                    }, offset, sortMode);

                    if (fallbackResult.status === 200) {
                        reviewData = fallbackResult.data;
                        success = true;
                    } else if (fallbackResult.status === 429) {
                        const wait = 5000 + (5000 * attempt) + Math.random() * 3000;
                        console.log(`⏳ Rate-limited (429) at offset ${offset}. Waiting ${(wait/1000).toFixed(0)}s (${attempt}/10)...`);
                        await sleep(wait);
                    } else {
                        console.log(`❌ Non-200 status (${result.status}/${fallbackResult.status}) at offset ${offset}`);
                        await sleep(3000);
                    }
                }
            }

            if (!success || reviewData.length === 0) {
                consecutiveEmpty++;
                console.log(`⚠️  Empty/failed at offset ${offset}. (${consecutiveEmpty}/${MAX_CONSECUTIVE_EMPTY})`);
                offset += PAGE_SIZE;
                await sleep(2000);
                continue;
            }

            consecutiveEmpty = 0;
            let batchHasRecent = false;

            for (const item of reviewData) {
                const attr = item.attributes || {};
                const title  = (attr.title || '').trim();
                const body   = (attr.review || '').trim();
                const rating = attr.rating ? String(attr.rating) : '0';
                const author = (attr.userName || 'Anonymous').trim();
                const date   = attr.date || '';

                totalScanned++;

                // Date filter
                if (date) {
                    const reviewDate = new Date(date);
                    if (reviewDate < cutoffDate) continue;
                    batchHasRecent = true;
                }

                // Dedup
                const key = makeKey({ author, date, title, body });
                if (seenKeys.has(key)) continue;

                // Wishlist match
                const combined = `${title} ${body}`;
                if (!isWishlistRelevant(combined)) continue;

                seenKeys.add(key);
                wishlistReviews.push({
                    title,
                    rating,
                    author,
                    date,
                    body,
                    url: REVIEW_PAGE_URL,
                    scraped_at: now.toISOString()
                });

                console.log(`🎯 [${wishlistReviews.length}/${TARGET_COUNT}] "${title.slice(0, 50)}" by ${author} (${date.split('T')[0]})`);

                if (wishlistReviews.length % 3 === 0) {
                    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(wishlistReviews, null, 2));
                }
                if (wishlistReviews.length >= TARGET_COUNT) break;
            }

            if (sortMode === 'mostRecent' && !batchHasRecent && reviewData.length > 0) {
                consecutiveOld++;
                if (consecutiveOld >= 5) {
                    console.log(`📛 5 batches of only old reviews. Moving on.`);
                    break;
                }
            } else {
                consecutiveOld = 0;
            }

            offset += PAGE_SIZE;

            if (totalScanned > 0 && totalScanned % 200 < PAGE_SIZE) {
                console.log(`📊 Scanned: ${totalScanned} | Matches: ${wishlistReviews.length}/${TARGET_COUNT}`);
            }

            // Polite delay with randomization
            await sleep(2000 + Math.random() * 2000);
        }
    }

    await browser.close();

    // ── Final save ──────────────────────────────────────────────────────
    const finalReviews = wishlistReviews.slice(0, TARGET_COUNT);
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(finalReviews, null, 2));

    console.log(`\n${'═'.repeat(60)}`);
    console.log(`🎉 DONE!  Wishlist reviews: ${finalReviews.length}`);
    console.log(`💾 Saved to: ${OUTPUT_FILE}`);
    console.log(`📊 Total scanned: ${totalScanned}`);
    if (finalReviews.length < TARGET_COUNT) {
        console.log(`⚠️  Note: Apple App Store has limited wishlist reviews in this date range.`);
        console.log(`   The App Store typically has far fewer reviews than Google Play.`);
    }
    console.log(`${'═'.repeat(60)}\n`);
}

scrapeWishlistReviews().catch(err => {
    console.error('💥 Fatal error:', err);
    process.exit(1);
});
