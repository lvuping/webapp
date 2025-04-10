import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import sharp from 'sharp';
import axios from 'axios'; // Using axios for simpler image downloads

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Converts Naver blog image URLs to their highest possible resolution.
 * @param {string} imgUrl - The original image URL.
 * @returns {string} The high-resolution image URL.
 */
function convertToHighResolution(imgUrl) {
    try {
        if (!imgUrl || typeof imgUrl !== 'string') {
            return imgUrl;
        }

        let baseUrl = imgUrl;
        let queryParams = '';
        if (imgUrl.includes('?')) {
            [baseUrl, queryParams] = imgUrl.split('?', 2);
        }

        // Naver Post images (postfiles.pstatic.net)
        if (baseUrl.includes('postfiles.pstatic.net')) {
            if (queryParams) {
                const params = new URLSearchParams(queryParams);
                const type = params.get('type');
                // If already high-res type, return original
                if (type && ['w966', 'w2', 'w1200', 'w800'].includes(type)) {
                    return imgUrl;
                }
                // Set type to w966 for high-res
                params.set('type', 'w966');
                return `${baseUrl}?${params.toString()}`;
            }
            // If no query params, return base URL (often original) or add type=w966 as fallback
            // Let's try adding type=w966 by default if no params exist, might be safer
            return `${baseUrl}?type=w966`;
        }

        // Other Naver images (blogpfthumb-phinf.pstatic.net, etc.)
        if (baseUrl.includes('pstatic.net')) {
            // Remove common size parameters from the filename part
            const urlParts = baseUrl.split('/');
            let filename = urlParts.pop() || ''; // Get last part (filename)

            // Remove size patterns like _s, _t, _m, _l, _s100 etc.
            filename = filename.replace(/_[stml]\d*(?=\.[^.]+$)/, ''); // e.g., _s100.jpg -> .jpg
            filename = filename.replace(/_[stml](?=\.[^.]+$)/, '');   // e.g., _s.jpg -> .jpg

            // Also handle type=wXXX in query params if they weren't split off earlier (less common in base URL)
            queryParams = queryParams.replace(/type=w\d+&?/, ''); // Remove type=wXXX

            const newBaseUrl = [...urlParts, filename].join('/');
            return queryParams ? `${newBaseUrl}?${queryParams}` : newBaseUrl;
        }

        // Other general URLs - return as is
        return imgUrl;
    } catch (error) {
        console.error(`Image URL conversion error for ${imgUrl}: ${error.message}`);
        return imgUrl; // Return original URL on error
    }
}

/**
 * Downloads an image from a URL and saves it.
 * @param {string} url - The image URL.
 * @param {string} folderPath - The path to the save folder.
 * @param {number} index - The image index.
 * @returns {Promise<string|null>} Path to the saved image file or null on failure.
 */
async function downloadImage(url, folderPath, index) {
    const fileName = `image_${String(index).padStart(3, '0')}.png`; // Always save as PNG
    const filePath = path.join(folderPath, fileName);
    const headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Referer": "https://blog.naver.com/",
    };

    const highResUrl = convertToHighResolution(url);
    console.log(`Attempting download (High-Res): ${highResUrl}`);

    const urlsToTry = [
        highResUrl,
        url.split('?')[0], // Original URL without query params
        url.includes('?') ? `${url.split('?')[0]}?type=w966` : `${url}?type=w966` // Force type=w966
    ];
    if (!urlsToTry.includes(url)) urlsToTry.splice(1, 0, url); // Add original URL if different

    for (const attemptUrl of [...new Set(urlsToTry)]) { // Use Set to avoid duplicate attempts
        try {
            const response = await axios.get(attemptUrl, {
                headers,
                responseType: 'arraybuffer', // Get image data as buffer
                timeout: 15000, // 15 seconds timeout
            });

            if (response.status === 200 && response.data) {
                // Use sharp to convert to PNG and save
                await sharp(response.data)
                    .png()
                    .toFile(filePath);

                const metadata = await sharp(filePath).metadata();
                console.log(`Image downloaded successfully: ${filePath} (Size: ${metadata.width}x${metadata.height})`);
                return filePath;
            }
        } catch (error) {
            console.warn(`Failed to download ${attemptUrl}: ${error.message}`);
        }
    }

    console.error(`All download attempts failed for original URL: ${url}`);
    return null;
}

/**
 * Saves content to a file.
 * @param {string} content - The content to save.
 * @param {string} folderPath - The path to the save folder.
 * @param {string} fileName - The name of the file.
 * @returns {Promise<string|null>} Path to the saved file or null on failure.
 */
