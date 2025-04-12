import express from 'express';
import path from 'path';
import fs from 'fs/promises'; // Import the promises version of fs
import { fileURLToPath } from 'url';
import { scrapeNaverBlog, saveDataToJson } from './search.js'; // Import functions from search.js
import { processBlogUrl } from './downloadBlog.js'; // Import the blog processing function from the new file

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const port = 3000;

// Middleware to parse JSON bodies
app.use(express.json());

// Serve static files from the current directory (e.g., index.html, main.html)
app.use(express.static(__dirname));

// Route to serve index.html at the root
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
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

// --- Utility function to read/write the results JSON ---
const resultsFilePath = path.join(__dirname, 'result', 'search_results.json');

async function readResultsFile() {
    try {
        await fs.access(resultsFilePath); // Check if file exists
        const data = await fs.readFile(resultsFilePath, 'utf8');
        return JSON.parse(data);
    } catch (error) {
        if (error.code === 'ENOENT') {
            console.log('results file not found, returning empty object.');
            return {}; // File doesn't exist, return empty object
        }
        // Handle JSON parsing errors or other read errors
        console.error('Error reading results file:', error);
        throw new Error('Could not read results file.'); // Re-throw specific error
    }
}

async function writeResultsFile(data) {
    try {
        // Ensure result directory exists
        await fs.mkdir(path.dirname(resultsFilePath), { recursive: true });
        await fs.writeFile(resultsFilePath, JSON.stringify(data, null, 2), 'utf8');
    } catch (error) {
        console.error('Error writing results file:', error);
        throw new Error('Could not write results file.');
    }
}
// --- End Utility Functions ---


// API endpoint to get all results from the single JSON file
app.get('/api/results', async (req, res) => {
  try {
    const data = await readResultsFile();
     // Basic validation: check if it's an object
     if (typeof data !== 'object' || data === null || Array.isArray(data)) {
        console.warn(`Warning: results file does not contain a valid JSON object. Returning empty.`);
        res.json({ success: true, data: {} }); // Return empty object if invalid format
     } else {
        res.json({ success: true, data: data });
     }
  } catch (error) {
    console.error('Error serving results:', error);
    res.status(500).json({ success: false, message: error.message || 'Server error reading results file.' });
  }
});

// API endpoint to DELETE selected results
app.delete('/api/results', async (req, res) => {
    const { linksToDelete } = req.body; // Expect an array of links (keys)

    if (!Array.isArray(linksToDelete) || linksToDelete.length === 0) {
        return res.status(400).json({ success: false, message: 'Invalid request: "linksToDelete" must be a non-empty array.' });
    }

    console.log(`Received request to delete ${linksToDelete.length} items.`);

    try {
        let data = await readResultsFile();
        let deleteCount = 0;
        linksToDelete.forEach(link => {
            if (data.hasOwnProperty(link)) {
                delete data[link];
                deleteCount++;
            } else {
                 console.warn(`Link not found for deletion: ${link}`);
            }
        });

        await writeResultsFile(data);
        console.log(`Successfully deleted ${deleteCount} items.`);
        res.json({ success: true, message: `${deleteCount} items deleted successfully.` });

    } catch (error) {
        console.error('Error deleting results:', error);
        res.status(500).json({ success: false, message: error.message || 'Server error deleting results.' });
    }
});

// API endpoint to update the 'extracted' status of items
app.patch('/api/results/status', async (req, res) => {
    const { linksToUpdate } = req.body; // Expect an array of links (keys)

    if (!Array.isArray(linksToUpdate) || linksToUpdate.length === 0) {
        return res.status(400).json({ success: false, message: 'Invalid request: "linksToUpdate" must be a non-empty array.' });
    }

    console.log(`Received request to update status for ${linksToUpdate.length} items.`);

    try {
        let data = await readResultsFile();
        let updateCount = 0;
        linksToUpdate.forEach(link => {
            if (data.hasOwnProperty(link)) {
                if (data[link].extracted !== true) { // Only update if not already true
                    data[link].extracted = true;
                    updateCount++;
                }
            } else {
                console.warn(`Link not found for status update: ${link}`);
            }
        });

        if (updateCount > 0) {
            await writeResultsFile(data);
            console.log(`Successfully updated status for ${updateCount} items.`);
        } else {
             console.log(`No status updates needed for the provided links.`);
        }
        res.json({ success: true, message: `${updateCount} items marked as extracted.` });

    } catch (error) {
        console.error('Error updating status:', error);
        res.status(500).json({ success: false, message: error.message || 'Server error updating status.' });
    }
});


// API endpoint to trigger blog download/processing
app.post('/api/download-blog', async (req, res) => {
  const { blogUrl, title, region, keyword } = req.body;

  if (!blogUrl) {
    return res.status(400).json({ success: false, message: 'Missing required parameter: blogUrl' });
  }

  console.log(`Received download request for: ${blogUrl}`);
  console.log(`  Title: ${title || 'N/A'}, Region: ${region || 'N/A'}, Keyword: ${keyword || 'N/A'}`);

  try {
    // Call the processing function from naverBlog.js
    const result = await processBlogUrl(blogUrl, title, region, keyword);

    if (result.success) {
      console.log(`Successfully processed blog: ${blogUrl}. Folder: ${result.folderPath}`);
      res.json({ success: true, message: 'Blog processed successfully.', folderPath: result.folderPath });
    } else {
      console.error(`Failed to process blog: ${blogUrl}`);
      res.status(500).json({ success: false, message: 'Failed to process blog.', folderPath: result.folderPath });
    }
  } catch (error) {
    console.error(`Error processing blog URL ${blogUrl}:`, error);
    res.status(500).json({ success: false, message: `Server error during blog processing: ${error.message}` });
  }
});


app.listen(port, () => {
  console.log(`Server listening at http://localhost:${port}`);
});
