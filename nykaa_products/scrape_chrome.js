const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

// Helper to simulate random human delay
const randomSleep = (min, max) => {
    const delay = Math.floor(Math.random() * (max - min + 1)) + min;
    return new Promise(resolve => setTimeout(resolve, delay));
};

async function scrapeNykaaProductsWithChrome() {
    console.log('Launching your local Chrome browser...');
    
    // Connect to the real local Chrome browser
    const browser = await puppeteer.launch({
        executablePath: '/usr/bin/google-chrome', 
        headless: false, // Visible browser to mimic a human and bypass strict WAF
        defaultViewport: null, 
        args: [
            '--start-maximized',
            '--disable-blink-features=AutomationControlled' // Bypass basic navigator.webdriver detection
        ]
    });

    const page = await browser.newPage();
    
    // Use an incredibly standard User-Agent for desktop Chrome
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

    try {
        const categoryUrl = 'https://www.nykaafashion.com/women/c/6842';
        console.log(`Navigating to ${categoryUrl}...`);
        
        // Wait until dom loads instead of networkidle to seem more human (we will wait out the rest manually)
        await page.goto(categoryUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
        
        console.log('Waiting for initial page load naturally...');
        await randomSleep(3000, 5000);
        
        let productLinks = new Set();
        let scrollAttempts = 0;
        
        console.log('Mimicking human scrolling to find product links...');
        
        while (productLinks.size < 100 && scrollAttempts < 40) {
            try {
                // Human-like smooth scroll down a bit
                await page.evaluate(() => {
                    window.scrollBy({ top: Math.floor(Math.random() * 800) + 400, behavior: 'smooth' });
                });
                
                // Random pause like someone reading or waiting for images to load
                await randomSleep(1500, 3500);
                
                const newLinks = await page.evaluate(() => {
                    const anchors = Array.from(document.querySelectorAll('a'));
                    // Filter for Nykaa product URLs
                    return anchors.filter(a => a.href && a.href.includes('/p/')).map(a => a.href);
                });
                
                newLinks.forEach(link => productLinks.add(link));
                
                if (productLinks.size >= 100) {
                    console.log(`Collected ${productLinks.size} links! Stop scrolling.`);
                    break;
                }
            } catch (err) {
                // If page reloads (e.g. captcha solved or auto-refresh), the frame detaches.
                if (err.message.includes('detached Frame') || err.message.includes('Execution context was destroyed')) {
                    console.log('Page navigating or frame detached (possibly anti-bot redirect). Waiting a few seconds...');
                    await randomSleep(4000, 6000);
                } else {
                    console.log('Non-critical error during scroll:', err.message);
                }
            }
            scrollAttempts++;
        }

        // We only want 100 random products
        const allLinks = Array.from(productLinks);
        for (let i = allLinks.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [allLinks[i], allLinks[j]] = [allLinks[j], allLinks[i]];
        }
        
        const urlsToScrape = allLinks.slice(0, 100);
        console.log(`Ready to scrape details for ${urlsToScrape.length} products.`);
        
        const productsData = [];

        // Scrape each product by navigating directly, simulating human clicking through pages
        for (let i = 0; i < urlsToScrape.length; i++) {
            const productUrl = urlsToScrape[i];
            console.log(`[${i+1}/${urlsToScrape.length}] Loading: ${productUrl}`);
            
            await page.goto(productUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
            
            // Wait for product details and reviews to lazily load
            await randomSleep(2000, 4000);
            
            try {
                // Slight scroll to trigger lazy loading reviews
                await page.evaluate(() => {
                    window.scrollBy({ top: 1000, behavior: 'smooth' });
                });
                await randomSleep(1500, 3000);

                const productDetail = await page.evaluate(() => {
                    const title = document.querySelector('h1')?.innerText?.trim() || 'Unknown';
                    
                    const priceElements = Array.from(document.querySelectorAll('span, div, p')).filter(el => el.innerText && el.innerText.includes('₹'));
                    const priceEl = priceElements.find(el => el.innerText.match(/\\d/));
                    const price = priceEl ? priceEl.innerText.trim().replace(/\\n/g, ' ') : 'N/A';
                    
                    const descEl = document.querySelector('[data-testid="description-content"], .description, .prod-desc');
                    const description = descEl ? descEl.innerText.trim() : 'No description available';
                    
                    // Fetch reviews and comments
                    const reviewElements = document.querySelectorAll('[data-testid="review-card"], .review-box, .review-container');
                    const reviews = Array.from(reviewElements).map(el => {
                        const author = el.querySelector('.author, .name, [data-testid="reviewer-name"]')?.innerText?.trim() || 'Anonymous';
                        const text = el.querySelector('.text, .content, p, [data-testid="review-text"]')?.innerText?.trim() || '';
                        const rating = el.querySelector('.rating, [data-testid="star-rating"]')?.innerText?.trim() || '';
                        return { author, rating, text };
                    });

                    return { title, price, description, reviews };
                });
                
                productDetail.url = productUrl;
                productsData.push(productDetail);
            } catch (err) {
                if (err.message.includes('detached Frame') || err.message.includes('Execution context was destroyed')) {
                    console.log(`Frame detached while scraping ${productUrl} (Possible CAPTCHA/bot redirect). Skipping...`);
                    // We pause significantly to let the human solve it if they are there, so the next product loop works
                    await randomSleep(10000, 15000);
                } else {
                    console.error(`Error scraping ${productUrl}:`, err.message);
                }
            }
            
            // Add a natural pause before fetching the next product
            await randomSleep(1500, 4000);
        }
        
        const outputFile = path.join(__dirname, 'nykaa_products.json');
        fs.writeFileSync(outputFile, JSON.stringify(productsData, null, 2));
        console.log(`✅ Successfully saved ${productsData.length} products to ${outputFile}`);

    } catch (error) {
        console.error('An error occurred while fetching:', error);
    } finally {
        console.log('Finished operations, closing browser in 5 seconds...');
        await randomSleep(5000, 5000);
        await browser.close();
    }
}

scrapeNykaaProductsWithChrome();
