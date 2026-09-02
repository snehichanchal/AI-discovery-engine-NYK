const gplay = require('google-play-scraper').default;
const fs = require('fs');
const path = require('path');

async function scrapeWishlistReviews() {
    try {
        console.log('='.repeat(70));
        console.log('Scraping 500 wishlist-related reviews for Nykaa Fashion');
        console.log('from Google Play Store (all time)');
        console.log('='.repeat(70));

        // --- Configuration ---
        const TARGET_COUNT = 500;
        const APP_ID = 'com.fsn.nds';
        const OUTPUT_FILE = 'nykaa_wishlist_reviews.json';
        const EXISTING_FILE = 'nykaa_google_store_reviews.json';



        // --- Load existing review IDs for deduplication ---
        let existingIds = new Set();

        // Load from the main reviews file
        if (fs.existsSync(EXISTING_FILE)) {
            const existingData = JSON.parse(fs.readFileSync(EXISTING_FILE, 'utf-8'));
            existingData.forEach(r => existingIds.add(r.id));
            console.log(`Loaded ${existingIds.size} existing review IDs from ${EXISTING_FILE} for dedup.`);
        }

        // Also load from any previously scraped wishlist file
        if (fs.existsSync(OUTPUT_FILE)) {
            const prevWishlist = JSON.parse(fs.readFileSync(OUTPUT_FILE, 'utf-8'));
            prevWishlist.forEach(r => existingIds.add(r.id));
            console.log(`Loaded ${prevWishlist.length} previously scraped wishlist reviews from ${OUTPUT_FILE} for dedup.`);
        }

        // --- Wishlist-related regex ---
        // Broad matching to capture reviews discussing wishlist, saving items,
        // favorites, hearts, bookmarks and related user behaviors
        const wishlistRegex = /wishlist|wish-list|wish list|\bwish\b|\bsaved\b|\bsave for later\b|\bfavorite\b|\bfavourite\b|\bheart\b|\bbookmark\b|save item|save product|saved product|wish listing|wishlisted|buy later/i;

        let wishlistReviews = [];
        let nextToken = null;
        let totalProcessed = 0;
        let totalSkippedDuplicate = 0;
        let batchNumber = 0;

        console.log(`\nStarting scrape... Target: ${TARGET_COUNT} wishlist reviews\n`);

        while (wishlistReviews.length < TARGET_COUNT) {
            batchNumber++;
            const response = await gplay.reviews({
                appId: APP_ID,
                sort: gplay.sort.NEWEST,
                num: 150,
                lang: 'en',
                country: 'in',
                nextPaginationToken: nextToken
            });

            if (!response.data || response.data.length === 0) {
                console.log('\n⚠️  No more reviews available from Google Play Store.');
                break;
            }

            totalProcessed += response.data.length;
            nextToken = response.nextPaginationToken;

            let batchWishlistCount = 0;

            for (const review of response.data) {
                // Check if the review text mentions wishlist-related terms
                if (review.text && wishlistRegex.test(review.text)) {
                    // Skip if already exists in previous scrapes
                    if (existingIds.has(review.id)) {
                        totalSkippedDuplicate++;
                        continue;
                    }

                    wishlistReviews.push({
                        id: review.id,
                        userName: review.userName,
                        userImage: review.userImage,
                        date: review.date,
                        score: review.score,
                        scoreText: review.scoreText,
                        url: review.url,
                        title: review.title,
                        text: review.text,
                        replyDate: review.replyDate,
                        replyText: review.replyText,
                        version: review.version,
                        thumbsUp: review.thumbsUp,
                        criterias: review.criterias
                    });

                    // Track the new ID to prevent within-run duplicates
                    existingIds.add(review.id);
                    batchWishlistCount++;

                    if (wishlistReviews.length >= TARGET_COUNT) break;
                }
            }

            console.log(
                `Batch ${batchNumber}: Processed ${response.data.length} reviews | ` +
                `Found ${batchWishlistCount} wishlist | ` +
                `Total: ${wishlistReviews.length}/${TARGET_COUNT}`
            );

            // Stop if no pagination token
            if (!nextToken) {
                console.log('\n⚠️  No more pages available.');
                break;
            }

            // Small delay to avoid rate limiting
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        // --- Save results ---
        const finalReviews = wishlistReviews.slice(0, TARGET_COUNT);

        // Sort by date (newest first)
        finalReviews.sort((a, b) => new Date(b.date) - new Date(a.date));

        fs.writeFileSync(OUTPUT_FILE, JSON.stringify(finalReviews, null, 2));

        console.log('\n' + '='.repeat(70));
        console.log('SCRAPING COMPLETE');
        console.log('='.repeat(70));
        console.log(`Total reviews processed:     ${totalProcessed}`);
        console.log(`Wishlist reviews found:      ${finalReviews.length}`);
        console.log(`Skipped (already scraped):   ${totalSkippedDuplicate}`);
        console.log(`Saved to:                    ${OUTPUT_FILE}`);

        if (finalReviews.length > 0) {
            const newest = new Date(finalReviews[0].date).toLocaleDateString();
            const oldest = new Date(finalReviews[finalReviews.length - 1].date).toLocaleDateString();
            console.log(`Date range of saved reviews: ${oldest} — ${newest}`);
        }

        if (finalReviews.length < TARGET_COUNT) {
            console.log(`\n⚠️  Note: Only ${finalReviews.length} wishlist reviews were found.`);
            console.log(`   The Google Play Store API may not have ${TARGET_COUNT} wishlist-related reviews available.`);
        }

        console.log('\n✅ Done!');

    } catch (error) {
        console.error('❌ Error scraping reviews:', error.message);
        console.error(error.stack);
    }
}

scrapeWishlistReviews();