async function saveToFile(content, folderPath, fileName) {
    try {
        const filePath = path.join(folderPath, fileName);
        await fs.writeFile(filePath, content, 'utf-8');
        console.log(`File saved successfully: ${filePath}`);
        return filePath;
    } catch (error) {
        console.error(`File save error (${fileName}): ${error.message}`);
        return null;
    }
}

/**
 * Extracts the structure (text and image order) from the main article content.
 * @param {import('playwright').Locator} articleLocator - Playwright locator for the article container (.se-main-container).
 * @returns {Promise<Array<{type: 'text'|'image', content: string | object}>>} The content structure.
 */
async function extractContentStructure(articleLocator) {
    return articleLocator.locator('.se-module').evaluateAll((modules) => {
        const structure = [];
        modules.forEach(module => {
            const textElement = module.querySelector('.se-text p, .se-text div'); // More robust text selection
            const imageElement = module.querySelector('.se-image img, .se-imageStrip img');

            if (textElement) {
                const text = textElement.textContent?.trim();
                if (text) {
                    structure.push({ type: 'text', content: text });
                }
            } else if (imageElement) {
                const imgUrl = imageElement.getAttribute('data-lazy-src') || imageElement.getAttribute('src');
                if (imgUrl) {
                    structure.push({
                        type: 'image',
                        content: {
                            url: imgUrl, // Keep original URL found here
                            alt: imageElement.getAttribute('alt') || '',
                            width: imageElement.getAttribute('data-width') || imageElement.width,
                            height: imageElement.getAttribute('data-height') || imageElement.height,
                        }
                    });
                }
            }
        });
        return structure;
    });
}

/**
 * Extracts image URLs in the order they appear in the article content.
 * @param {import('playwright').Locator} articleLocator - Playwright locator for the article container.
 * @returns {Promise<string[]>} Ordered list of high-resolution image URLs.
 */
async function extractOrderedImageUrls(articleLocator) {
    console.log("Extracting images in order from HTML modules...");

    const imageUrls = await articleLocator.locator('.se-module').evaluateAll((modules, convertFuncStr) => {
        // Need to pass the conversion function string and eval it inside the browser context
        const convertToHighRes = new Function(`return ${convertFuncStr}`)();
        const urls = [];
        modules.forEach(module => {
            const imgElement = module.querySelector('.se-image img, .se-imageStrip img');
            if (imgElement) {
                const imgUrl = imgElement.getAttribute('data-lazy-src') || imgElement.getAttribute('src');
                if (imgUrl) {
                    const highResUrl = convertToHighRes(imgUrl);
                    if (highResUrl && !urls.includes(highResUrl)) {
                        urls.push(highResUrl);
                    }
                }
            }
        });
        return urls;
    }, convertToHighResolution.toString()); // Pass the function code as a string

    if (imageUrls.length > 0) {
        console.log(`Found ${imageUrls.length} images in order via modules.`);
        imageUrls.forEach((url, i) => console.log(`Image ${i + 1}: ${url}`));
        return imageUrls;
    }

    // Fallback: Find all images directly within the container if module search fails
    console.log("Module search failed, falling back to direct image search...");
    const allImageUrls = await articleLocator.locator('img').evaluateAll((imgs, convertFuncStr) => {
         const convertToHighRes = new Function(`return ${convertFuncStr}`)();
         const urls = [];
         imgs.forEach(img => {
             const imgUrl = img.getAttribute('data-lazy-src') || img.getAttribute('src');
             // Basic filter for likely content images
             if (imgUrl && imgUrl.includes('pstatic.net') && !imgUrl.includes('static.map') && !imgUrl.includes('blogpfthumb')) {
                 const highResUrl = convertToHighRes(imgUrl);
                 if (highResUrl && !urls.includes(highResUrl)) {
                     urls.push(highResUrl);
                 }
             }
         });
         return urls;
    }, convertToHighResolution.toString());

    console.log(`Found ${allImageUrls.length} images in order via direct search.`);
    allImageUrls.forEach((url, i) => console.log(`Image ${i + 1}: ${url}`));
    return allImageUrls;
}


/**
 * Fixes lazy-loaded images within the HTML container in the browser context.
 * @param {import('playwright').Locator} articleLocator - Playwright locator for the article container.
 * @param {string} convertFuncStr - Stringified version of convertToHighResolution function.
 */
