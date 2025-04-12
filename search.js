import { chromium } from 'playwright';
import fs from 'fs'; // Import fs module
import path from 'path'; // Import path module
import { fileURLToPath } from 'url'; // Needed to check for direct execution

async function scrapeNaverBlog(keyword, city, fromDate, toDate, scrollCount) {
    // Determine if the script is being run directly or imported
    const currentFilePath = fileURLToPath(import.meta.url);
    const mainScriptPath = process.argv[1];
    const isDirectRun = currentFilePath === mainScriptPath;
    const launchOptions = { headless: !isDirectRun }; // Headless = true if imported, false if run directly

    const encodedKeyword = encodeURIComponent(keyword + ' ' + city);
    const baseUrl = "https://search.naver.com/search.naver?ssc=tab.blog.all";
    const url = `${baseUrl}&query=${encodedKeyword}&sm=tab_opt&nso=so%3Ar%2Cp%3Afrom${fromDate}to${toDate}`;

    console.log(`1. URL 접속 시도: ${url}`);

    let browser; // Declare browser outside try
    let page;    // Declare page outside try

    try {
        // Launch with determined options
        console.log(`Launching browser (Headless: ${launchOptions.headless})`);
        browser = await chromium.launch(launchOptions);
        page = await browser.newPage();    // Move page creation inside try

        await page.goto(url);

        console.log("2. 페이지 로딩 대기 시작");
        await page.waitForSelector(
            "#main_pack > section > div.api_subject_bx > ul > li:nth-child(1)",
            { timeout: 20000 }
        );
        console.log("3. 페이지 로딩 완료");

        console.log(`4. 스크롤 시작 (총 ${scrollCount}회)`);
        for (let i = 0; i < scrollCount; i++) {
            await page.evaluate("window.scrollBy(0, 1500)");
            await page.waitForTimeout(500); // Increased wait time
            console.log(`   스크롤 ${i + 1}/${scrollCount} 완료`);
        }

        await page.waitForTimeout(2000);

        console.log("\n5. 현재 페이지의 HTML 구조 확인");
        const pageContent = await page.content();
        const firstBlogElement = pageContent.indexOf(
            "#main_pack > section > div.api_subject_bx > ul > li:nth-child(1) > div > div.detail_box > div.title_area > a"
        );
        console.log("첫 번째 블로그 영역:", firstBlogElement);

        const blogs = await page.$$("li.bx");
        console.log(`\n6. 찾은 블로그 수: ${blogs.length}`);

        const items = [];

        for (let idx = 0; idx < blogs.length; idx++) {
            try {
                const blog = blogs[idx];
                const titleElem = await blog.$(".title_link");

                const title = titleElem ? await titleElem.innerText() : "";
                const link = titleElem ? await titleElem.getAttribute("href") : "";

                if (title.includes(keyword)) {
                    items.push({
                        title: title,
                        link: link,
                        city: city,
                        keyword: keyword,
                        fromDate: fromDate,
                        toDate: toDate,
                        extracted: false, // Add default extracted status
                    });
                    console.log(`✓ 블로그 추가 성공: ${title.substring(0, 20)}...`);
                } else {
                    console.log(
                        `× 제외된 블로그: ${title.substring(0, 20)}... (키워드 '${keyword}' 없음)`
                    );
                }
            } catch (e) {
                console.log(`× 블로그 ${idx + 1} 처리 중 에러: ${String(e)}`);
                continue;
            }
        }

        console.log(`\n7. 총 수집된 블로그 수: ${items.length}`);

        return items;
    } catch (e) {
        console.log(`치명적 에러 발생: ${String(e)}`);
        console.log("데이터 수집 실패");
        // Ensure browser is closed even if page creation failed but launch succeeded
        if (browser && browser.isConnected()) await browser.close();
        return []; // Return empty array on error
    } finally {
        // Ensure browser is closed if it was successfully launched and connected
        // The catch block handles closing on error now.
        // This finally block ensures closure on successful completion.
        if (browser && browser.isConnected()) {
             await browser.close();
        }
    }
}

// Function to save data to a single JSON file, using link as key
function saveDataToJson(newData) {
    if (!newData || newData.length === 0) {
        console.log("No new data collected, skipping file save.");
        return;
    }

    // Define the single file path
    const resultDir = path.join(process.cwd(), 'result');
    const filePath = path.join(resultDir, 'search_results.json');

    let existingData = {};

    try {
        // Ensure result directory exists
        if (!fs.existsSync(resultDir)) {
            fs.mkdirSync(resultDir, { recursive: true });
            console.log(`Created directory: ${resultDir}`);
        }

        // Read existing data if file exists
        if (fs.existsSync(filePath)) {
            try {
                const fileContent = fs.readFileSync(filePath, 'utf8');
                existingData = JSON.parse(fileContent);
                // Basic validation: check if it's an object
                if (typeof existingData !== 'object' || existingData === null || Array.isArray(existingData)) {
                    console.warn(`Warning: Existing file ${filePath} does not contain a valid JSON object. Starting fresh.`);
                    existingData = {};
                }
            } catch (parseError) {
                console.error(`Error parsing existing JSON file ${filePath}: ${parseError}. Starting fresh.`);
                existingData = {}; // Reset if parsing fails
            }
        }

        // Add or update new data using link as the key
        newData.forEach(item => {
            if (item && item.link) { // Ensure item and link exist
                existingData[item.link] = item; // Add or overwrite entry
            } else {
                console.warn("Skipping item due to missing link:", item);
            }
        });

        // Write the updated data back to the file
        fs.writeFileSync(filePath, JSON.stringify(existingData, null, 2), 'utf8');
        console.log(`\n✅ Data successfully saved/updated in: ${filePath}`);

    } catch (error) {
        console.error(`\n❌ Error saving data to file ${filePath}: ${error}`);
    }
}

export { scrapeNaverBlog, saveDataToJson };


// --- Direct Execution Block for Testing ---
const currentFilePathForCheck = fileURLToPath(import.meta.url);
const mainScriptPathForCheck = process.argv[1];
if (currentFilePathForCheck === mainScriptPathForCheck) {
    console.log("\n--- Running search.js directly for testing ---");
    // Define test parameters (Use YYYYMMDD format for dates)
    const testKeyword = "캠핑";
    const testCity = "가평";
    const testFromDate = "20250401";
    const testToDate = "20250410";
    const testScrollCount = 1;

    (async () => {
        console.log(`Running test scrape: Keyword="${testKeyword}", City="${testCity}", From=${testFromDate}, To=${testToDate}, Scrolls=${testScrollCount}`);
        try {
            const results = await scrapeNaverBlog(testKeyword, testCity, testFromDate, testToDate, testScrollCount);
            console.log(`\n--- Test Run Complete ---`);
            console.log(`Found ${results.length} items.`);
            // Save test results to the consolidated file
            if (results.length > 0) {
                 saveDataToJson(results); // No need for keyword/city in filename anymore
            }
        } catch (error) {
            console.error("\n--- Test Run Failed ---");
            console.error("Error during direct execution:", error);
        }
    })();
}
