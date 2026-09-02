const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function runWishlistScraper() {
    console.log('================================================================');
    console.log('🚀 Apple App Store Wishlist Reviews Scraper for Nykaa Fashion');
    console.log('================================================================\n');

    const APP_ID = '1439872423';
    const TARGET_COUNT = 500;
    const MONTHS_WINDOW = 6;
    
    const OUTPUT_FILE = path.join(__dirname, 'nykaa_app_store_wishlist_reviews_6months.json');
    const EXISTING_FILE = path.join(__dirname, 'nykaa_app_store_reviews.json');
    const REVIEW_URL = `https://apps.apple.com/in/app/nykaa-fashion-shopping-app/id${APP_ID}?see-all=reviews`;

    // Date cutoff: 6 months ago from current time (Aug 31, 2026)
    const now = new Date('2026-08-31T12:11:23+05:30');
    const cutoffDate = new Date(now);
    cutoffDate.setMonth(cutoffDate.getMonth() - MONTHS_WINDOW);
    console.log(`📅 Cutoff Date (Last 6 Months): ${cutoffDate.toISOString().split('T')[0]} to ${now.toISOString().split('T')[0]}`);

    // Wishlist relevance patterns
    const primaryWishlistRegex = /wishlist|wish-list|wish list|wishlisted|wish listing|add to wishlist|wishlist feature|wishlist bug|wishlist items|wishlist disappear|wishlist cleared|wishlist empty|wishlist loading|wishlist sync|wishlist not working|wishlist section|wishlist server|wishlist filter|remove from wishlist|move to wishlist|wishlist category/i;
    const secondaryWishlistRegex = /\bsaved items?\b|\bsave for later\b|\bfavorite\b|\bfavourite\b|\bheart icon\b|\bheart button\b|\bbookmark\b|save item|save product|saved product|buy later|\bsaved\b.*\blist\b|\blist\b.*\bsaved\b|\bheart\b.*\bfilled\b|\bfilled\b.*\bheart\b/i;
    const complaintWishRegex = /\bi wish\b.*\b(could|i could|there was|they|you|can)\b|\bi wish\b.*\bstar|\bwish you\b|\bwish her\b|\bwish him\b|\bwish them\b|\bbest wish|\bgood wish|\bwish the best\b|\bwish life\b|\bwish.*\brated?\b/i;

    function isWishlistRelevant(title, body) {
        const text = `${title} ${body}`;
        if (primaryWishlistRegex.test(text)) return true;
        if (secondaryWishlistRegex.test(text)) return true;
        if (/\bwish\b/i.test(text) && !complaintWishRegex.test(text)) return true;
        return false;
    }

    // Dedup keys
    const seenKeys = new Set();
    function getDedupKey(item) {
        const author = (item.author || item.userName || '').trim().toLowerCase();
        const title = (item.title || '').trim().toLowerCase();
        const date = (item.date || '').slice(0, 10);
        return `${author}_${date}_${title}`;
    }

    // 1. Load previously scraped reviews for deduplication
    let existingCount = 0;
    if (fs.existsSync(EXISTING_FILE)) {
        try {
            const raw = fs.readFileSync(EXISTING_FILE, 'utf8');
            const data = JSON.parse(raw);
            if (Array.isArray(data)) {
                data.forEach(item => seenKeys.add(getDedupKey(item)));
                existingCount = data.length;
                console.log(`📂 Loaded ${existingCount} previously scraped reviews from ${path.basename(EXISTING_FILE)} for deduplication.`);
            }
        } catch (e) {
            console.warn(`⚠️ Warning loading ${EXISTING_FILE}: ${e.message}`);
        }
    }

    // Load any existing output data
    let wishlistReviews = [];
    if (fs.existsSync(OUTPUT_FILE)) {
        try {
            const raw = fs.readFileSync(OUTPUT_FILE, 'utf8');
            const data = JSON.parse(raw);
            if (Array.isArray(data)) {
                wishlistReviews = data;
                data.forEach(item => seenKeys.add(getDedupKey(item)));
                console.log(`📂 Loaded ${wishlistReviews.length} existing reviews from output file.`);
            }
        } catch (e) {
            console.warn(`⚠️ Warning loading ${OUTPUT_FILE}: ${e.message}`);
        }
    }

    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    console.log('\n🌐 Launching browser & initializing session...');
    await page.goto(`https://apps.apple.com/in/app/nykaa-fashion-shopping-app/id${APP_ID}`, { waitUntil: 'domcontentloaded' });
    await sleep(3000);

    const sortModes = ['mostRecent', 'mostHelpful'];
    let totalScanned = 0;

    for (const sortMode of sortModes) {
        console.log(`\n🔍 Scanning App Store reviews (Sort Mode: ${sortMode})...`);
        let offset = 0;
        let consecutiveEmpty = 0;

        while (offset < 2000 && consecutiveEmpty < 5) {
            let res = null;
            let retries = 0;

            while (retries < 3) {
                res = await page.evaluate(async (off, sort, appId) => {
                    const url = `https://apps.apple.com/api/apps/v1/catalog/in/apps/${appId}/reviews?l=en-GB&limit=20&offset=${off}&sort=${sort}&platform=iphone`;
                    try {
                        const r = await fetch(url);
                        if (r.status === 429) return { status: 429, data: [] };
                        if (r.status !== 200) return { status: r.status, data: [] };
                        const json = await r.json();
                        return { status: 200, data: json.data || [] };
                    } catch (e) {
                        return { status: 500, data: [] };
                    }
                }, offset, sortMode, APP_ID);

                if (res.status === 429) {
                    retries++;
                    console.log(`⏳ Rate limit encountered at offset ${offset}. Pausing 4 seconds (attempt ${retries}/3)...`);
                    await sleep(4000);
                } else {
                    break;
                }
            }

            if (!res || !res.data || res.data.length === 0) {
                consecutiveEmpty++;
                offset += 20;
                await sleep(1000);
                continue;
            }

            consecutiveEmpty = 0;
            totalScanned += res.data.length;

            for (const item of res.data) {
                const attr = item.attributes || {};
                const title = (attr.title || '').trim();
                const body = (attr.review || '').trim();
                const rating = attr.rating ? String(attr.rating) : '0';
                const author = (attr.userName || 'Anonymous').trim();
                const dateStr = attr.date || '';
                const reviewDate = dateStr ? new Date(dateStr) : null;

                // Check 6 months date condition
                const isWithin6Months = reviewDate && reviewDate >= cutoffDate && reviewDate <= now;

                // Dedup check
                const dedupKey = getDedupKey({ author, title, date: dateStr });
                if (seenKeys.has(dedupKey)) continue;

                // Check wishlist relevance
                if (isWishlistRelevant(title, body)) {
                    seenKeys.add(dedupKey);
                    const reviewObj = {
                        title,
                        rating,
                        author,
                        date: dateStr,
                        body,
                        url: REVIEW_URL,
                        within_last_6_months: isWithin6Months,
                        scraped_at: now.toISOString()
                    };
                    wishlistReviews.push(reviewObj);

                    console.log(`  🎯 Found Wishlist Review [${wishlistReviews.length}] | Date: ${dateStr.slice(0, 10)} | Author: ${author} | Title: "${title}"`);

                    // Write incremental updates
                    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(wishlistReviews, null, 2));

                    if (wishlistReviews.length >= TARGET_COUNT) break;
                }
            }

            if (wishlistReviews.length >= TARGET_COUNT) break;
            offset += res.data.length;
            await sleep(1200);
        }
    }

    await browser.close();

    // Final result summary & save
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(wishlistReviews, null, 2));

    console.log('\n================================================================');
    console.log('✅ Scraping Complete!');
    console.log(`📊 Total Reviews Scanned across App Store: ${totalScanned}`);
    console.log(`💾 Total Wishlist Reviews Saved: ${wishlistReviews.length}`);
    console.log(`📁 File Saved to: ${OUTPUT_FILE}`);
    console.log('================================================================\n');
}

runWishlistScraper().catch(err => {
    console.error('Fatal execution error:', err);
    process.exit(1);
});
