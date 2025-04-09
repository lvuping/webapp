from playwright.sync_api import sync_playwright, expect
import time
import os
import re  # 정규표현식 사용을 위해 추가
import markdown
import platform
import pandas as pd  # 엑셀 파일 처리를 위해 pandas 추가
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


def markdown_to_naver_html(markdown_text):
    """마크다운 텍스트를 네이버 블로그에 맞는 HTML로 변환"""

    # ```markdown 및 ``` 태그 제거
    # 먼저 ```markdown 형식 제거
    markdown_text = re.sub(r"```markdown\n", "", markdown_text)
    # 그 다음 ```language 형식 제거
    markdown_text = re.sub(r"```[a-zA-Z0-9_]*\n", "", markdown_text)
    # 마지막으로 닫는 ``` 제거
    markdown_text = re.sub(r"```\n?", "", markdown_text)

    # 기본 마크다운 -> HTML 변환
    html = markdown.markdown(markdown_text, extensions=["extra"])

    # 네이버 블로그 스타일에 맞게 변환

    # 1. 제목 변환
    html = re.sub(
        r"<h1>(.*?)</h1>",
        r'<div class="se-module se-module-text"><p class="se-text-paragraph se-text-paragraph-align-center"><span style="font-size: 24px;"><strong>\1</strong></span></p></div>',
        html,
    )

    html = re.sub(
        r"<h2>(.*?)</h2>",
        r'<div class="se-module se-module-text"><p class="se-text-paragraph"><span style="font-size: 20px;"><strong>\1</strong></span></p></div>',
        html,
    )

    html = re.sub(
        r"<h3>(.*?)</h3>",
        r'<div class="se-module se-module-text"><p class="se-text-paragraph"><span style="font-size: 18px;"><strong>\1</strong></span></p></div>',
        html,
    )

    # 2. 인용구 변환
    html = re.sub(
        r"<blockquote>(.*?)</blockquote>",
        r'<div class="se-component-content"><div class="se-section se-section-quotation se-l-quotation_line"><blockquote class="se-quotation-container"><div class="se-module se-module-text se-quote"><p class="se-text-paragraph">\1</p></div></blockquote></div></div>',
        html,
    )

    # 3. 일반 텍스트 단락 변환
    html = re.sub(
        r"<p>(.*?)</p>",
        r'<div class="se-module se-module-text"><p class="se-text-paragraph">\1</p></div>',
        html,
    )

    # 4. 수평선 변환
    html = re.sub(
        r"<hr />",
        r'<div class="se-module se-module-horizontalLine"><hr class="se-hr"></div>',
        html,
    )

    # 5. 목록 변환 (간단한 형태)
    html = re.sub(
        r"<ul>(.*?)</ul>",
        r'<div class="se-module se-module-text"><ul class="se-list">\1</ul></div>',
        html,
    )

    html = re.sub(
        r"<ol>(.*?)</ol>",
        r'<div class="se-module se-module-text"><ol class="se-list">\1</ol></div>',
        html,
    )

    # 6. 이미지 변환 (기본형)
    html = re.sub(
        r'<img src="(.*?)" alt="(.*?)" />',
        r'<div class="se-module se-module-image"><a class="se-module-image-link"><img src="\1" alt="\2" class="se-image-resource"></a></div>',
        html,
    )

    # 7. 외부 URL 링크 변환 (og:link 형식)
    # 링크 패턴 찾기 - 이미 변환된 <a> 태그 중 class가 없는 것을 찾음
    url_pattern = r'<a href="(https?://[^"]+)"(?! class=)[^>]*>(.*?)</a>'

    # 링크를 네이버 블로그 OG 링크 컴포넌트로 변환
    def replace_with_oglink(match):
        url = match.group(1)
        title = match.group(2)
        # 일반 텍스트 링크는 그대로 두고 [표시텍스트](URL) 형식으로 된 링크만 변환
        if title != url:
            return f"""
<div class="se-component se-oglink se-l-default __se-component">
    <div class="se-component-content">
        <div class="se-section se-section-oglink se-l-default se-section-align-left">
            <div class="se-module se-module-oglink">
                <a href="{url}" class="se-oglink-info __se_link" target="_blank" data-linkdata="{{&quot;link&quot;: &quot;{url}&quot;}}">
                    <div class="se-oglink-info-container">
                        <strong class="se-oglink-title">{title}</strong>
                        <p class="se-oglink-url">{url}</p>
                    </div>
                </a>
            </div>
        </div>
    </div>
</div>
"""
        else:
            # URL만 있는 경우 일반 링크로 유지
            return f'<a href="{url}" target="_blank">{title}</a>'

    html = re.sub(url_pattern, replace_with_oglink, html)

    # 8. 문단 구분 처리 (빈 줄 -> 문단 구분)
    # 연속된 div 태그 사이에 빈 줄 추가
    html = re.sub(r"</div>\s*<div", r"</div><br><div", html)

    return html


