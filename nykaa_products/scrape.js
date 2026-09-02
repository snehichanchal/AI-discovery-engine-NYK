const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');
const path = require('path');

async function scrapeNykaaProducts() {
    // Starting with a general category page on Nykaa Fashion
    const url = 'https://www.nykaafashion.com/women/c/6842';
    console.log(`Navigating to ${url}...`);

    const browser = await puppeteer.launch({ 
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080']
    });
    
    const page = await browser.newPage();
    
    // Set realistic user agent to help bypass bot detection
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    await page.setViewport({ width: 1920, height: 1080 });

    try {
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        
        const content = await page.content();
        if (content.includes('Access Denied') && content.includes('errors.edgesuite.net')) {
            console.error("❌ ERROR: Akamai Edge WAF blocked the request. This usually happens when scraping from a datacenter IP. Please run this script from a residential IP or use a proxy service.");
            await browser.close();
            return;
        }

        let productLinks = new Set();
        let previousHeight = 0;
        
        console.log('Scrolling to find 100 product links...');
        
        while (productLinks.size < 100) {
            const newLinks = await page.evaluate(() => {
                const anchors = Array.from(document.querySelectorAll('a'));
                // Nykaa product URLs usually have '/p/' in them
                const productAnchors = anchors.filter(a => a.href && a.href.includes('/p/'));
                return productAnchors.map(a => a.href);
            });
            
            newLinks.forEach(link => productLinks.add(link));
            
            if (productLinks.size >= 100) {
                console.log(`Found ${productLinks.size} links. Stopping scroll.`);
                break;
            }

            previousHeight = await page.evaluate('document.body.scrollHeight');
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)');
            await new Promise(resolve => setTimeout(resolve, 2500)); 
            
            const newHeight = await page.evaluate('document.body.scrollHeight');
            if (newHeight === previousHeight) {
                console.log('Reached the bottom of the page or no more products loading.');
                break; 
            }
        }

        const allLinks = Array.from(productLinks);
        console.log("Sample links found:", allLinks.slice(0, 5));
        // Fisher-Yates shuffle
        for (let i = allLinks.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [allLinks[i], allLinks[j]] = [allLinks[j], allLinks[i]];
        }
        
        const urlsToScrape = allLinks.slice(0, 100);
        console.log(`Selected ${urlsToScrape.length} random products to scrape details...`);
        
        const productsData = [];

        for (let i = 0; i < urlsToScrape.length; i++) {
            const productUrl = urlsToScrape[i];
            console.log(`[${i+1}/${urlsToScrape.length}] Scraping: ${productUrl}`);
            
            const productPage = await browser.newPage();
            await productPage.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
            
            try {
                // Navigate to product page
                await productPage.goto(productUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
                // Give dynamic content some time to load
                await new Promise(resolve => setTimeout(resolve, 3000));

                const productDetail = await productPage.evaluate(() => {
                    // Extract Title
                    const titleEl = document.querySelector('h1');
                    const title = titleEl ? titleEl.innerText.trim() : 'Unknown Product';
                    
                    // Extract Price (looking for rupees symbol)
                    const priceElements = Array.from(document.querySelectorAll('span, div, p')).filter(el => el.innerText && el.innerText.includes('₹'));
                    const priceEl = priceElements.find(el => el.innerText.match(/\\d/));
                    const price = priceEl ? priceEl.innerText.trim().replace(/\\n/g, ' ') : 'N/A';
                    
                    // Extract Description
                    const descEl = document.querySelector('[data-testid="description-content"], .description, #description, .prod-desc');
                    const description = descEl ? descEl.innerText.trim() : 'No description available';
                    
                    // Extract Reviews and Comments
                    // The selectors might need to be updated based on Nykaa's specific DOM structure
                    const reviewElements = document.querySelectorAll('[data-testid="review-card"], .review-box, .review-container');
                    const reviews = Array.from(reviewElements).map(el => {
                        const author = el.querySelector('.author, .name, [data-testid="reviewer-name"]')?.innerText?.trim() || 'Anonymous';
                        const text = el.querySelector('.text, .content, p, [data-testid="review-text"]')?.innerText?.trim() || '';
                        const rating = el.querySelector('.rating, [data-testid="star-rating"]')?.innerText?.trim() || '';
                        return { author, rating, text };
                    });

                    return {
                        title,
                        price,
                        description,
                        reviews
                    };
                });
                
                productDetail.url = productUrl;
                productsData.push(productDetail);
                
            } catch (err) {
                console.error(`Failed to scrape ${productUrl}: ${err.message}`);
            } finally {
                await productPage.close();
            }
            
            // Adding a small delay between requests to be polite
            await new Promise(resolve => setTimeout(resolve, 1500));
        }
        
        // Save the scraped data
        const outputFile = path.join(__dirname, 'nykaa_products.json');
        fs.writeFileSync(outputFile, JSON.stringify(productsData, null, 2));
        console.log(`✅ Successfully saved ${productsData.length} product details to ${outputFile}`);

    } catch (error) {
        console.error('Critical Error in main scrape process:', error);
    } finally {
        await browser.close();
    }
}

scrapeNykaaProducts();
