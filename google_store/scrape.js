const gplay = require('google-play-scraper').default;
const fs = require('fs');

async function scrapeReviews() {
    try {
        console.log('Scraping the 200 latest reviews for Nykaa Fashion around wishlist from the Google Play Store...');
        
        const wishlistRegex = /wishlist|wish-list|wish list|\bwish\b|\bsaved\b|\bsave for later\b|\bfavorite\b|\bfavourite\b|\bheart\b|\bbookmark\b|save item|save product|saved product|wish listing|wishlisted|buy later/i;
        
        let wishlistReviews = [];
        let nextToken = null;
        let totalProcessed = 0;
        const targetCount = 200;

        while (wishlistReviews.length < targetCount) {
            const response = await gplay.reviews({
                appId: 'com.fsn.nds',
                sort: gplay.sort.NEWEST,
                num: 150,
                lang: 'en',
                country: 'in',
                nextPaginationToken: nextToken
            });

            if (!response.data || response.data.length === 0) {
                console.log('No more reviews available from Google Play Store.');
                break;
            }

            totalProcessed += response.data.length;
            nextToken = response.nextPaginationToken;

            for (const review of response.data) {
                if (review.text && wishlistRegex.test(review.text)) {
                    wishlistReviews.push(review);
                    if (wishlistReviews.length >= targetCount) break;
                }
            }

            console.log(`Processed ${totalProcessed} reviews... Found ${wishlistReviews.length}/${targetCount} wishlist reviews.`);

            if (!nextToken) break;
        }
        
        const final200Reviews = wishlistReviews.slice(0, targetCount);
        const outputPath = 'nykaa_google_store_reviews.json';
        fs.writeFileSync(outputPath, JSON.stringify(final200Reviews, null, 2));
        
        console.log(`✅ Successfully saved ${final200Reviews.length} wishlist reviews (out of ${totalProcessed} scanned) to ${outputPath}`);
    } catch (error) {
        console.error('❌ Error scraping reviews:', error.message);
    }
}

scrapeReviews();