async function fixLazyLoadedImages(articleLocator, convertFuncStr) {
    await articleLocator.evaluate((container, convertFuncStr) => {
        const convertToHighRes = new Function(`return ${convertFuncStr}`)();
        const imgTags = container.querySelectorAll('img');
        imgTags.forEach(img => {
            const lazySrc = img.getAttribute('data-lazy-src');
            const currentSrc = img.getAttribute('src');

            if (lazySrc) {
                const highResUrl = convertToHighRes(lazySrc); // Convert the lazy source
                // If src exists and is low-res/blur, replace it with high-res
                if (currentSrc && (currentSrc.includes('blur') || /_[stml]\d*|type=w\d+/.test(currentSrc))) {
                     img.setAttribute('src', highResUrl);
                } else if (!currentSrc) {
                    // If src doesn't exist, set it
                     img.setAttribute('src', highResUrl);
                }
                 // Optionally update data-lazy-src itself to high-res if needed later
                 // img.setAttribute('data-lazy-src', highResUrl);
            } else if (currentSrc && (currentSrc.includes('blur') || /_[stml]\d*|type=w\d+/.test(currentSrc))) {
                // If no lazy-src, but src is low-res, try converting src
                const highResUrl = convertToHighRes(currentSrc);
                img.setAttribute('src', highResUrl);
            }
        });
    }, convertFuncStr);
}


/**
 * Creates a text file mapping text paragraphs and image placeholders based on content structure.
 * @param {string} text - The full article text.
 * @param {string[]} orderedImageUrls - List of ordered image URLs.
 * @param {Array<{type: 'text'|'image', content: string | object}>} contentStructure - The extracted content structure.
 * @param {string} folderPath - The path to the save folder.
 * @returns {Promise<string|null>} Path to the saved content file or null on failure.
 */
async function createImagePositionsText(text, orderedImageUrls, contentStructure, folderPath) {
    try {
        if (!text && !orderedImageUrls?.length) {
            console.warn("No text or images to create position file.");
            return null;
        }

        let resultText = "";
        const imageMap = orderedImageUrls.map((url, index) => ({
            url: url,
            filename: `image_${String(index + 1).padStart(3, '0')}.png`,
            path: path.join(folderPath, `image_${String(index + 1).padStart(3, '0')}.png`)
        }));
        let imageIndex = 0;

        console.log(`Creating positions text using content structure (items: ${contentStructure?.length || 0})`);

        if (contentStructure && contentStructure.length > 0) {
            for (const item of contentStructure) {
                if (item.type === 'text') {
                    resultText += item.content + "\n\n";
                } else if (item.type === 'image' && imageIndex < imageMap.length) {
                    const imgInfo = imageMap[imageIndex];
                    // Find the matching image in the ordered list (structure might have slightly different URLs)
                    // This assumes the structure order matches the orderedImageUrls order
                    resultText += `[이미지: ${imgInfo.filename}]\n`;
                    resultText += `[이미지 경로: ${imgInfo.path}]\n`;
                    resultText += `[원본 URL: ${imgInfo.url}]\n\n`;
                    imageIndex++;
                }
            }
             // Add any remaining images not captured by structure (less likely if structure is accurate)
             while (imageIndex < imageMap.length) {
                 const imgInfo = imageMap[imageIndex];
                 resultText += `[이미지: ${imgInfo.filename}]\n`;
                 resultText += `[이미지 경로: ${imgInfo.path}]\n`;
                 resultText += `[원본 URL: ${imgInfo.url}]\n\n`;
                 imageIndex++;
             }

        } else {
            // Fallback: Intersperse images with text paragraphs if structure is missing
            console.warn("Content structure missing or empty. Interspersing images.");
            const paragraphs = text.split('\n').map(p => p.trim()).filter(Boolean);
            const interval = Math.max(1, Math.floor(paragraphs.length / (imageMap.length + 1)));

            let currentImageIdx = 0;
            for (let i = 0; i < paragraphs.length; i++) {
                resultText += paragraphs[i] + "\n\n";
                // Place an image after every 'interval' paragraphs
                if ((i + 1) % interval === 0 && currentImageIdx < imageMap.length) {
                    const imgInfo = imageMap[currentImageIdx];
                    resultText += `[이미지: ${imgInfo.filename}]\n`;
                    resultText += `[이미지 경로: ${imgInfo.path}]\n`;
                    resultText += `[원본 URL: ${imgInfo.url}]\n\n`;
                    currentImageIdx++;
                }
            }
            // Add remaining images at the end
            while (currentImageIdx < imageMap.length) {
                 const imgInfo = imageMap[currentImageIdx];
                 resultText += `[이미지: ${imgInfo.filename}]\n`;
                 resultText += `[이미지 경로: ${imgInfo.path}]\n`;
                 resultText += `[원본 URL: ${imgInfo.url}]\n\n`;
                 currentImageIdx++;
            }
        }

        return saveToFile(resultText.trim(), folderPath, "content_with_images.txt");

    } catch (error) {
        console.error(`Error creating image positions text: ${error.message}`);
        return null;
    }
}