def write_naver_blog(markdown_content=None, folder_path=None, location=None):
    """
    네이버 블로그에 포스팅하는 함수

    Args:
        markdown_content (str, optional): 마크다운 형식의 콘텐츠. Defaults to None.
        folder_path (str, optional): 포스팅할 콘텐츠가 있는 폴더 경로. Defaults to None.
        location (str, optional): 변경할 지역명. Defaults to None.

    Returns:
        bool: 포스팅 성공 여부

    Raises:
        ValueError: 필수 파라미터가 누락되었거나 파일이 존재하지 않는 경우
    """
    print(
        f"Starting blog posting process with folder_path: {folder_path}, location: {location}"
    )

    # folder_path가 주어지지 않은 경우 에러 처리
    if folder_path is None:
        raise ValueError("folder_path must be provided")

    # folder_path가 문자열이 아닌 경우 문자열로 변환
    folder_path = str(folder_path)
    print(f"Converted folder_path to string: {folder_path}")

    # folder_path가 절대 경로인지 확인
    if not os.path.isabs(folder_path):
        # 상대 경로인 경우 현재 스크립트 위치 기준으로 절대 경로로 변환
        folder_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), folder_path
        )
        print(f"Converted to absolute path: {folder_path}")

    # 폴더가 존재하는지 확인
    if not os.path.exists(folder_path):
        raise ValueError(f"Folder does not exist: {folder_path}")
    print(f"Folder exists: {folder_path}")

    # 필수 파일들이 존재하는지 확인
    title_file_path = os.path.join(folder_path, "title.txt")
    output_md_path = os.path.join(folder_path, "output.md")

    if not os.path.exists(title_file_path):
        raise ValueError(f"Title file not found: {title_file_path}")
    if not os.path.exists(output_md_path):
        raise ValueError(f"Output markdown file not found: {output_md_path}")

    print(f"Required files found in folder: {folder_path}")

    # 운영체제에 따른 단축키 지정
    is_macos = platform.system() == "Darwin"
    print(f"Operating system: {'macOS' if is_macos else 'Windows'}")

    # 단축키 정의
    if is_macos:
        bold_key = "Meta+b"  # Meta = Command on macOS
        italic_key = "Meta+i"
        blockquote_start_key = "Meta+Alt+q"  # 인용구 시작
        blockquote_end_key = "Meta+Alt+h"  # 인용구 종료
    else:
        bold_key = "Control+B"
        italic_key = "Control+I"
        blockquote_start_key = "Control+Alt+Q"
        blockquote_end_key = "Control+Alt+H"

    # 마크다운을 네이버 블로그 HTML로 변환
    html_content = markdown_to_naver_html(markdown_content)

    with sync_playwright() as p:
        try:
            # 브라우저 실행 설정
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            print("Launching browser...")

            # 브라우저 시작 전 디버그 정보 출력
            print(f"Chromium executable path: {p.chromium.executable_path}")
            
            browser = p.chromium.launch(
                headless=False,
                slow_mo=100,
            )

            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                permissions=["geolocation"],
                java_script_enabled=True,
                is_mobile=False,
                has_touch=False,
            )

            page = context.new_page()
            print("Browser launched successfully")

            # 현재 업로드할 이미지 경로 변수
            current_image_path = None

            # 파일 선택기 이벤트 핸들러 설정
            def handle_file_chooser(file_chooser):
                print("File chooser detected")
                if current_image_path and os.path.exists(current_image_path):
                    image_path = current_image_path
                else:
                    image_path = os.path.join(folder_path, "image_001.png")
                print(f"Selected image path: {image_path}")
                file_chooser.set_files(image_path)

            page.on("filechooser", handle_file_chooser)

            # 네이버 블로그 접속
            print("Navigating to Naver blog...")
            page.goto("https://blog.naver.com/lvup-")
            page.wait_for_load_state("networkidle")

            # iframe으로 정확하게 접근
            main_frame = page.frame("mainFrame")
            if not main_frame:
                raise ValueError("Could not find mainFrame")

            # 이미 로그인되어 있는지 확인
            already_logged_in = False
            try:
                write_button = main_frame.get_by_role("link", name="글쓰기")
                if write_button.count() > 0:
                    print("Already logged in")
                    already_logged_in = True
            except Exception as e:
                print(f"Login status check error: {e}")
                already_logged_in = False

            # 로그인이 필요한 경우에만 로그인 진행
            if not already_logged_in:
                print("Logging in...")
                main_frame.get_by_role("link", name="로그인").click()
                page.get_by_role("textbox", name="아이디 또는 전화번호").click()
                page.get_by_role("textbox", name="아이디 또는 전화번호").fill(
                    "eastkim64"
                )
                page.get_by_role("textbox", name="아이디 또는 전화번호").press("Tab")
                page.get_by_role("textbox", name="비밀번호").fill("gusl@()%")
                page.locator("#log\\.login").click()
                page.wait_for_load_state("networkidle")
                main_frame = page.frame("mainFrame")
                print("Login completed")


            page.pause()
            page.goto("https://cafe.naver.com/ca-fe/cafes/12175294/articles/write?boardType=L")
            page.get_by_role("button", name="게시판을 선택해 주세요").click()
            page.get_by_role("button", name="회원사진첩").click()
            page.get_by_role("textbox", name="제목을 입력해 주세요").click()
            page.get_by_role("textbox", name="제목을 입력해 주세요").fill("제목 테스트")
            page.get_by_role("paragraph").filter(has_text="내용을 입력하세요").click()
            page.keyboard.type("test")
            page.get_by_role("button", name="임시등록").click()

            # 글쓰기 링크 클릭
            print("Clicking write button...")
            main_frame.get_by_role("link", name="글쓰기").click()
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # iframe 접근 시도
            editor_frame = page.frame("mainFrame")
            if not editor_frame:
                raise ValueError("Could not find editor frame")

            # 제목과 본문 입력
            if editor_frame:
                try:
                    # 작성중인글 확인 및 취소
                    try:
                        popup_cancel = editor_frame.get_by_role(
                            "button", name="취소", exact=True
                        )
                        if popup_cancel.count() > 0:
                            print(
                                "Found 'writing in progress' popup, clicking cancel button"
                            )
                            popup_cancel.click()
                            time.sleep(1)
                    except Exception as e:
                        print(f"No writing in progress popup detected: {e}")

                    # 제목 입력
                    print("Reading title file...")
                    with open(title_file_path, "r", encoding="utf-8") as title_file:
                        title_content = title_file.read().strip()
                    print(f"Title content: {title_content}")
                    title_text_element = editor_frame.get_by_text("제목", exact=True)
                    if title_text_element.count() > 0:
                        title_text_element.click()
                        page.keyboard.type(title_content)
                        page.keyboard.press("Enter")
                        print("Title entered successfully")
                        time.sleep(1)

                    # 본문 입력
                    print("Reading content file...")
                    with open(output_md_path, "r", encoding="utf-8") as output_file:
                        body_content = output_file.read()
                    print("Content file read successfully")
                    
                    # 첫줄에 "---"로 시작하는 문구가 있으면 제거 (예: "---변경된 글 ([오산]누수탐지_witch172_223709101360)")
                    body_content = re.sub(r'^---.*?\n', '', body_content, count=1, flags=re.MULTILINE)
                    print("Removed metadata line if present")

                    # 본문 입력 처리
                    body_text_element = editor_frame.get_by_text(
                        "본문에 #을 이용하여 태그를 사용해보세요! (최대 30개)",
                        exact=True,
                    )
                    if body_text_element.count() > 0:
                        body_text_element.click()
                        page.keyboard.press("Control+Alt+C")
                        time.sleep(0.5)

                        # 본문 내용 처리
                        lines = body_content.split("\n")
                        for line in lines:
                            # 이미지 태그 확인
                            image_match = re.search(
                                r"\{(image_\d+\.(?:png|jpg|jpeg|gif))\}", line
                            )
                            if image_match:
                                image_filename = image_match.group(1)
                                print(f"Found image tag: {image_filename}")

                                current_image_path = os.path.join(
                                    folder_path,
                                    image_filename,
                                )

                                if os.path.exists(current_image_path):
                                    image_button = editor_frame.locator(
                                        ".se-toolbar-item-image"
                                    )
                                    if image_button.count() > 0:
                                        image_button.click()
                                        print(
                                            f"Image button clicked for {image_filename}"
                                        )
                                        time.sleep(1.5)
                                else:
                                    print(
                                        f"Warning: Image file not found: {current_image_path}"
                                    )
                                    page.keyboard.press("Enter")
                            else:
                                # 마크다운 문법 처리
                                # 제목(Heading) 처리 (# text)
                                heading_match = re.match(
                                    r"^(#{1,6})\s+(.+)$", line.strip()
                                )
                                if heading_match:
                                    heading_level = len(heading_match.group(1))
                                    heading_text = heading_match.group(2)

                                    # 제목 크기에 따른 폰트 크기 설정
                                    if heading_level == 1:
                                        # 제목1 (H1) - 굵게 처리
                                        page.keyboard.press(bold_key)
                                        # 텍스트 크기를 늘리는 단축키가 있다면 여기서 사용
                                        # 네이버 에디터에서 폰트 크기 키보드 단축키가 없으면 툴바를 사용해야 함
                                        # 여기서는 기본적으로 굵게만 처리
                                        page.keyboard.type(heading_text)
                                        page.keyboard.press(bold_key)
                                    elif heading_level == 2:
                                        # 제목2 (H2)
                                        page.keyboard.press(bold_key)
                                        page.keyboard.type(heading_text)
                                        page.keyboard.press(bold_key)
                                    else:
                                        # 제목3 이상 (H3-H6)
                                        page.keyboard.press(bold_key)
                                        page.keyboard.type(heading_text)
                                        page.keyboard.press(bold_key)

                                    # 줄바꿈 추가
                                    page.keyboard.press("Enter")

                                # 인용구 처리 (> text)
                                elif line.strip().startswith(">"):
                                    # 인용구 처리
                                    # > 기호 제거하고 텍스트만 추출
                                    quote_text = line.strip()[1:].strip()

                                    # 인용구 단축키 Ctrl+Alt+Q 누르기 (macOS 환경에 관계없이 원래 단축키 사용)
                                    page.keyboard.press("Control+Alt+Q")
                                    time.sleep(0.5)

                                    # 인용구 내용 입력
                                    page.keyboard.type(quote_text)

                                    # 인용구 종료
                                    page.keyboard.press("Control+Alt+H")

                                else:
                                    # 멀티라인 굵은 텍스트 처리를 위한 상태 변수
                                    global bold_mode_active
                                    global italic_mode_active

                                    if "bold_mode_active" not in globals():
                                        bold_mode_active = False
                                    if "italic_mode_active" not in globals():
                                        italic_mode_active = False

                                    # 줄 시작 또는 중간에 ** 패턴이 있는지 확인 (동시에 해당 줄에 닫힌 ** 없는 경우)
                                    # ** 경계가 있지만 그 줄에 짝을 이루는 **가 없는 경우만 처리
                                    start_bold = False
                                    if (
                                        not bold_mode_active
                                        and line.count("**") % 2 == 1
                                    ):
                                        start_bold = True

                                    # 종료 위치 확인 (종료 줄인 경우)
                                    end_bold = False
                                    if bold_mode_active and line.count("**") % 2 == 1:
                                        end_bold = True

                                    # 굵은 텍스트 모드 상태 확인 및 처리
                                    if start_bold:
                                        # 굵은 텍스트 시작
                                        bold_mode_active = True

                                        # 텍스트 처리 - 첫 번째 ** 이후의 텍스트만 추출
                                        text_parts = line.split("**", 1)
                                        if len(text_parts) > 1:
                                            # 앞부분 텍스트 (** 이전)
                                            if text_parts[0]:
                                                page.keyboard.type(text_parts[0])

                                            # 굵은 텍스트 시작 단축키
                                            page.keyboard.press(bold_key)

                                            # 나머지 텍스트 입력
                                            page.keyboard.type(text_parts[1])
                                        else:
                                            # ** 표시가 있지만 텍스트 분할이 안 된 경우 (비정상 케이스)
                                            page.keyboard.type(line)

                                    elif end_bold:
                                        # 굵은 텍스트 종료
                                        # 텍스트 처리 - ** 앞의 텍스트만 추출
                                        text_parts = line.split("**", 1)

                                        # 앞부분 텍스트 입력 (** 이전까지)
                                        if text_parts[0]:
                                            page.keyboard.type(text_parts[0])

                                        # 굵은 텍스트 종료 단축키
                                        page.keyboard.press(bold_key)

                                        # 나머지 텍스트가 있으면 입력
                                        if len(text_parts) > 1:
                                            page.keyboard.type(text_parts[1])

                                    elif bold_mode_active:
                                        # 굵은 텍스트 모드 중이므로 그대로 타이핑 (** 없는 중간 줄)
                                        page.keyboard.type(line)

                                    else:
                                        # 굵은 텍스트 처리 (**text**)과 기울임 텍스트 처리 (*text*)
                                        segments = []
                                        current_position = 0

                                        # ** 패턴과 * 패턴 모두 찾기
                                        combined_pattern = re.compile(
                                            r"(\*\*(.*?)\*\*|\*(.*?)\*)"
                                        )
                                        for match in combined_pattern.finditer(line):
                                            start, end = match.span()
                                            # 이전 일반 텍스트 추가
                                            if start > current_position:
                                                segments.append(
                                                    (
                                                        "normal",
                                                        line[current_position:start],
                                                    )
                                                )

                                            matched_text = match.group(0)
                                            if matched_text.startswith("**"):
                                                # 굵은 텍스트 (** **)
                                                segments.append(
                                                    ("bold", match.group(2))
                                                )
                                            else:
                                                # 기울임 텍스트 (* *)
                                                segments.append(
                                                    ("italic", match.group(3))
                                                )

                                            current_position = end

                                        # 남은 텍스트 처리
                                        if current_position < len(line):
                                            segments.append(
                                                ("normal", line[current_position:])
                                            )

                                        # 일반 텍스트 처리 (스타일 포함)
                                        for segment_type, segment_text in segments:
                                            if segment_type == "bold":
                                                # 굵은 텍스트 시작
                                                page.keyboard.press(bold_key)
                                                page.keyboard.type(segment_text)
                                                # 굵은 텍스트 종료
                                                page.keyboard.press(bold_key)
                                            elif segment_type == "italic":
                                                # 기울임 텍스트 시작
                                                page.keyboard.press(italic_key)
                                                page.keyboard.type(segment_text)
                                                # 기울임 텍스트 종료
                                                page.keyboard.press(italic_key)
                                            else:
                                                page.keyboard.type(segment_text)

                                        # 줄바꿈 추가
                                        page.keyboard.press("Enter")
                        print("Content entered successfully")

                        # 장소 추가 부분
                        address = None

                        # location이 제공되었고, 엑셀 파일이 존재하는 경우 주소 찾기
                        if location:
                            print(f"지역 정보가 제공되었습니다: {location}")
                            # 스크립트 위치 기준 docs/map.xlsx 경로 설정
                            excel_path = os.path.join(
                                os.path.dirname(os.path.abspath(__file__)),
                                "docs",
                                "map.xlsx",
                            )

                            # 엑셀 파일이 존재하는지 확인
                            if os.path.exists(excel_path):
                                try:
                                    # 엑셀 파일 읽기
                                    df = pd.read_excel(excel_path)
                                    print(
                                        f"map.xlsx 파일 로드 성공, 데이터 형태: {df.shape}, 컬럼: {df.columns.tolist()}"
                                    )

                                    # '지역' 열에서 location과 일치하는 행 찾기
                                    matching_rows = df[df["지역"] == location]

                                    # 일치하는 행이 있으면 주소 가져오기
                                    if not matching_rows.empty:
                                        address = matching_rows.iloc[0]["주소"]
                                        print(
                                            f"지역 '{location}'에 해당하는 주소를 찾았습니다: {address}"
                                        )
                                    else:
                                        print(
                                            f"지역 '{location}'에 해당하는 주소를 찾을 수 없습니다. 엑셀 파일의 지역 목록: {df['지역'].unique().tolist()}"
                                        )
                                except Exception as e:
                                    print(f"엑셀 파일 읽기 오류: {e}")
                            else:
                                print(f"엑셀 파일을 찾을 수 없습니다: {excel_path}")
                        else:
                            print(
                                "지역 정보가 제공되지 않았습니다. 주소 자동 입력을 건너뜁니다."
                            )

                        # 주소가 있는 경우에만 장소 추가 진행
                        if address:
                            print(f"주소({address})를 사용하여 장소 추가를 시작합니다.")
                            page.locator(
                                'iframe[name="mainFrame"]'
                            ).content_frame.get_by_role(
                                "button", name="장소 추가"
                            ).click()

                            page.locator(
                                'iframe[name="mainFrame"]'
                            ).content_frame.get_by_role(
                                "textbox", name="장소명을 입력하세요"
                            ).click()

                            page.locator(
                                'iframe[name="mainFrame"]'
                            ).content_frame.get_by_role(
                                "textbox", name="장소명을 입력하세요"
                            ).fill(
                                address + " 누수탐지"
                            )
                            time.sleep(0.5)
                            page.locator(
                                'iframe[name="mainFrame"]'
                            ).content_frame.get_by_role(
                                "textbox", name="장소명을 입력하세요"
                            ).press(
                                "Enter"
                            )

                            # 검색 결과에서 첫 번째 항목 선택
                            page.locator(
                                'iframe[name="mainFrame"]'
                            ).content_frame.locator(
                                "strong.se-place-map-search-result-title"
                            ).first.click()

                            page.locator(
                                'iframe[name="mainFrame"]'
                            ).content_frame.get_by_role(
                                "button", name="추가", exact=True
                            ).click()

                            page.locator(
                                'iframe[name="mainFrame"]'
                            ).content_frame.get_by_role(
                                "button", name="확인", exact=True
                            ).click()

                        # 발행 버튼 클릭
                        print("Clicking publish button...")
                        close_button = editor_frame.get_by_role(
                            "button", name="닫기"
                        ).nth(1)
                        close_button.click()
                        time.sleep(1)

                        publish_btn = editor_frame.get_by_text("발행", exact=True)
                        if publish_btn.count() > 0:
                            publish_btn.click(force=True)
                            print("Publish button clicked")
                            time.sleep(2)

                            confirm_button = editor_frame.get_by_text(
                                "발행", exact=True
                            )
                            if confirm_button.count() >= 2:
                                confirm_button.nth(1).click(force=True)
                                print("Publish confirmed")
                                time.sleep(5)
                                return True

                except Exception as e:
                    print(f"Error during content entry: {e}")
                    raise

            return False

        except Exception as e:
            print(f"Error during blog posting: {e}")
            raise
        finally:
            # 리소스 정리
            for p in context.pages:
                p.close()
            browser.close()
            print("Browser closed")

    return True


def save_markdown_to_file(markdown_content, output_file="output.txt"):
    """마크다운 내용을 텍스트 파일로 저장"""
    # ```markdown 및 ``` 태그 제거
    # 먼저 ```markdown 형식 제거
    markdown_content = re.sub(r"```markdown\n", "", markdown_content)
    # 그 다음 ```language 형식 제거
    markdown_content = re.sub(r"```[a-zA-Z0-9_]*\n", "", markdown_content)
    # 마지막으로 닫는 ``` 제거
    markdown_content = re.sub(r"```\n?", "", markdown_content)

    # 파일에 저장
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"마크다운 내용이 {output_file}에 저장되었습니다.")
    return markdown_content


if __name__ == "__main__":
    # 테스트용 폴더 경로와 지역
    test_folder_path = "20250402_2031_gz73gj1_223751315667"
    test_location = "김포"  # 테스트 지역명
    try:
        result = write_naver_blog(folder_path=test_folder_path, location=test_location)
        print(f"Blog posting {'successful' if result else 'failed'}")
    except Exception as e:
        print(f"Error in main: {e}")
