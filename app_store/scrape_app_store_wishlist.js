const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function scrapeAppStoreWishlistReviews() {
    console.log('🚀 Starting Turbo App Store wishlist reviews scraper for Nykaa Fashion...');

    const wishlistRegex = /wishlist|wish-list|wish list|\bwish\b|\bsaved\b|\bsave for later\b|\bfavorite\b|\bfavourite\b|\bheart\b|\bbookmark\b|save item|save product|saved product|wish listing|wishlisted|buy later/i;
    
    const outputPath = path.join(__dirname, 'nykaa_app_store_reviews.json');
    const reviewUrl = 'https://apps.apple.com/in/app/nykaa-fashion-shopping-app/id1439872423?see-all=reviews';
    const targetCount = 200;

    let wishlistReviews = [];
    const seenKeys = new Set();

    if (fs.existsSync(outputPath)) {
        try {
            const raw = fs.readFileSync(outputPath, 'utf8');
            const existing = JSON.parse(raw);
            if (Array.isArray(existing)) {
                wishlistReviews = existing;
                for (const item of existing) {
                    const key = `${item.author}_${item.date}_${item.title}_${(item.body || '').slice(0, 30)}`;
                    seenKeys.add(key);
                }
                console.log(`📂 Loaded ${wishlistReviews.length} pre-existing wishlist reviews from ${outputPath}`);
            }
        } catch (e) {
            console.log('Error reading existing file:', e.message);
        }
    }

    if (wishlistReviews.length >= targetCount) {
        console.log(`✅ Target of ${targetCount} wishlist reviews already reached (${wishlistReviews.length} available).`);
        return;
    }

    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    console.log('Navigating to App Store homepage for clean origin context...');
    await page.goto('https://apps.apple.com', { waitUntil: 'networkidle2' });
    await sleep(2000);

    const sortModes = ['mostRecent', 'mostHelpful'];
    const batchSize = 2; // 2 requests = 40 reviews per step

    for (const sortMode of sortModes) {
        if (wishlistReviews.length >= targetCount) break;

        console.log(`\n🔍 Scanning reviews with sortMode="${sortMode}"...`);
        let currentOffset = 0;
        let totalScannedInMode = 0;
        let consecutiveEmptyBatches = 0;

        while (wishlistReviews.length < targetCount && consecutiveEmptyBatches < 8) {
            const offsetsToFetch = [];
            for (let b = 0; b < batchSize; b++) {
                offsetsToFetch.push(currentOffset + (b * 20));
            }

            let success = false;
            let attempts = 0;
            let batchResults = null;

            while (!success && attempts < 5) {
                attempts++;
                batchResults = await page.evaluate(async (offs, sort) => {
                    const fetchPromises = offs.map(async (off) => {
                        const url = `https://apps.apple.com/api/apps/v1/catalog/in/apps/1439872423/reviews?l=en-GB&limit=20&offset=${off}&sort=${sort}&platform=iphone`;
                        try {
                            const r = await fetch(url);
                            if (r.status !== 200) {
                                return { status: r.status, text: await r.text(), off };
                            }
                            const data = await r.json();
                            return { status: r.status, data: data.data || [], off };
                        } catch (e) {
                            return { status: 500, text: e.message, off };
                        }
                    });
                    return Promise.all(fetchPromises);
                }, offsetsToFetch, sortMode);

                const has429 = batchResults.some(r => r.status === 429);
                if (has429) {
                    const backoff = 5000 * attempts;
                    console.log(`⏳ Rate limited (429) at offset ${currentOffset} (attempt ${attempts}/5). Waiting ${backoff/1000}s...`);
                    await sleep(backoff);
                } else {
                    success = true;
                }
            }

            let totalItemsInBatch = 0;
            for (const res of batchResults) {
                if (res.status === 200 && res.data && res.data.length > 0) {
                    totalItemsInBatch += res.data.length;
                    totalScannedInMode += res.data.length;

                    for (const item of res.data) {
                        const attr = item.attributes || {};
                        const title = attr.title ? attr.title.trim() : '';
                        const body = attr.review ? attr.review.trim() : '';
                        const rating = attr.rating ? String(attr.rating) : '0';
                        const author = attr.userName ? attr.userName.trim() : 'Anonymous';
                        const date = attr.date || '';

                        const dedupKey = `${author}_${date}_${title}_${body.slice(0, 30)}`;
                        if (seenKeys.has(dedupKey)) continue;

                        const combinedText = `${title} ${body}`;

                        if (wishlistRegex.test(combinedText)) {
                            seenKeys.add(dedupKey);
                            wishlistReviews.push({
                                title,
                                rating,
                                author,
                                date,
                                body,
                                url: reviewUrl
                            });

                            console.log(`🎯 [${wishlistReviews.length}/${targetCount}] Found wishlist review (author: "${author}", date: "${date.split('T')[0]}")`);
                            fs.writeFileSync(outputPath, JSON.stringify(wishlistReviews, null, 2));

                            if (wishlistReviews.length >= targetCount) break;
                        }
                    }
                }
            }

            if (totalItemsInBatch === 0) {
                consecutiveEmptyBatches++;
                console.log(`⚠️ No reviews in batch starting at offset ${currentOffset}. Empty batch count: ${consecutiveEmptyBatches}`);
            } else {
                consecutiveEmptyBatches = 0;
            }

            currentOffset += (batchSize * 20);

            if (totalScannedInMode % 200 === 0) {
                console.log(`📊 Mode [${sortMode}]: Scanned ${totalScannedInMode} reviews | Wishlist reviews total: ${wishlistReviews.length}/${targetCount}`);
            }

            await sleep(800); // 800ms delay between steps
        }
    }

    await browser.close();

    const finalReviews = wishlistReviews.slice(0, targetCount);
    console.log(`\n🎉 Completed! Total wishlist reviews collected: ${finalReviews.length}`);
    fs.writeFileSync(outputPath, JSON.stringify(finalReviews, null, 2));
    console.log(`💾 Successfully updated ${outputPath} with ${finalReviews.length} reviews.`);
}

scrapeAppStoreWishlistReviews().catch(err => {
    console.error('Fatal error in scraper:', err);
    process.exit(1);
});