/**
 * Creates an HTML file containing only text and image tags from the original HTML, preserving order.
 * @param {string} htmlFilePath - Path to the original saved HTML file.
 * @param {string} folderPath - Path to the output folder.
 * @returns {Promise<string|null>} Path to the created text/image HTML file or null on failure.
 */
async function createTextImgContent(htmlFilePath, folderPath) {
    try {
        const htmlContent = await fs.readFile(htmlFilePath, 'utf-8');
        // Using cheerio as it's simpler for static HTML parsing than Playwright's evaluate
        const cheerio = await import('cheerio');
        const $ = cheerio.load(htmlContent);

        let newContent = "";
        const processedImgSrcs = new Set();
        let imgCounter = 1;

        // Select modules that contain text or images
        $('.se-module-text, .se-module-image, .se-image, .se-imageStrip').each((_, module) => {
            const $module = $(module);

            // Text: Find paragraphs within text modules
            if ($module.hasClass('se-module-text')) {
                $module.find('p, div').each((_, p) => { // Check divs too
                    const text = $(p).text().trim();
                    // Filter out zero-width spaces or empty strings
                    if (text && text !== '\u200B') {
                        newContent += `<p>${text}</p>\n`;
                    }
                });
            }
            // Image: Find images within image modules or containers
            else if ($module.hasClass('se-module-image') || $module.hasClass('se-image') || $module.hasClass('se-imageStrip')) {
                const imgElem = $module.find('img').first(); // Find the first image within
                if (imgElem.length) {
                    const src = imgElem.attr('src') || '';
                    const alt = imgElem.attr('alt') || '';

                    // Check for duplicates and valid src
                    if (src && !processedImgSrcs.has(src)) {
                        const imgTag = `<img src="${src}" alt="${alt}">\n`;
                        const imgNameTag = `{image_${String(imgCounter).padStart(3, '0')}.png}\n`; // Reference the expected filename
                        newContent += imgTag + imgNameTag;
                        processedImgSrcs.add(src);
                        imgCounter++;
                    }
                }
            }
        });

        const outputFilePath = path.join(folderPath, "text_img_content.html");
        await fs.writeFile(outputFilePath, newContent, 'utf-8');
        console.log(`Text/Image only HTML created: ${outputFilePath}`);
        return outputFilePath;

    } catch (error) {
        console.error(`Error creating text/image HTML: ${error.message}`);
        import('traceback').then(tb => tb.print_exc()); // Node doesn't have traceback directly
        return null;
    }
}

/**
 * Adds random watermarks to images in a folder.
 * @param {string} imageFolderPath - Path to the folder with images.
 * @param {string} watermarkFolderPath - Path to the folder with watermarks.
 * @returns {Promise<number>} Number of successfully watermarked images.
 */
