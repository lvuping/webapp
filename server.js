import express from 'express';
import { scrapeNaverBlog } from './naver.js'; // Import the function
import fs from 'fs/promises'; // For file system operations
import path from 'path'; // For handling file paths
import { fileURLToPath } from 'url'; // To get __dirname in ES modules

// --- Basic Setup ---
const app = express();
const port = 3000; // You can change this port if needed

// Get directory name in ES module scope
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Middleware to parse JSON request bodies
app.use(express.json());

// --- API Endpoint ---
app.post('/api/run-naver-search', async (req, res) => {
    console.log('Received search request:', req.body);
    const { keyword, region, from_date, to_date, scroll_count } = req.body;

    // Basic validation
    if (!keyword || !region || !from_date || !to_date || !scroll_count) {
        return res.status(400).json({ success: false, message: 'Missing required parameters.' });
    }

    // Format dates for naver.js (assuming YYYY-MM-DD input from HTML)
    const fromDateFormatted = from_date.replace(/-/g, '.');
    const toDateFormatted = to_date.replace(/-/g, '.');
    const scrollCountNum = parseInt(scroll_count, 10);

    if (isNaN(scrollCountNum) || scrollCountNum < 1) {
         return res.status(400).json({ success: false, message: 'Invalid scroll count.' });
    }

    try {
        console.log(`Calling scrapeNaverBlog with: ${keyword}, ${region}, ${fromDateFormatted}, ${toDateFormatted}, ${scrollCountNum}`);
        const results = await scrapeNaverBlog(keyword, region, fromDateFormatted, toDateFormatted, scrollCountNum);
        console.log(`Scraping finished. Found ${results.length} items.`);

        // --- File Saving Logic ---
        const now = new Date();
        const timestamp = now.getFullYear().toString() +
                          (now.getMonth() + 1).toString().padStart(2, '0') +
                          now.getDate().toString().padStart(2, '0') +
                          now.getHours().toString().padStart(2, '0') +
                          now.getMinutes().toString().padStart(2, '0');
        // Sanitize keyword and region for filename (replace spaces, etc.)
        const safeKeyword = keyword.replace(/[^a-z0-9ㄱ-ㅎㅏ-ㅣ가-힣_-]/gi, '_');
        const safeRegion = region.replace(/[^a-z0-9ㄱ-ㅎㅏ-ㅣ가-힣_-]/gi, '_');
        const filename = `${safeKeyword}_${safeRegion}_${timestamp}.json`;
        const resultsDir = path.join(__dirname, 'result');
        const filePath = path.join(resultsDir, filename);

        // Ensure result directory exists
        try {
            await fs.access(resultsDir);
        } catch (error) {
            if (error.code === 'ENOENT') {
                console.log(`Creating result directory: ${resultsDir}`);
                await fs.mkdir(resultsDir, { recursive: true });
            } else {
                throw error; // Re-throw other errors
            }
        }

        console.log(`Saving results to: ${filePath}`);
        await fs.writeFile(filePath, JSON.stringify(results, null, 2), 'utf-8');
        console.log('File saved successfully.');

        res.json({
            success: true,
            message: `Search complete. Found ${results.length} items. Saved to ${filename}`,
            filename: filename,
            itemCount: results.length
        });

    } catch (error) {
        console.error('Error during scraping or saving:', error);
        res.status(500).json({ success: false, message: `An error occurred: ${error.message}` });
    }
});

// --- Serve Static Files (Optional but useful for testing) ---
// Serve naver.html and potentially index.html from the root
app.use(express.static(__dirname));

// --- Start Server ---
app.listen(port, () => {
    console.log(`Server listening at http://localhost:${port}`);
    console.log(`Access the search interface at http://localhost:${port}/naver.html`);
});
