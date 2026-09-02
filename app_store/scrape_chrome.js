const puppeteer = require('puppeteer-core');
const fs = require('fs');

const randomSleep = (min, max) => {
    const delay = Math.floor(Math.random() * (max - min + 1)) + min;
    return new Promise(resolve => setTimeout(resolve, delay));
};

async function scrapeAppStoreReviewsWithChrome() {
    console.log('Launching your local Chrome browser...');
    
    // Launch using the user's actual Chrome browser
    const browser = await puppeteer.launch({
        executablePath: '/usr/bin/google-chrome', 
        headless: false, // User requested visible browser
        defaultViewport: null, 
        args: [
            '--start-maximized',
            '--disable-blink-features=AutomationControlled' // Bypass basic bot detection
        ]
    });

    const page = await browser.newPage();
    
    // Set a realistic user agent
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36');

    try {
        console.log('Navigating to Nykaa App Store page to mimic human behavior...');
        await page.goto('https://apps.apple.com/in/app/nykaa-fashion-shopping-app/id1439872423', { waitUntil: 'networkidle2' });
        
        // Scroll around to act like a human
        await page.evaluate(() => window.scrollBy({ top: 500, behavior: 'smooth' }));
        await randomSleep(2000, 4000);
        await page.evaluate(() => window.scrollBy({ top: 800, behavior: 'smooth' }));
        await randomSleep(2000, 3500);

        console.log("Fetching reviews via Apple's internal RSS API...");
        
        // We will execute fetch requests from INSIDE the browser page to get the data
        const reviews = await page.evaluate(async () => {
            const allReviews = [];
            
            for (let pageNum = 1; pageNum <= 2; pageNum++) {
                const url = `https://itunes.apple.com/in/rss/customerreviews/page=${pageNum}/id=1439872423/sortBy=mostRecent/json`;
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.feed && data.feed.entry) {
                    data.feed.entry.forEach(entry => {
                        allReviews.push({
                            title: entry.title.label,
                            rating: entry['im:rating'].label,
                            author: entry.author.name.label,
                            date: entry.updated ? entry.updated.label : 'N/A',
                            body: entry.content.label,
                            url: 'https://apps.apple.com/in/app/nykaa-fashion-shopping-app/id1439872423?see-all=reviews'
                        });
                    });
                }
                
                // Sleep inside evaluate is hard without a helper, we'll just fetch them sequentially
            }
            return allReviews;
        });

        if (reviews.length > 0) {
            // Trim to exactly 100 if we got more
            const finalReviews = reviews.slice(0, 100);
            
            fs.writeFileSync('nykaa_app_store_reviews.json', JSON.stringify(finalReviews, null, 2));
            console.log(`✅ Successfully saved ${finalReviews.length} reviews to nykaa_app_store_reviews.json`);
        } else {
            console.log('❌ Failed to extract any reviews.');
        }
        
    } catch (error) {
        console.error('Error scraping:', error);
    } finally {
        await randomSleep(2000, 3000);
        await browser.close();
    }
}

scrapeAppStoreReviewsWithChrome();