async function addWatermarksToImages(imageFolderPath, watermarkFolderPath) {
    try {
        const imageFiles = (await fs.readdir(imageFolderPath)).filter(f => /\.(png|jpg|jpeg|webp|bmp)$/i.test(f));
        const watermarkFiles = (await fs.readdir(watermarkFolderPath)).filter(f => /\.(png|jpg|jpeg|webp|bmp)$/i.test(f));

        if (!watermarkFiles.length) {
            console.log(`No watermark images found in ${watermarkFolderPath}`);
            return 0;
        }
        if (!imageFiles.length) {
            console.log(`No images found in ${imageFolderPath}`);
            return 0;
        }

        let watermarkedCount = 0;
        for (const imgFile of imageFiles) {
            const imgPath = path.join(imageFolderPath, imgFile);
            try {
                const mainImage = sharp(imgPath);
                const metadata = await mainImage.metadata();
                const mainWidth = metadata.width;
                const mainHeight = metadata.height;

                if (!mainWidth || !mainHeight) {
                     console.warn(`Skipping ${imgFile}, could not get dimensions.`);
                     continue;
                }

                const watermarkFile = watermarkFiles[Math.floor(Math.random() * watermarkFiles.length)];
                const watermarkPath = path.join(watermarkFolderPath, watermarkFile);

                // Define corners for sharp's gravity
                const corners = ['northwest', 'northeast', 'southwest', 'southeast'];
                const corner = corners[Math.floor(Math.random() * corners.length)];

                // Calculate watermark size (e.g., 45% of the smallest dimension)
                const watermarkTargetSize = Math.min(mainWidth, mainHeight) * 0.45;

                const watermarkImage = sharp(watermarkPath);
                const watermarkMetadata = await watermarkImage.metadata();

                // Resize watermark proportionally
                const ratio = Math.min(watermarkTargetSize / watermarkMetadata.width, watermarkTargetSize / watermarkMetadata.height);
                const resizedWidth = Math.round(watermarkMetadata.width * ratio);
                const resizedHeight = Math.round(watermarkMetadata.height * ratio);

                const resizedWatermarkBuffer = await watermarkImage
                    .resize(resizedWidth, resizedHeight, { fit: 'inside' })
                    .toBuffer();

                // Composite the watermark
                const tempOutputPath = `${imgPath}.tmp`; // Save to temp file first
                await mainImage
                    .composite([{
                        input: resizedWatermarkBuffer,
                        gravity: corner, // Use sharp's gravity
                    }])
                    .toFile(tempOutputPath);

                // Replace original file
                await fs.rename(tempOutputPath, imgPath);

                watermarkedCount++;
                console.log(`Added watermark to ${imgFile} at ${corner} corner`);

            } catch (err) {
                console.error(`Error adding watermark to ${imgFile}: ${err.message}`);
                // Clean up temp file if it exists
                try { await fs.unlink(`${imgPath}.tmp`); } catch { /* ignore */ }
            }
        }
        console.log(`Successfully added watermarks to ${watermarkedCount}/${imageFiles.length} images`);
        return watermarkedCount;

    } catch (error) {
        console.error(`Error in watermarking process: ${error.message}`);
        return 0;
    }
}


/**
 * Extracts HTML content and images from a Naver blog URL using Playwright.
 * @param {string} url - The Naver blog URL.
 * @returns {Promise<object|null>} Object containing blogId, logNo, htmlContent, orderedImageUrls, textContent, contentStructure, blogTitle, or null on failure.
 */
