const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');
const path = require('path');

async function scrapeMouthshut(page, url) {
    console.log(`Scraping Mouthshut: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    
    // Wait for the reviews to load
    try { await page.waitForSelector('.review-article', { timeout: 10000 }); } catch (e) {}

    const reviews = await page.evaluate((currentUrl) => {
        const reviewElements = document.querySelectorAll('.review-article, .row.review-article, .review-list');
        const data = [];
        
        reviewElements.forEach(el => {
            const author = el.querySelector('.user-ms-name, .profile-details a')?.innerText?.trim() || 'Unknown';
            const headlineEl = el.querySelector('strong, .review-title, a[class*="review-title"]');
            const headline = headlineEl?.innerText?.trim() || '';
            const urlEl = el.querySelector('a[href*="/review/"]');
            const url = urlEl ? (urlEl.href.startsWith('http') ? urlEl.href : 'https://www.mouthshut.com' + urlEl.getAttribute('href')) : currentUrl;
            
            // Extract the visible text of the review
            const contentEl = el.querySelector('.more.reviewdata, .review-content, .reviewdata');
            let content = contentEl ? contentEl.innerText.trim() : '';
            
            // Some reviews on Mouthshut might contain videos, we will mark the transcription field
            const hasVideo = el.querySelector('.video-thumbnail, .video-player, video') !== null;
            
            if (headline || content) {
                data.push({
                    platform: 'Mouthshut',
                    author,
                    headline,
                    url: url,
                    content: content || "Content not available",
                    video_transcript: hasVideo ? "Video present - Transcript not available" : "No video",
                    scraped_at: new Date().toISOString()
                });
            }
        });
        return data;
    }, url);
    
    console.log(`Found ${reviews.length} reviews from Mouthshut.`);
    return reviews;
}

async function scrapePissedConsumer(page, url) {
    console.log(`Scraping PissedConsumer: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    
    // Wait for the reviews to load
    try { await page.waitForSelector('.review-row, .review-block, .review-item', { timeout: 10000 }); } catch (e) {}

    const reviews = await page.evaluate((currentUrl) => {
        const reviewElements = document.querySelectorAll('.review-row, .review-block, .review-item, article');
        const data = [];
        
        reviewElements.forEach(el => {
            const author = el.querySelector('.user-name, .author-name, .author-info, .reviewer-name')?.innerText?.trim() || 'Unknown';
            const headlineEl = el.querySelector('h2.review-title, h3.review-title, .title, h2.review-title a, h3.review-title a');
            const headline = headlineEl?.innerText?.trim() || '';
            let reviewUrl = currentUrl;
            if (headlineEl && headlineEl.tagName === 'A') {
                reviewUrl = headlineEl.href;
            } else {
                const linkEl = el.querySelector('a[href*="/review/"]');
                if (linkEl) reviewUrl = linkEl.href;
            }
            if (reviewUrl && !reviewUrl.startsWith('http')) {
                reviewUrl = 'https://nykaa-fashion.pissedconsumer.com' + reviewUrl;
            }
            
            const contentEl = el.querySelector('.review-text, .text, .content, .review-content');
            let content = contentEl ? contentEl.innerText.trim() : '';
            
            const hasVideo = el.querySelector('video, iframe[src*="youtube"], .video-container') !== null;
            
            if (headline || content) {
                data.push({
                    platform: 'PissedConsumer',
                    author,
                    headline,
                    url: reviewUrl,
                    content: content || "Content not available",
                    video_transcript: hasVideo ? "Video present - Transcript not available" : "No video",
                    scraped_at: new Date().toISOString()
                });
            }
        });
        return data;
    }, url);
    
    console.log(`Found ${reviews.length} reviews from PissedConsumer.`);
    return reviews;
}

async function main() {
    const mouthshutBaseUrl = "https://www.mouthshut.com/product-reviews/nykaa-fashion-reviews-926168279";
    const pissedConsumerBaseUrl = "https://nykaa-fashion.pissedconsumer.com/review.html";
    
    const browser = await puppeteer.launch({ 
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080']
    });
    
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    await page.setViewport({ width: 1920, height: 1080 });
    
    let allReviews = [];
    
    // Scrape Mouthshut - 6 pages (approx 120 reviews)
    for(let i=1; i<=6; i++) {
        let url = i === 1 ? mouthshutBaseUrl : `${mouthshutBaseUrl}-page-${i}`;
        try {
            const mouthshutReviews = await scrapeMouthshut(page, url);
            allReviews = allReviews.concat(mouthshutReviews);
        } catch (e) {
            console.error(`Error scraping Mouthshut page ${i}:`, e.message);
        }
    }
    
    // Scrape PissedConsumer - 4 pages (approx 40 reviews)
    for(let i=1; i<=4; i++) {
        let url = i === 1 ? pissedConsumerBaseUrl : `${pissedConsumerBaseUrl}?page=${i}`;
        try {
            const pissedConsumerReviews = await scrapePissedConsumer(page, url);
            allReviews = allReviews.concat(pissedConsumerReviews);
        } catch (e) {
            console.error(`Error scraping PissedConsumer page ${i}:`, e.message);
        }
    }
    
    await browser.close();
    
    // If updating existing file, load it first
    const outputPath = path.join(__dirname, 'community_discussion_data.json');
    let existingData = [];
    // We overwrite completely since we are scraping page 1 again
    fs.writeFileSync(outputPath, JSON.stringify(allReviews, null, 4));
    console.log(`\nSuccessfully saved ${allReviews.length} total reviews to ${outputPath}`);
}

main();
