import { chromium } from 'playwright';

async function scrapeNaverBlog(keyword, city, fromDate, toDate, scrollCount) {
    const encodedKeyword = encodeURIComponent(keyword + ' ' + city);
    const baseUrl = "https://search.naver.com/search.naver?ssc=tab.blog.all";
    const url = `${baseUrl}&query=${encodedKeyword}&sm=tab_opt&nso=so%3Ar%2Cp%3Afrom${fromDate}to${toDate}`;

    console.log(`1. URL 접속 시도: ${url}`);

    const browser = await chromium.launch();
    const page = await browser.newPage();

    try {
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
        return [];
    } finally {
        await browser.close();
    }
}

// Example usage (you would call this function with the appropriate parameters)
scrapeNaverBlog("보일러수리", "원주", "2020.01.01", "2021.01.01", 5).then(data => console.log(JSON.stringify(data, null, 2)));

// import { extractNaverBlogContent } from './naverBlog.js'; // Added .js extension

// export { scrapeNaverBlog, extractNaverBlogContent };
