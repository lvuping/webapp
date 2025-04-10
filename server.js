import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { scrapeNaverBlog, saveDataToJson } from './search.js'; // Import functions from search.js

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const port = 3000;

// Middleware to parse JSON bodies
app.use(express.json());

// Serve static files from the current directory (e.g., index.html, main.html)
app.use(express.static(__dirname));

// Route to serve main.html at the root
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'main.html'));
});

// API endpoint to run the Naver search
app.post('/api/run-naver-search', async (req, res) => {
  const { keyword, region, from_date, to_date, scroll_count } = req.body;

  // Basic validation
  if (!keyword || !region || !from_date || !to_date || !scroll_count) {
    return res.status(400).json({ success: false, message: 'Missing required parameters.' });
  }

  // Convert scroll_count to number just in case
  const scrollCountNum = parseInt(scroll_count, 10);
  if (isNaN(scrollCountNum) || scrollCountNum <= 0) {
      return res.status(400).json({ success: false, message: 'Invalid scroll_count.' });
  }

  // Format dates to YYYYMMDD as required by Naver URL
  const fromDateFormatted = from_date.replace(/-/g, ''); // Remove hyphens
  const toDateFormatted = to_date.replace(/-/g, '');   // Remove hyphens


  console.log(`Received search request: Keyword=${keyword}, Region=${region}, From=${fromDateFormatted}, To=${toDateFormatted}, Scrolls=${scrollCountNum}`);

  try {
    // Run the scraping function
    const results = await scrapeNaverBlog(keyword, region, fromDateFormatted, toDateFormatted, scrollCountNum);

    // Save the results
    saveDataToJson(results, keyword, region); // Pass keyword and region for filename

    const message = results.length > 0
        ? `Search completed successfully. Found ${results.length} items. Data saved.`
        : `Search completed, but no matching items found for "${keyword}" in "${region}".`;

    res.json({ success: true, message: message, count: results.length });

  } catch (error) {
    console.error('Error during scraping process:', error);
    res.status(500).json({ success: false, message: `Server error during search: ${error.message}` });
  }
});

app.listen(port, () => {
  console.log(`Server listening at http://localhost:${port}`);
});