async function extractNaverBlogData(url) {
    let browser = null;
    try {
        console.log(`Launching browser for ${url}`);
        browser = await chromium.launch({ headless: true }); // Use headless mode
        const context = await browser.newContext({
            userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            acceptDownloads: false, // We handle downloads via axios/sharp
        });
        const page = await context.newPage();

        console.log(`Navigating to ${url}`);
        await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }); // Wait for network to be idle

        // Extract blogId and logNo from URL
        let blogId = null;
        let logNo = null;
        const urlMatch = url.match(/blog\.naver\.com\/([^/]+)\/(\d+)/);
        if (urlMatch) {
            blogId = urlMatch[1];
            logNo = urlMatch[2];
            console.log(`Extracted from URL - Blog ID: ${blogId}, Post No: ${logNo}`);
        } else {
            console.warn("Could not extract blogId/logNo from URL.");
            // Attempt to extract from iframe source if needed later?
        }

        let articleLocator = null;
        let blogTitle = null;
        let pageOrFrame = page; // Start with the main page

        // Try finding the main container directly
        const mainContainerLocator = page.locator('.se-main-container').first();
        if (await mainContainerLocator.isVisible({ timeout: 5000 })) {
            console.log("Found .se-main-container in main page.");
            articleLocator = mainContainerLocator;
            // Try getting title from main page container
            const titleElement = articleLocator.locator('.se-title-text').first();
            if (await titleElement.isVisible({ timeout: 1000 })) {
                blogTitle = await titleElement.textContent();
                console.log(`Blog Title (Main Page): ${blogTitle}`);
            }
        } else {
            // If not found, try the iframe
            console.log(".se-main-container not found in main page, checking iframe#mainFrame...");
            const frameLocator = page.frameLocator('#mainFrame');
            if (frameLocator) {
                 const iframeContainerLocator = frameLocator.locator('.se-main-container').first();
                 // Wait slightly longer inside iframe potentially
                 if (await iframeContainerLocator.isVisible({ timeout: 10000 })) {
                     console.log("Found .se-main-container in iframe#mainFrame.");
                     articleLocator = iframeContainerLocator;
                     pageOrFrame = frameLocator; // Operations should target the frame now
                     // Try getting title from iframe container
                     const titleElement = articleLocator.locator('.se-title-text').first();
                     if (await titleElement.isVisible({ timeout: 1000 })) {
                         blogTitle = await titleElement.textContent();
                         console.log(`Blog Title (Iframe): ${blogTitle}`);
                     }
                 } else {
                     console.error("Could not find .se-main-container in iframe either.");
                 }
            } else {
                 console.error("Could not find iframe#mainFrame.");
            }
        }

        if (!articleLocator) {
            console.error("Failed to locate the main article content container.");
            await browser.close();
            return null;
        }

        // --- Data Extraction ---
        console.log("Extracting data from article container...");

        // 1. Fix lazy loaded images (run JS in browser)
        console.log("Fixing lazy loaded images...");
        await fixLazyLoadedImages(articleLocator, convertToHighResolution.toString());

        // 2. Extract Content Structure
        console.log("Extracting content structure...");
        const contentStructure = await extractContentStructure(articleLocator);
        console.log(`Extracted structure with ${contentStructure.length} items.`);

        // 3. Extract Ordered Image URLs (High-Res)
        console.log("Extracting ordered image URLs...");
        const orderedImageUrls = await extractOrderedImageUrls(articleLocator); // Already converts to high-res

        // 4. Extract HTML Content (after fixing images)
        console.log("Extracting HTML content...");
        const htmlContent = await articleLocator.innerHTML();

        // 5. Extract Text Content
        console.log("Extracting text content...");
        const textContent = await articleLocator.innerText();

        // 6. Extract Blog Title (if not found yet)
        if (!blogTitle) {
             const titleElement = articleLocator.locator('.se-title-text').first();
             if (await titleElement.isVisible({ timeout: 1000 })) {
                 blogTitle = await titleElement.textContent();
                 console.log(`Blog Title (Final Attempt): ${blogTitle}`);
             } else {
                 console.warn("Could not find blog title.");
                 blogTitle = "Untitled"; // Default title
             }
        }

        await browser.close();
        console.log("Browser closed.");

        return {
            blogId,
            logNo,
            htmlContent,
            orderedImageUrls,
            textContent: textContent.trim(),
            contentStructure,
            blogTitle: blogTitle?.trim() || "Untitled",
        };

    } catch (error) {
        console.error(`Error extracting blog data: ${error.message}`);
        if (browser) {
            await browser.close();
        }
        return null;
    }
}

// Placeholder for process_images module functionality
// In a real scenario, you'd import and call functions from process_images.js
async function processImagesPlaceholder(folderPath) {
    console.log(`Placeholder: Running image processing for folder: ${folderPath}`);
    // Example: Create the expected output file if it doesn't exist
    const processedFilePath = path.join(folderPath, "content_with_images_processed.txt");
    const contentFilePath = path.join(folderPath, "content_with_images.txt");
    try {
        if (!await fs.access(processedFilePath).then(() => true).catch(() => false)) {
             if (await fs.access(contentFilePath).then(() => true).catch(() => false)) {
                 const content = await fs.readFile(contentFilePath, 'utf-8');
                 await fs.writeFile(processedFilePath, `Processed:\n${content}`, 'utf-8');
                 console.log(`Created placeholder processed file: ${processedFilePath}`);
             } else {
                 console.warn(`Cannot create placeholder processed file, ${contentFilePath} missing.`);
             }
        } else {
             console.log(`Processed file already exists: ${processedFilePath}`);
        }
    } catch (error) {
        console.error(`Error in processImagesPlaceholder: ${error.message}`);
    }
}


/**
 * Processes a Naver blog URL: scrapes content, downloads images, saves files.
 * @param {string} blogUrl - The URL to process.
 * @param {string|null} [title=null] - Optional title provided externally.
 * @param {string} [region=""] - Optional region name.
 * @param {string} [keyword=""] - Optional keyword.
 * @returns {Promise<{blogId: string|null, logNo: string|null, folderPath: string|null, success: boolean}>} Result object.
 */
