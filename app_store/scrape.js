const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function scrapeAppStoreWishlistReviews() {
    console.log('🚀 Starting App Store wishlist reviews scraper for Nykaa Fashion...');

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
            console.log('Error loading existing file:', e.message);
        }
    }

    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    console.log('Navigating to App Store homepage...');
    await page.goto('https://apps.apple.com', { waitUntil: 'networkidle2' });
    await sleep(2000);

    let offset = 0;
    let totalScanned = 0;
    let consecutiveEmpty = 0;
    const maxOffset = 5000;

    while (wishlistReviews.length < targetCount && offset <= maxOffset && consecutiveEmpty < 10) {
        let success = false;
        let attempts = 0;
        let batchData = null;

        while (!success && attempts < 5) {
            attempts++;
            const res = await page.evaluate(async (off) => {
                const url = `https://apps.apple.com/api/apps/v1/catalog/in/apps/1439872423/reviews?l=en-GB&limit=20&offset=${off}&sort=mostRecent&platform=iphone`;
                try {
                    const r = await fetch(url);
                    if (r.status !== 200) {
                        return { status: r.status, text: await r.text() };
                    }
                    const data = await r.json();
                    return { status: r.status, data: data.data || [] };
                } catch (e) {
                    return { status: 500, text: e.message };
                }
            }, offset);

            if (res.status === 200 && res.data) {
                batchData = res.data;
                success = true;
            } else if (res.status === 429) {
                const backoff = 5000 * attempts;
                console.log(`⏳ Rate limited (429) at offset ${offset} (attempt ${attempts}/5). Waiting ${backoff/1000}s...`);
                await sleep(backoff);
            } else {
                console.log(`❌ Response ${res.status} at offset ${offset}: ${res.text || 'Empty'}`);
                break;
            }
        }

        if (!success || !batchData || batchData.length === 0) {
            consecutiveEmpty++;
            console.log(`⚠️ Empty response at offset ${offset}. Consecutive empty: ${consecutiveEmpty}`);
            offset += 20;
            await sleep(1500);
            continue;
        }

        consecutiveEmpty = 0;
        totalScanned += batchData.length;
        offset += batchData.length;

        for (const item of batchData) {
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

                if (wishlistReviews.length >= targetCount) {
                    break;
                }
            }
        }

        if (totalScanned % 200 === 0) {
            console.log(`📊 Scanned ${totalScanned} total reviews | Wishlist reviews: ${wishlistReviews.length}/${targetCount}`);
        }

        await sleep(1200);
    }

    await browser.close();

    const finalReviews = wishlistReviews.slice(0, targetCount);
    console.log(`\n🎉 Scraping finished! Total scanned: ${totalScanned} | Wishlist reviews saved: ${finalReviews.length}`);
    fs.writeFileSync(outputPath, JSON.stringify(finalReviews, null, 2));
    console.log(`💾 Successfully updated ${outputPath} with ${finalReviews.length} reviews.`);
}

scrapeAppStoreWishlistReviews().catch(err => {
    console.error('Fatal error in scraper:', err);
    process.exit(1);
});
