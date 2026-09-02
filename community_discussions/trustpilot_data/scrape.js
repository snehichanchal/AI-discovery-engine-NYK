const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');
const path = require('path');

async function scrapeTrustpilot() {
    const domain = 'nykaafashion.com';
    const pages = 5;
    const allReviews = [];

    console.log(`Scraping Trustpilot reviews for ${domain}...`);

    const browser = await puppeteer.launch({ 
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080']
    });
    
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    await page.setViewport({ width: 1920, height: 1080 });
    
    for (let p = 1; p <= pages; p++) {
        const url = `https://www.trustpilot.com/review/${domain}?page=${p}`;
        console.log(`Fetching page ${p}: ${url}`);
        
        try {
            await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
            
            // Trustpilot uses Cloudflare / Datadome, sometimes it asks for a captcha
            const content = await page.content();
            if (content.includes('cf-browser-verification') || content.includes('captcha')) {
                console.warn(`WARNING: Cloudflare/Captcha challenge detected on page ${p}.`);
            }
            
            // Extract reviews from the page DOM and LD+JSON
            const reviews = await page.evaluate(() => {
                const pageReviews = [];
                
                // Method 1: Try structured data first
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                scripts.forEach(script => {
                    if (!script.innerText) return;
                    try {
                        const data = JSON.parse(script.innerText);
                        if (Array.isArray(data)) {
                            data.forEach(item => {
                                if (item['@type'] === 'LocalBusiness' && item.review) {
                                    item.review.forEach(r => pageReviews.push(r));
                                }
                            });
                        } else if (data['@type'] === 'LocalBusiness' && data.review) {
                            data.review.forEach(r => pageReviews.push(r));
                        }
                    } catch (e) {}
                });
                
                let parsedReviews = pageReviews.map(review => ({
                    platform: 'Trustpilot',
                    author: review.author ? review.author.name : 'Unknown',
                    rating: review.reviewRating ? review.reviewRating.ratingValue : null,
                    headline: review.headline || '',
                    content: review.reviewBody || '',
                    date_published: review.datePublished || '',
                    scraped_at: new Date().toISOString()
                }));

                // Method 2: If structured data failed, fallback to DOM parsing
                if (parsedReviews.length === 0) {
                    const reviewCards = document.querySelectorAll('article, .paper_paper__1PY90');
                    reviewCards.forEach(card => {
                        const author = card.querySelector('.typography_heading-xxs__qkLXz, [data-consumer-name-typography]')?.innerText?.trim() || 'Unknown';
                        const headline = card.querySelector('h2, [data-service-review-title-typography]')?.innerText?.trim() || '';
                        const content = card.querySelector('p[data-service-review-text-typography]')?.innerText?.trim() || '';
                        const dateText = card.querySelector('time')?.getAttribute('datetime') || '';
                        
                        // Rating is usually in an img alt tag or a specific div
                        const ratingImg = card.querySelector('img[alt*="Rated"]');
                        let rating = null;
                        if (ratingImg) {
                            const match = ratingImg.alt.match(/Rated (\\d)/);
                            if (match) rating = match[1];
                        }
                        
                        if (content || headline) {
                            parsedReviews.push({
                                platform: 'Trustpilot',
                                author,
                                rating,
                                headline,
                                content,
                                date_published: dateText,
                                scraped_at: new Date().toISOString()
                            });
                        }
                    });
                }
                
                return parsedReviews;
            });
            
            if (reviews.length > 0) {
                allReviews.push(...reviews);
                console.log(`Found ${reviews.length} reviews on page ${p}.`);
            } else {
                console.log(`No reviews found on page ${p}. End of results or bot detection.`);
                break;
            }
            
            // Random delay to mimic human behavior
            await new Promise(resolve => setTimeout(resolve, 2000 + Math.random() * 1500));
            
        } catch (err) {
            console.error(`Error on page ${p}: ${err.message}`);
            break;
        }
    }
    
    await browser.close();
    
    if (allReviews.length > 0) {
        console.log(`\nSuccessfully scraped ${allReviews.length} reviews.`);
        
        const jsonFilename = path.join(__dirname, 'nykaa_trustpilot_reviews.json');
        fs.writeFileSync(jsonFilename, JSON.stringify(allReviews, null, 4));
        console.log(`Data saved to ${jsonFilename}`);
        
    } else {
        console.log('\nNo reviews found or scraping failed.');
    }
}

scrapeTrustpilot();
