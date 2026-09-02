const puppeteer = require('../app_store/node_modules/puppeteer');
const fs = require('fs');

async function scrapeReddit() {
    console.log('Starting Puppeteer to scrape actual discussions from old.reddit.com...');
    
    // Launch headless browser
    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    
    // Set a normal user agent to avoid being blocked
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36');
    
    const posts = [];
    const targetCount = 100;
    
    try {
        console.log('Navigating to search page...');
        await page.goto('https://old.reddit.com/search?q=Nykaa+fashion&sort=new', { waitUntil: 'domcontentloaded', timeout: 30000 });
        
        while (posts.length < targetCount) {
            console.log(`Extracting data... (Current count: ${posts.length})`);
            
            // Extract posts on the current page
            const newPosts = await page.evaluate(() => {
                const results = [];
                const searchResultElements = document.querySelectorAll('.search-result');
                
                searchResultElements.forEach(el => {
                    const titleEl = el.querySelector('.search-title');
                    const timeEl = el.querySelector('.search-time time');
                    const authorEl = el.querySelector('.search-author a');
                    const scoreEl = el.querySelector('.search-score');
                    const commentsEl = el.querySelector('.search-comments');
                    const urlEl = el.querySelector('a.search-link');
                    
                    if (titleEl && urlEl) {
                        results.push({
                            platform: 'Reddit',
                            id: urlEl.href.split('/').filter(Boolean).pop(),
                            author: authorEl ? authorEl.textContent : 'Unknown',
                            content: titleEl.textContent,
                            url: urlEl.href,
                            created_at: timeEl ? timeEl.getAttribute('datetime') : new Date().toISOString(),
                            metrics: `Score: ${scoreEl ? scoreEl.textContent.trim() : '0'}, Comments: ${commentsEl ? commentsEl.textContent.replace(/[^0-9]/g, '') : '0'}`
                        });
                    }
                });
                
                return results;
            });
            
            posts.push(...newPosts);
            
            if (posts.length >= targetCount) break;
            
            // Try to click the "next" button
            const nextButton = await page.$('.nextprev a[rel~="next"]');
            if (nextButton) {
                console.log('Navigating to next page...');
                await Promise.all([
                    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
                    nextButton.click()
                ]);
                // Random delay to mimic human behavior
                await new Promise(resolve => setTimeout(resolve, 2000 + Math.random() * 2000));
            } else {
                console.log('No more pages found.');
                break;
            }
        }
        
    } catch (e) {
        console.error('Error during scraping:', e);
    } finally {
        await browser.close();
    }
    
    // Cap at exactly 100 if we got more
    const finalPosts = posts.slice(0, targetCount);
    
    if (finalPosts.length > 0) {
        console.log(`Successfully scraped ${finalPosts.length} real discussions.`);
        
        // Save to JSON
        fs.writeFileSync('social_media_discussions.json', JSON.stringify(finalPosts, null, 4));
        console.log('Saved data to social_media_discussions.json');
        
        // Save to CSV
        const headers = ['platform', 'id', 'author', 'content', 'url', 'created_at', 'metrics'];
        const csvRows = [headers.join(',')];
        
        for (const post of finalPosts) {
            const row = headers.map(header => {
                let val = post[header] || '';
                // Escape quotes
                val = val.toString().replace(/"/g, '""');
                return `"${val}"`;
            });
            csvRows.push(row.join(','));
        }
        
        fs.writeFileSync('social_media_discussions.csv', csvRows.join('\n'));
        console.log('Saved data to social_media_discussions.csv');
    } else {
        console.log('Failed to scrape any real posts.');
    }
}

scrapeReddit();
