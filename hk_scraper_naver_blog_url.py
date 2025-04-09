import pandas as pd
from playwright.sync_api import sync_playwright
import datetime
import time
from dotenv import load_dotenv
import os
import urllib.parse
import sys

# Import custom browser configuration if available
try:
    import custom_naver_browser
    browser_configured = custom_naver_browser.setup_browser_paths()
except ImportError:
    browser_configured = False
    # Fallback - in PyInstaller environment, set browser path to system browser
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = '0'
        print("Running in PyInstaller environment without custom browser module. Setting PLAYWRIGHT_BROWSERS_PATH=0")

# Load environment variables
load_dotenv()


# 1. 네이버 블로그 데이터 수집 --------------------------------------------
def get_naver_blog(city, keyword, from_date, to_date, scroll_count=10):
    """네이버 블로그에서 키워드로 검색하여 결과 수집"""
    # 인코딩된 검색어 준비
    search_keyword = city + " " + keyword
    encoded_keyword = urllib.parse.quote(search_keyword)
    items = []
    context = None

    # 현재 시간 출력
    print(
        f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 검색 시작: {search_keyword}"
    )

    with sync_playwright() as p:
        try:
            # 화면 크기 가져오기 및 창 위치/크기 설정
            screen_width = 1920  # 일반적인 FHD 해상도 기준
            window_width = screen_width // 2  # 화면 너비의 절반

            # 브라우저 시작 전 디버그 정보 출력
            print(f"Chromium executable path: {p.chromium.executable_path}")
            
            # 브라우저 실행 (persistent context 사용)
            context = p.chromium.launch_persistent_context(
                user_data_dir="",  # 임시 디렉토리 사용
                headless=False,
                viewport={"width": window_width, "height": 1080},
                args=[
                    f"--window-position={window_width},0",
                    f"--window-size={window_width},1080",
                ],
            )
            page = context.new_page()

            # JavaScript 설정을 통한 웹드라이버 감지 우회
            page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });
            """
            )

            # 페이지 접속
            url = f"https://search.naver.com/search.naver?ssc=tab.blog.all&query={encoded_keyword}&sm=tab_opt&nso=so%3Ar%2Cp%3Afrom{from_date}to{to_date}"
            print(f"1. URL 접속 시도: {url}")
            page.goto(url)

            # 페이지 로딩 대기
            print("2. 페이지 로딩 대기 시작")
            page.wait_for_selector(
                "#main_pack > section > div.api_subject_bx > ul > li:nth-child(1)",
                timeout=20000,
            )
            print("3. 페이지 로딩 완료")

            # 스크롤 처리
            print(f"4. 스크롤 시작 (총 {scroll_count}회)")
            for i in range(scroll_count):
                page.evaluate("window.scrollBy(0, 1500)")
                time.sleep(0.5)  # 스크롤 후 대기 시간 증가
                print(f"   스크롤 {i+1}/{scroll_count} 완료")

            # 상품 정보 수집 전 추가 대기
            time.sleep(2)

            # 디버깅을 위한 페이지 내용 출력
            print("\n5. 현재 페이지의 HTML 구조 확인")
            page_content = page.content()
            print(
                "첫 번째 블로그 영역:",
                page_content.find(
                    "#main_pack > section > div.api_subject_bx > ul > li:nth-child(1) > div > div.detail_box > div.title_area > a"
                ),
            )

            # 상품 목록 확인
            blogs = page.query_selector_all("li.bx")
            print(f"\n6. 찾은 블로그 수: {len(blogs)}")

            for idx, blog in enumerate(blogs, 1):
                try:
                    # 각 요소 찾기 - 제목과 링크만 추출
                    title_elem = blog.query_selector(".title_link")

                    # title과 link 추출
                    title = title_elem.inner_text() if title_elem else ""
                    link = title_elem.get_attribute("href") if title_elem else ""

                    # 키워드가 타이틀에 포함되어 있는지 확인
                    if keyword in title:
                        # 각 항목에 지역, 키워드, 시작일, 종료일도 추가
                        items.append([title, link, city, keyword, from_date, to_date])
                        print(f"✓ 블로그 추가 성공: {title[:20]}...")
                    else:
                        print(
                            f"× 제외된 블로그: {title[:20]}... (키워드 '{keyword}' 없음)"
                        )

                except Exception as e:
                    print(f"× 블로그 {idx} 처리 중 에러: {str(e)}")
                    continue

            print(f"\n7. 총 수집된 블로그 수: {len(items)}")

            if items:
                # 컬럼명도 변경하여 블로그명을 제목으로 표시
                return pd.DataFrame(
                    items,
                    columns=["제목", "링크", "지역", "키워드", "시작일", "종료일"],
                )
            else:
                print("수집된 블로그가 없습니다.")
                return pd.DataFrame()

        except Exception as e:
            print(f"치명적 에러 발생: {str(e)}")
            print("데이터 수집 실패")
            return pd.DataFrame()
        finally:
            if context:  # context가 존재할 때만 close 호출
                context.close()


# 2. 엑셀 파일 저장 ----------------------------------------------------
def save_to_excel(df, filename, search_keyword):
    # 누락된 값 처리
    df = df.fillna("")  # 누락된 값을 빈 문자열로 대체

    # 중복 제거
    df = df.drop_duplicates()

    # 빈 문자열이 있는 행 제거
    df = df[df["블로그명"].str.strip() != ""]
    df = df[df["링크"].str.strip() != ""]

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{filename}_{search_keyword}_{timestamp}.xlsx"
    df.to_excel(filename, index=False)
    return filename


# 메인 실행 -------------------------------------------------------------
if __name__ == "__main__":
    # 테스트용 기본값
    city = input("검색할 지역를 입력하세요: ")
    keyword = input("검색할 키워드를 입력하세요: ")
    from_date = input("검색 시작일을 입력하세요 (YYYYMMDD 형식): ")
    to_date = input("검색 종료일을 입력하세요 (YYYYMMDD 형식): ")

    search_keyword = city + " " + keyword
    df = get_naver_blog(city, keyword, from_date, to_date)

    if not df.empty:
        filename = save_to_excel(df, "naver_blog_result", search_keyword)
        print(f"{len(df)}개 데이터 수집 완료! 파일명: {filename}")
    else:
        print("데이터 수집 실패")