async function processBlogUrl(blogUrl, title = null, region = "", keyword = "") {
    const watermarkFolder = path.join(__dirname, "photo"); // Assuming 'photo' folder is in the same directory
    let watermarkFolderExists = false;
    try {
        await fs.access(watermarkFolder);
        watermarkFolderExists = true;
        console.log(`Watermark folder found: ${watermarkFolder}`);
    } catch {
        console.warn(`Watermark folder not found: ${watermarkFolder}`);
    }

    console.log(`\nProcessing Blog URL: ${blogUrl}`);
    console.log("Extracting data...");

    const blogData = await extractNaverBlogData(blogUrl);

    if (!blogData || !blogData.blogId || !blogData.logNo || !blogData.htmlContent) {
        console.error("Failed to extract essential blog data.");
        return { blogId: null, logNo: null, folderPath: null, success: false };
    }

    const {
        blogId, logNo, htmlContent, orderedImageUrls, textContent, contentStructure, blogTitle
    } = blogData;

    // --- Folder Naming ---
    const now = new Date();
    const dateStr = now.toISOString().slice(0, 16).replace(/[-T:]/g, ''); // YYYYMMDD_HHMM

    let folderName = "";
    const cleanTitle = blogTitle?.replace(/[\\/:*?"<>|]/g, '') || ''; // Sanitize title for folder name

    if (region && keyword) {
        console.log(`Using provided Region (${region}) and Keyword (${keyword}) for folder name.`);
        folderName = `[${region}]${keyword}_${blogId}_${logNo}`;
    } else {
        let location = "";
        if (cleanTitle) {
            // Try to extract location (e.g., Korean city/district name at the beginning)
            const locationMatch = cleanTitle.match(/^([가-힣]+\s*[가-힣]+)/);
            if (locationMatch) {
                location = locationMatch[1].trim();
            }
        }

        if (location) {
            let extractedKeyword = "";
            const titleWithoutLocation = cleanTitle.replace(location, '').trim();
            if (titleWithoutLocation) {
                // Try to get the first word(s) as keyword
                const keywordMatch = titleWithoutLocation.match(/^([가-힣a-zA-Z0-9\s]+)/); // Allow spaces in keyword
                 if (keywordMatch) {
                     // Take first few words, limit length
                     extractedKeyword = keywordMatch[1].trim().split(' ').slice(0, 3).join(' ');
                 }
            }
            folderName = extractedKeyword
                ? `[${location}]${extractedKeyword}_${blogId}_${logNo}`
                : `[${location}]_${blogId}_${logNo}`;
        } else {
            // Fallback using date and potentially part of the title
            const titlePart = cleanTitle.substring(0, 20).trim() || 'NoTitle';
            folderName = `${dateStr}_${titlePart}_${blogId}_${logNo}`;
        }
    }
    // Ensure folder name is valid
    folderName = folderName.replace(/[\\/:*?"<>|]/g, '_').substring(0, 150); // Sanitize and limit length
    const folderPath = path.join(process.cwd(), folderName);

    // --- File Operations ---
    try {
        await fs.mkdir(folderPath, { recursive: true });
        console.log(`Folder created: ${folderPath}`);

        // Save Title
        const finalTitle = title || blogTitle || 'Untitled';
        await saveToFile(finalTitle, folderPath, "title.txt");

        // Save Original HTML
        const htmlFile = await saveToFile(htmlContent, folderPath, "original_content.html");

        // Download Images
        let downloadedFiles = [];
        if (orderedImageUrls && orderedImageUrls.length > 0) {
            console.log(`\nDownloading ${orderedImageUrls.length} images...`);
            const downloadPromises = orderedImageUrls.map((imgUrl, i) =>
                downloadImage(imgUrl, folderPath, i + 1)
                    .then(filePath => {
                        if (filePath) downloadedFiles.push(filePath);
                        // Add slight delay between starting downloads to avoid overwhelming server
                        return new Promise(resolve => setTimeout(resolve, 100 * i));
                    })
            );
            await Promise.all(downloadPromises);
            console.log(`\nImage download complete: ${downloadedFiles.length}/${orderedImageUrls.length} successful.`);

            // Add Watermarks
            if (watermarkFolderExists && downloadedFiles.length > 0) {
                console.log("\nAdding watermarks to downloaded images...");
                const watermarkedCount = await addWatermarksToImages(folderPath, watermarkFolder);
                console.log(`Watermark addition complete: ${watermarkedCount}/${downloadedFiles.length} successful.`);
            }
        } else {
            console.log("\nNo images found or extracted to download.");
        }

        // Create Image Positions Text File
        if (textContent || (orderedImageUrls && orderedImageUrls.length > 0)) {
            console.log("\nCreating text and image position file...");
            await createImagePositionsText(textContent, orderedImageUrls, contentStructure, folderPath);
        }

        // Create Text/Image Only HTML
        if (htmlFile) {
            console.log("\nCreating text/image only HTML file...");
            await createTextImgContent(htmlFile, folderPath);
        }

        // Process Images (Placeholder)
        console.log("\nProcessing images and creating final content file (placeholder)...");
        await processImagesPlaceholder(folderPath); // Replace with actual call if module exists

        console.log(`\nProcessing complete. Output folder: ${folderPath}`);
        return { blogId, logNo, folderPath, success: true };

    } catch (error) {
        console.error(`Error during file operations for ${folderPath}: ${error.message}`);
        return { blogId, logNo, folderPath, success: false };
    }
}

/**
 * Processes an existing blog folder: adds watermarks, creates derived files.
 * @param {string} folderPath - Path to the folder to process.
 * @returns {Promise<boolean>} Success status.
 */
async function processBlogFolder(folderPath) {
     const watermarkFolder = path.join(__dirname, "photo");
     const htmlFilePath = path.join(folderPath, "original_content.html");

     try {
         await fs.access(folderPath); // Check if folder exists
     } catch {
         console.error(`Error: Folder does not exist: ${folderPath}`);
         return false;
     }

     try {
         await fs.access(htmlFilePath); // Check if HTML file exists
     } catch {
         console.error(`Error: HTML file does not exist: ${htmlFilePath}`);
         // Decide if processing can continue without HTML (e.g., just watermarking)
         // For now, let's assume HTML is needed for some steps.
         // return false; // Or proceed with caution
         console.warn(`Warning: HTML file missing, some steps might be skipped.`);
     }

     try {
         // Add Watermarks (if watermark folder exists)
         let watermarkFolderExists = false;
         try {
             await fs.access(watermarkFolder);
             watermarkFolderExists = true;
         } catch { /* ignore */ }

         if (watermarkFolderExists) {
             console.log("\nAdding watermarks to images...");
             const imageFiles = (await fs.readdir(folderPath)).filter(f => /\.(png|jpg|jpeg|webp|bmp)$/i.test(f));
             if (imageFiles.length > 0) {
                 const watermarkedCount = await addWatermarksToImages(folderPath, watermarkFolder);
                 console.log(`Watermark addition complete: ${watermarkedCount} successful.`);
             } else {
                 console.log("No images found in folder to watermark.");
             }
         } else {
              console.log("Watermark folder not found, skipping watermarking.");
         }

         // Create Text/Image Only HTML (if original HTML exists)
         if (await fs.access(htmlFilePath).then(() => true).catch(() => false)) {
             console.log("\nCreating text/image only HTML file...");
             await createTextImgContent(htmlFilePath, folderPath);
         } else {
             console.log("Original HTML missing, skipping text/image HTML creation.");
         }

         // Process Images (Placeholder)
         console.log("\nProcessing images and creating final content file (placeholder)...");
         await processImagesPlaceholder(folderPath); // Replace with actual call

         // Check if processed file exists
         const processedFilePath = path.join(folderPath, "content_with_images_processed.txt");
         if (await fs.access(processedFilePath).then(() => true).catch(() => false)) {
             console.log(`\nFolder processing complete. Check folder: ${folderPath}`);
             return true;
         } else {
             console.warn(`Warning: Processed file was not created: ${processedFilePath}`);
             return false; // Indicate potential issue
         }

     } catch (error) {
         console.error(`Error processing folder ${folderPath}: ${error.message}`);
         import('traceback').then(tb => tb.print_exc());
         return false;
     }
}


// --- Main Execution ---
(async () => {
    const args = process.argv.slice(2);

    if (args.length > 0) {
        const param = args[0];
        try {
            const stats = await fs.stat(param);
            if (stats.isDirectory()) {
                console.log(`Folder processing mode: ${param}`);
                await processBlogFolder(param);
            } else {
                // Assume it's a file path or something else unexpected if not a URL
                 console.error(`Parameter is a file, not a directory or URL: ${param}`);
                 console.log("Usage: node naverBlog.js [URL | FOLDER_PATH]");
            }
        } catch (error) {
            // If fs.stat fails, assume it's a URL or invalid path
            if (param.startsWith('http')) {
                console.log(`URL processing mode: ${param}`);
                await processBlogUrl(param);
            } else {
                console.error(`Invalid parameter or path does not exist: ${param}`);
                console.log("Usage: node naverBlog.js [URL | FOLDER_PATH]");
            }
        }
    } else {
        // Default example URL
        const defaultBlogUrl = "https://blog.naver.com/hot9676/223749658381"; // Replace with a valid test URL if needed
        console.log(`No arguments provided, using default example URL: ${defaultBlogUrl}`);
        await processBlogUrl(defaultBlogUrl);
    }
})();
