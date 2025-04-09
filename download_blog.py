import requests
from bs4 import BeautifulSoup
import re
import os
import time
from urllib.parse import urlparse
from datetime import datetime
import json
from PIL import Image
import random
import process_images  # Import the process_images module

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


def extract_naver_blog_html_and_images(url):
    """
    네이버 블로그 URL에서 HTML 콘텐츠와 이미지를 추출합니다.

    Args:
        url (str): 네이버 블로그 URL

    Returns:
        tuple: (블로그ID, 게시물번호, HTML 내용, 이미지 URL 리스트, 텍스트 내용, 이미지 위치 정보, 블로그 제목). 오류 발생 시 (None, None, None, None, None, None, None) 반환.
    """
    try:
        # 사용자 에이전트와 헤더 설정으로 실제 브라우저처럼 보이게 함
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://blog.naver.com/",
        }

        session = requests.Session()
        response = session.get(url, headers=headers)
        response.raise_for_status()

        # 블로그 ID와 게시물 번호 추출
        blog_id = None
        log_no = None

        # URL에서 추출 시도
        url_pattern = r"blog\.naver\.com/([^/]+)/(\d+)"
        url_match = re.search(url_pattern, url)
        if url_match:
            blog_id = url_match.group(1)
            log_no = url_match.group(2)

        print(f"블로그 ID: {blog_id}, 게시물 번호: {log_no}")

        # HTML 파싱 시도
        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        # 블로그 제목 추출
        blog_title = None
        title_element = soup.select_one(".se-title-text")
        if title_element:
            blog_title = title_element.get_text(strip=True)
            print(f"블로그 제목: {blog_title}")

        # HTML 콘텐츠와 텍스트 내용 추출
        article_html = ""
        article_text = ""
        article_content = None
        iframe_soup = None
        ordered_image_urls = []  # HTML에 나타나는 순서대로 이미지 URL을 저장

        # 먼저 기본 페이지에서 se-main-container 찾기
        main_container = soup.select_one(".se-main-container")
        if main_container:
            print("메인 페이지에서 .se-main-container 찾음")
            article_content = main_container

            # 블로그 제목이 아직 없으면 메인 컨테이너에서 찾기
            if not blog_title:
                title_element = main_container.select_one(".se-title-text")
                if title_element:
                    blog_title = title_element.get_text(strip=True)
                    print(f"메인 컨테이너에서 블로그 제목: {blog_title}")

            # 이미지 URL 수정 (data-lazy-src 속성을 src 속성으로 변경)
            fix_lazy_loaded_images(main_container)

            # 콘텐츠 구조 분석 (텍스트와 이미지 순서 추출)
            content_structure = extract_content_structure(main_container)

            # 이미지 URL을 나타나는 순서대로 추출
            ordered_image_urls = extract_ordered_image_urls(main_container)

            article_html = str(main_container)
            article_text = main_container.get_text(separator="\n", strip=True)
        else:
            # iframe에서 찾기 시도
            iframe = soup.find("iframe", id="mainFrame")
            if iframe:
                iframe_src = iframe.get("src")
                if iframe_src:
                    if not iframe_src.startswith(("http:", "https:")):
                        iframe_url = "https://blog.naver.com" + iframe_src
                    else:
                        iframe_url = iframe_src

                    print(f"iframe URL: {iframe_url}")
                    iframe_response = session.get(iframe_url, headers=headers)
                    iframe_soup = BeautifulSoup(iframe_response.text, "html.parser")

                    # iframe 내에서 블로그 제목 찾기
                    if not blog_title:
                        title_element = iframe_soup.select_one(".se-title-text")
                        if title_element:
                            blog_title = title_element.get_text(strip=True)
                            print(f"iframe에서 블로그 제목: {blog_title}")

                    # iframe 내에서 se-main-container 찾기
                    iframe_main_container = iframe_soup.select_one(".se-main-container")
                    if iframe_main_container:
                        print("iframe 내에서 .se-main-container 찾음")
                        article_content = iframe_main_container

                        # 블로그 제목이 아직 없으면 iframe 메인 컨테이너에서 찾기
                        if not blog_title:
                            title_element = iframe_main_container.select_one(
                                ".se-title-text"
                            )
                            if title_element:
                                blog_title = title_element.get_text(strip=True)
                                print(
                                    f"iframe 메인 컨테이너에서 블로그 제목: {blog_title}"
                                )

                        # 이미지 URL 수정 (data-lazy-src 속성을 src 속성으로 변경)
                        fix_lazy_loaded_images(iframe_main_container)

                        # 콘텐츠 구조 분석 (텍스트와 이미지 순서 추출)
                        content_structure = extract_content_structure(
                            iframe_main_container
                        )

                        # 이미지 URL을 나타나는 순서대로 추출
                        ordered_image_urls = extract_ordered_image_urls(
                            iframe_main_container
                        )

                        article_html = str(iframe_main_container)
                        article_text = iframe_main_container.get_text(
                            separator="\n", strip=True
                        )

        if not article_content:
            print("se-main-container를 찾을 수 없습니다.")
            return None, None, None, None, None, None, None

        # 이미지 요소도 추가로 찾기 (혹시 놓친 이미지가 있을 수 있음)
        if not ordered_image_urls:
            print("순서대로 이미지를 찾지 못했습니다. 다른 방법 시도 중...")
            image_urls = []

            # 이미지 요소 찾기
            if not image_urls:
                print("이미지 태그 직접 검색 중...")
                image_elements = article_content.select(".se-image, .se-imageStrip")
                for img_container in image_elements:
                    img_tag = img_container.select_one("img")
                    if img_tag:
                        # data-lazy-src 속성을 우선 확인 (고화질 이미지 URL)
                        img_url = img_tag.get("data-lazy-src") or img_tag.get("src")
                        if img_url:
                            high_res_url = convert_to_high_resolution(img_url)
                            if high_res_url not in image_urls:
                                image_urls.append(high_res_url)

            # 자바스크립트 변수에서도 이미지 추출 시도
            script_tags = (
                soup.find_all("script")
                if not iframe_soup
                else iframe_soup.find_all("script")
            )
            for script in script_tags:
                script_text = script.string
                if script_text and "se-module-image" in script_text:
                    # SE3 에디터의 이미지 관련 패턴 - 원본 이미지 URL 찾기
                    img_patterns = [
                        r'"originalUrl"\s*:\s*"(https://post[^"]+)"',  # 우선 원본 URL 패턴 먼저 찾기
                        r'"url"\s*:\s*"(https://post[^"]+)"',  # 그 다음 일반 URL 패턴
                    ]

                    for pattern in img_patterns:
                        matches = re.findall(pattern, script_text)
                        for match in matches:
                            if "postfiles.pstatic.net" in match:
                                high_res_url = convert_to_high_resolution(match)
                                if high_res_url not in image_urls:
                                    image_urls.append(high_res_url)

            # 중복 제거
            image_urls = list(set(image_urls))

            # 이미지를 찾지 못한 경우, 빈 리스트 반환
            ordered_image_urls = image_urls

        return (
            blog_id,
            log_no,
            article_html,
            ordered_image_urls,
            article_text,
            content_structure,
            blog_title,
        )

    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return None, None, None, None, None, None, None


def convert_to_high_resolution(img_url):
    """
    네이버 블로그 이미지 URL을 최대 해상도 URL로 변환합니다.

    Args:
        img_url (str): 원본 이미지 URL

    Returns:
        str: 최대 해상도 이미지 URL
    """
    try:
        # 1. 쿼리 파라미터가 있는 경우, 기본 URL만 추출
        if "?" in img_url:
            base_url = img_url.split("?")[0]
            query_params = img_url.split("?")[1]
        else:
            base_url = img_url
            query_params = ""

        # 2. 네이버 포스트 이미지인 경우 (postfiles.pstatic.net)
        if "postfiles.pstatic.net" in base_url:
            # 먼저 원본 URL을 그대로 시도 (쿼리 파라미터 없이)
            # 많은 경우 쿼리 파라미터 없는 URL이 원본 이미지를 제공함
            if query_params:
                # 기존 타입 파라미터 분석
                has_type_param = False
                for param in query_params.split("&"):
                    if param.startswith("type="):
                        has_type_param = True
                        type_value = param.split("=")[1]
                        # 이미 고해상도 타입이면 원본 URL 반환
                        if type_value in ["w966", "w2", "w1200", "w800"]:
                            return img_url

                # 고해상도 타입이 아니면 w966으로 시도 (original은 종종 404 오류 발생)
                if has_type_param:
                    new_query = re.sub(r"type=[^&]+", "type=w966", query_params)
                    return f"{base_url}?{new_query}"
                else:
                    return f"{base_url}?{query_params}&type=w966"

            # 쿼리 파라미터가 없는 경우, 원본 URL 시도 후 실패하면 w966 추가
            return base_url

        # 3. 다른 네이버 이미지인 경우 (blogpfthumb-phinf.pstatic.net 등)
        elif "pstatic.net" in base_url:
            # 이미지 크기 관련 파라미터가 URL에 포함된 경우 처리
            if any(
                size_param in base_url for size_param in ["_s", "_t", "_m", "type=w"]
            ):
                # 크기 관련 파라미터를 제거하거나 최대 크기로 변경
                url_parts = base_url.split("/")

                # URL의 마지막 부분에서 크기 관련 변경
                filename = url_parts[-1]

                # 파일명에 크기 패턴이 있는 경우 (예: image_t.jpg, image_s100.jpg 등)
                size_patterns = ["_s", "_t", "_m", "_l"]
                for pattern in size_patterns:
                    if pattern in filename:
                        # 크기 표시 제거하여 원본 파일명으로 변경
                        parts = filename.split(".")
                        name = parts[0]
                        ext = parts[1] if len(parts) > 1 else "jpg"

                        name = re.sub(r"_[stm]\d*", "", name)  # _s100 같은 패턴 제거
                        name = re.sub(r"_[stm]", "", name)  # _s, _t, _m 같은 패턴 제거

                        new_filename = f"{name}.{ext}"
                        url_parts[-1] = new_filename
                        return "/".join(url_parts)

            # 이미 최대 해상도이거나 변경할 필요가 없는 URL
            return base_url

        # 4. 그 외 일반 URL - 그대로 반환
        return img_url

    except Exception as e:
        print(f"이미지 URL 변환 오류: {e}")
        return img_url  # 오류 발생 시 원본 URL 반환


def download_image(url, folder_path, index):
    """
    이미지 URL에서 이미지를 다운로드하여 저장합니다.

    Args:
        url (str): 이미지 URL
        folder_path (str): 저장할 폴더 경로
        index (int): 이미지 인덱스

    Returns:
        str: 저장된 이미지 파일 경로. 실패 시 None.
    """
    try:
        # 항상 PNG 확장자 사용
        file_name = f"image_{index:03d}.png"
        file_path = os.path.join(folder_path, file_name)

        # 이미지 다운로드
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://blog.naver.com/",
        }

        # 원본 URL이 아직 고화질이 아닐 수 있으므로 한 번 더 변환
        high_res_url = convert_to_high_resolution(url)
        print(f"고화질 이미지 URL: {high_res_url}")

        # 첫 번째 시도: 고화질 URL
        try:
            response = requests.get(
                high_res_url, headers=headers, stream=True, timeout=10
            )
            response.raise_for_status()
        except requests.exceptions.RequestException:
            print(f"고화질 URL 다운로드 실패, 원본 URL로 재시도: {url}")

            # 두 번째 시도: 원본 URL (쿼리 파라미터 제거)
            try:
                base_url = url.split("?")[0]
                response = requests.get(
                    base_url, headers=headers, stream=True, timeout=10
                )
                response.raise_for_status()
            except requests.exceptions.RequestException:
                print(
                    f"원본 URL 다운로드 실패, 쿼리 파라미터를 w966으로 설정하여 재시도"
                )

                # 세 번째 시도: type=w966으로 설정
                try:
                    if "?" in url:
                        url_parts = url.split("?")
                        base_url = url_parts[0]
                        query = url_parts[1]

                        if "type=" in query:
                            query = re.sub(r"type=[^&]+", "type=w966", query)
                        else:
                            query += "&type=w966"

                        fallback_url = f"{base_url}?{query}"
                    else:
                        fallback_url = f"{url}?type=w966"

                    response = requests.get(
                        fallback_url, headers=headers, stream=True, timeout=10
                    )
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    print(f"모든 다운로드 시도 실패: {e}")
                    return None

        # 파일에 저장
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)

        # 이미지 크기 확인
        with Image.open(file_path) as img:
            width, height = img.size

        print(f"이미지 다운로드 완료: {file_path} (크기: {width}x{height})")
        return file_path

    except Exception as e:
        print(f"이미지 다운로드 오류 ({url}): {e}")
        return None


def save_to_file(content, folder_path, file_name):
    """
    콘텐츠를 파일로 저장합니다.

    Args:
        content (str): 저장할 콘텐츠
        folder_path (str): 저장할 폴더 경로
        file_name (str): 파일명

    Returns:
        str: 저장된 파일 경로
    """
    try:
        file_path = os.path.join(folder_path, file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"파일 저장 완료: {file_path}")
        return file_path
    except Exception as e:
        print(f"파일 저장 오류: {e}")
        return None


def extract_content_structure(article_content):
    """
    HTML 콘텐츠에서 텍스트와 이미지의 구조(순서)를 추출합니다.

    Args:
        article_content (BeautifulSoup): HTML 콘텐츠를 담고 있는 BeautifulSoup 객체

    Returns:
        list: [(유형, 내용), ...] 형태의 구조. 유형은 'text' 또는 'image'.
    """
    content_structure = []

    # 네이버 블로그는 se-module 클래스로 콘텐츠를 구분함
    modules = article_content.select(".se-module")

    for module in modules:
        # 텍스트 모듈인 경우
        if module.select_one(".se-text"):
            text_content = module.get_text(strip=True)
            if text_content:
                content_structure.append(("text", text_content))

        # 이미지 모듈인 경우
        elif module.select_one(".se-image, .se-imageStrip"):
            img_tag = module.select_one("img")
            if img_tag:
                # data-lazy-src 속성이 있으면 그 값을, 없으면 src 값을 사용
                img_url = img_tag.get("data-lazy-src") or img_tag.get("src")
                if img_url:
                    image_info = {
                        "url": img_url,
                        "alt": img_tag.get("alt", ""),
                        "width": img_tag.get("data-width", ""),
                        "height": img_tag.get("data-height", ""),
                    }
                    content_structure.append(("image", image_info))

    return content_structure


def create_image_positions_text(text, image_urls, content_structure, folder_path):
    """
    콘텐츠 구조(텍스트와 이미지 순서)에 따라 텍스트와 이미지를 배치하여 파일로 저장합니다.

    Args:
        text (str): 본문 텍스트
        image_urls (list): 이미지 URL 목록 (순서대로 정렬됨)
        content_structure (list): 콘텐츠 구조 [(유형, 내용), ...]
        folder_path (str): 저장할 폴더 경로

    Returns:
        str: 저장된 파일 경로
    """
    try:
        if not image_urls:
            return save_to_file(text, folder_path, "content_with_images.txt")

        # 텍스트 단락 분리 (여러 줄 묶음이 있을 수 있음)
        paragraphs = []
        current_para = ""

        for line in text.split("\n"):
            if line.strip():
                current_para += line + "\n"
            elif current_para:
                paragraphs.append(current_para.strip())
                current_para = ""

        if current_para:
            paragraphs.append(current_para.strip())

        # 결과 텍스트 구성 - 본문과 이미지 위치만 포함
        result_text = ""

        # 콘텐츠 구조를 기반으로 텍스트와 이미지 배치
        if content_structure:
            print(
                f"콘텐츠 구조에 따라 텍스트와 이미지 배치 중... (항목 수: {len(content_structure)})"
            )

            paragraph_index = 0
            image_index = 0

            # 이미지 URL을 콘텐츠 구조에 맞게 정렬
            for item_type, content in content_structure:
                if item_type == "text":
                    # 텍스트 단락 추가 (해당 내용 찾기)
                    if paragraph_index < len(paragraphs):
                        result_text += paragraphs[paragraph_index] + "\n\n"
                        paragraph_index += 1

                elif item_type == "image" and image_index < len(image_urls):
                    # 이미지 삽입 - HTML에서의 순서를 유지하는 것이 핵심
                    # HTML에 있는 순서대로 이미지 파일 이름 사용
                    image_filename = f"image_{image_index+1:03d}.png"
                    full_image_path = os.path.join(folder_path, image_filename)
                    original_url = image_urls[image_index]
                    result_text += f"[이미지: {image_filename}]\n"
                    result_text += f"[이미지 경로: {full_image_path}]\n"
                    result_text += f"[원본 URL: {original_url}]\n\n"
                    image_index += 1

            # 남은 단락과 이미지 추가
            while paragraph_index < len(paragraphs):
                result_text += paragraphs[paragraph_index] + "\n\n"
                paragraph_index += 1

            while image_index < len(image_urls):
                image_filename = f"image_{image_index+1:03d}.png"
                full_image_path = os.path.join(folder_path, image_filename)
                original_url = image_urls[image_index]
                result_text += f"[이미지: {image_filename}]\n"
                result_text += f"[이미지 경로: {full_image_path}]\n"
                result_text += f"[원본 URL: {original_url}]\n\n"
                image_index += 1

        else:
            # 콘텐츠 구조가 없는 경우 순서대로 배치
            print("콘텐츠 구조 정보가 없습니다. 이미지를 순서대로 배치합니다.")

            # 텍스트와 이미지 간격 계산
            interval = max(1, len(paragraphs) // (len(image_urls) + 1))

            for i, para in enumerate(paragraphs):
                result_text += para + "\n\n"

                # 이미지 순서대로 삽입
                img_index = i // interval
                if i > 0 and i % interval == 0 and img_index < len(image_urls):
                    image_filename = f"image_{img_index+1:03d}.png"
                    full_image_path = os.path.join(folder_path, image_filename)
                    original_url = image_urls[img_index]
                    result_text += f"[이미지: {image_filename}]\n"
                    result_text += f"[이미지 경로: {full_image_path}]\n"
                    result_text += f"[원본 URL: {original_url}]\n\n"

        # 결과 파일 저장 - 하나의 파일만 생성
        content_file = save_to_file(
            result_text.strip(), folder_path, "content_with_images.txt"
        )
        return content_file

    except Exception as e:
        print(f"이미지 위치 텍스트 생성 오류: {e}")
        return None


def fix_lazy_loaded_images(html_container):
    """
    HTML 콘텐츠 내의 지연 로딩(lazy loading) 이미지의 속성을 수정합니다.
    data-lazy-src 속성을 src 속성으로 변경하여 이미지가 즉시 로드되도록 합니다.
    또한 blur 처리된 이미지를 고화질 이미지로 교체합니다.

    Args:
        html_container (BeautifulSoup): HTML 콘텐츠를 담고 있는 BeautifulSoup 객체
    """
    # 1. 모든 이미지 태그 찾기
    img_tags = html_container.find_all("img")

    for img in img_tags:
        # 2. data-lazy-src 속성이 있는 경우 (지연 로딩 이미지)
        if img.has_attr("data-lazy-src"):
            # 고화질 이미지 URL 가져오기
            high_res_url = img["data-lazy-src"]

            # 3. 저해상도 blur 이미지 URL을 고화질 URL로 교체
            if img.has_attr("src"):
                # 현재 src URL이 blur 처리된 이미지인지 확인
                current_src = img["src"]
                if (
                    "blur" in current_src
                    or "w80" in current_src
                    or "s80" in current_src
                ):
                    # 고화질 URL로 교체 (원본 형식 유지)
                    img["src"] = high_res_url
                    # data-lazy-src 속성에 있는 원본 URL을 고화질 URL로 교체
                    img["data-lazy-src"] = convert_to_high_resolution(high_res_url)

        # 4. src 속성이 있지만 저해상도 URL인 경우
        elif img.has_attr("src"):
            src_url = img["src"]
            if "blur" in src_url or any(
                size_param in src_url for size_param in ["w80", "s80", "s160"]
            ):
                # 고화질 URL로 변환
                high_res_url = convert_to_high_resolution(src_url)
                img["src"] = high_res_url
                # 원본 URL 보존
                if not img.has_attr("data-original-src"):
                    img["data-original-src"] = src_url


def extract_ordered_image_urls(article_content):
    """
    HTML 콘텐츠에서 이미지 URL을 나타나는 순서대로 추출합니다.

    Args:
        article_content (BeautifulSoup): HTML 콘텐츠

    Returns:
        list: 순서대로 정렬된 이미지 URL 목록
    """
    ordered_urls = []

    try:
        # 방법 1: se-module 클래스 내에서 순서대로 이미지 찾기
        print("HTML에서 이미지 모듈을 순서대로 검색 중...")
        all_modules = article_content.select(".se-module")

        for module in all_modules:
            # 이미지 모듈인지 확인
            if module.select_one(".se-image") or module.select_one(".se-imageStrip"):
                img_tag = module.select_one("img")
                if img_tag:
                    # 고해상도 이미지 URL 추출
                    img_url = img_tag.get("data-lazy-src") or img_tag.get("src")
                    if img_url:
                        high_res_url = convert_to_high_resolution(img_url)
                        if high_res_url not in ordered_urls:
                            ordered_urls.append(high_res_url)
                            print(f"이미지 찾음 ({len(ordered_urls)}): {high_res_url}")

        # 방법 1로 이미지를 못 찾았으면 방법 2 시도
        if not ordered_urls:
            print("방법 1로 이미지를 찾지 못했습니다. 다른 방법 시도 중...")

            # 방법 2: 직접 이미지 태그 찾기
            image_containers = article_content.select(".se-image, .se-imageStrip")

            for container in image_containers:
                img_tag = container.select_one("img")
                if img_tag:
                    img_url = img_tag.get("data-lazy-src") or img_tag.get("src")
                    if img_url:
                        high_res_url = convert_to_high_resolution(img_url)
                        if high_res_url not in ordered_urls:
                            ordered_urls.append(high_res_url)
                            print(f"이미지 찾음 ({len(ordered_urls)}): {high_res_url}")

        # 방법 2로도 이미지를 못 찾았으면 방법 3 시도
        if not ordered_urls:
            print("방법 2로도 이미지를 찾지 못했습니다. 모든 img 태그 검색 중...")

            # 방법 3: 모든 img 태그 검색
            img_tags = article_content.select("img")

            for img in img_tags:
                img_url = img.get("data-lazy-src") or img.get("src")
                if (
                    img_url
                    and ("postfiles.pstatic.net" in img_url)
                    and ("blur" not in img_url)
                ):
                    high_res_url = convert_to_high_resolution(img_url)
                    if high_res_url not in ordered_urls:
                        ordered_urls.append(high_res_url)
                        print(f"이미지 찾음 ({len(ordered_urls)}): {high_res_url}")

    except Exception as e:
        print(f"이미지 URL 추출 중 오류 발생: {e}")

    print(f"총 {len(ordered_urls)}개의 이미지를 순서대로 찾았습니다.")

    # 모든 이미지 URL 출력 (디버깅용)
    for i, url in enumerate(ordered_urls, 1):
        print(f"이미지 {i}: {url}")

    return ordered_urls


def create_text_img_content(html_file_path, folder_path):
    """
    HTML 파일에서 텍스트와 이미지 태그만 남기고 모두 제거한 후 새 파일로 저장합니다.
    원본 HTML의 텍스트와 이미지 순서를 유지합니다.
    중복된 이미지는 제거합니다.
    이미지에 순서대로 번호를 붙여 표시합니다.

    Args:
        html_file_path (str): 원본 HTML 파일 경로
        folder_path (str): 출력 폴더 경로

    Returns:
        str: 생성된 파일 경로
    """
    try:
        # 파일 읽기
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # content_with_images.txt 파일 읽기 (있는 경우)
        content_text_path = os.path.join(folder_path, "content_with_images.txt")
        content_text = ""
        if os.path.exists(content_text_path):
            with open(content_text_path, "r", encoding="utf-8") as f:
                content_text = f.read()

        # HTML 파싱
        soup = BeautifulSoup(html_content, "html.parser")

        # 새로운 HTML 문서 생성
        new_content = ""

        # 중복 이미지 방지를 위한 이미지 src 추적
        processed_img_srcs = set()

        # 이미지 카운터
        img_counter = 1

        # 모든 콘텐츠 모듈을 순서대로 처리
        all_modules = soup.select(
            ".se-module-text, .se-module-image, .se-image, .se-imageStrip"
        )

        for module in all_modules:
            # 텍스트 모듈인 경우
            if "se-module-text" in module.get("class", []):
                paragraphs = module.select("p")
                for p in paragraphs:
                    # 빈 텍스트가 아닌 경우에만 추가
                    text = p.get_text(strip=True)
                    if text and text != "​":  # 빈 공백 문자도 제외
                        new_content += f"<p>{text}</p>\n"

            # 이미지 모듈인 경우
            elif any(
                img_class in module.get("class", [])
                for img_class in ["se-module-image", "se-image", "se-imageStrip"]
            ):
                img_elem = module.select_one("img")
                if img_elem:
                    src = img_elem.get("src", "")
                    alt = img_elem.get("alt", "")

                    # 이미지 중복 확인 - 이미 처리한 src인지 확인
                    if src and src not in processed_img_srcs:
                        # 이미지 태그와 번호 태그 함께 추가
                        img_tag = f'<img src="{src}" alt="{alt}">\n'
                        img_name_tag = f"{{image_{img_counter:03d}.png}}\n"

                        new_content += img_tag + img_name_tag
                        processed_img_srcs.add(src)  # 처리한 이미지 src 추가
                        img_counter += 1  # 이미지 카운터 증가

        # 결과 저장
        output_file_path = os.path.join(folder_path, "text_img_content.html")
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        print(f"텍스트와 이미지만 포함된 HTML 파일 생성 완료: {output_file_path}")
        return output_file_path

    except Exception as e:
        print(f"텍스트와 이미지 HTML 생성 중 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return None


def add_watermarks_to_images(image_folder_path, watermark_folder_path):
    """
    Add a random watermark from the photo folder to one corner of each downloaded image.
    The watermark is applied directly to the original images.

    Args:
        image_folder_path (str): Path to folder containing downloaded images
        watermark_folder_path (str): Path to folder containing watermark images

    Returns:
        int: Number of successfully watermarked images
    """
    try:
        # Get list of all images in the folders
        image_files = [
            f
            for f in os.listdir(image_folder_path)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
        ]

        watermark_files = [
            f
            for f in os.listdir(watermark_folder_path)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
        ]

        if not watermark_files:
            print(f"No watermark images found in {watermark_folder_path}")
            return 0

        if not image_files:
            print(f"No images found in {image_folder_path}")
            return 0

        watermarked_count = 0

        # Process each image
        for img_file in image_files:
            img_path = os.path.join(image_folder_path, img_file)

            try:
                # Open the main image
                main_img = Image.open(img_path)
                main_width, main_height = main_img.size

                # Select a random watermark image
                watermark_file = random.choice(watermark_files)

                # Define corners (we'll randomly select one)
                corners = [
                    (0, 0),  # top-left
                    (main_width, 0),  # top-right
                    (0, main_height),  # bottom-left
                    (main_width, main_height),  # bottom-right
                ]

                # Select a random corner
                corner = random.choice(corners)

                # Calculate watermark size (proportional to main image)
                # Increased to 45% (1.5 times the previous 30%)
                watermark_size = int(
                    min(main_width, main_height) * 0.45
                )  # 45% of the smallest dimension

                # Add the watermark to the chosen corner
                watermark_path = os.path.join(watermark_folder_path, watermark_file)
                watermark = Image.open(watermark_path)

                # Resize watermark proportionally
                watermark_w, watermark_h = watermark.size
                ratio = min(watermark_size / watermark_w, watermark_size / watermark_h)
                new_size = (int(watermark_w * ratio), int(watermark_h * ratio))
                watermark = watermark.resize(new_size, Image.LANCZOS)

                # Adjust position to place watermark fully inside the corner
                x, y = corner
                if x > 0:  # right side
                    x -= watermark.width
                if y > 0:  # bottom side
                    y -= watermark.height

                # Paste watermark onto main image
                # If watermark has transparency (RGBA), use it as mask
                if watermark.mode == "RGBA":
                    main_img.paste(watermark, (x, y), watermark)
                else:
                    main_img.paste(watermark, (x, y))

                # Save the watermarked image (overwrite original)
                main_img.save(img_path)
                watermarked_count += 1
                print(
                    f"Added watermark to {img_file} at {('top-left', 'top-right', 'bottom-left', 'bottom-right')[corners.index(corner)]} corner"
                )

            except Exception as e:
                print(f"Error adding watermark to {img_file}: {e}")
                continue

        print(
            f"Successfully added watermarks to {watermarked_count}/{len(image_files)} images"
        )
        return watermarked_count

    except Exception as e:
        print(f"Error in watermarking process: {e}")
        return 0


def process_blog_url(blog_url, title=None, region="", keyword=""):
    """
    네이버 블로그 URL을 받아 내용을 스크랩하고 저장합니다.

    Args:
        blog_url (str): 스크랩할 네이버 블로그 URL
        title (str, optional): 외부에서 제공하는 제목 (있는 경우 이 제목으로 title.txt 파일 생성)
        region (str, optional): GUI에서 지정한 지역명
        keyword (str, optional): GUI에서 지정한 키워드

    Returns:
        tuple: (blog_id, log_no, folder_path, success) - 성공 여부와 함께 블로그 ID, 로그 번호, 생성된 폴더 경로 반환
    """
    # 워터마크 이미지 폴더 경로
    script_dir = os.path.dirname(os.path.abspath(__file__))
    watermark_folder = os.path.join(script_dir, "photo")

    if not os.path.exists(watermark_folder):
        print(f"워터마크 폴더가 존재하지 않습니다: {watermark_folder}")
        watermark_folder = None

    print(f"\n블로그 URL: {blog_url}")
    print("데이터 추출 중...")

    # HTML, 이미지 URL, 텍스트 추출
    (
        blog_id,
        log_no,
        html_content,
        image_urls,
        text_content,
        content_structure,
        blog_title,
    ) = extract_naver_blog_html_and_images(blog_url)

    # 결과 확인 및 파일 저장
    if blog_id and log_no and html_content:
        # 현재 날짜/시간 가져오기
        now = datetime.now()
        date_str = now.strftime("%Y%m%d_%H%M")

        # GUI에서 지정한 지역과 키워드가 있으면 우선 사용
        if region and keyword:
            print(f"GUI에서 지정한 지역({region})과 키워드({keyword}) 사용")
            folder_name = f"[{region}]{keyword}_{blog_id}_{log_no}"
        else:
            # GUI에서 지정하지 않은 경우 블로그 제목에서 지역 추출
            location = ""
            if blog_title:
                location_match = re.search(r"^([가-힣]+\s*[가-힣]+)", blog_title)
                if location_match:
                    location = location_match.group(1).strip()

            # 폴더 이름 생성
            if location:
                # Get the keyword from the blog title after location, if available
                extracted_keyword = ""
                if blog_title and location:
                    blog_title_without_location = blog_title.replace(
                        location, "", 1
                    ).strip()
                    if blog_title_without_location:
                        # Try to get the first word as keyword
                        keyword_match = re.search(
                            r"^([가-힣a-zA-Z0-9]+)", blog_title_without_location
                        )
                        if keyword_match:
                            extracted_keyword = keyword_match.group(1).strip()

                if extracted_keyword:
                    folder_name = f"[{location}]{extracted_keyword}_{blog_id}_{log_no}"
                else:
                    folder_name = f"[{location}]_{blog_id}_{log_no}"
            else:
                folder_name = f"{date_str}_{blog_id}_{log_no}"
        folder_path = os.path.join(os.getcwd(), folder_name)

        # 폴더가 존재하지 않으면 생성
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"폴더 생성: {folder_path}")

        # 블로그 제목 저장 - 외부에서 제공된 제목이 있으면 그것을 사용
        if title:
            title_file = save_to_file(title, folder_path, "title.txt")
            print(f"제목 파일 저장 완료 (외부 제공): {title_file}")
        elif blog_title:
            title_file = save_to_file(blog_title, folder_path, "title.txt")
            print(f"제목 파일 저장 완료: {title_file}")

        # HTML 파일 저장
        html_file = save_to_file(html_content, folder_path, "original_content.html")

        # 이미지 다운로드 - 순서 유지하면서 다운로드
        if image_urls and len(image_urls) > 0:
            print(f"\n이미지 다운로드 시작 (총 {len(image_urls)}개)...")
            downloaded_files = []

            for i, image_url in enumerate(image_urls, 1):
                file_name = f"image_{i:03d}.png"
                print(f"이미지 다운로드 중 ({i}/{len(image_urls)}): {image_url}")
                print(f"저장 파일명: {file_name}")

                file_path = download_image(image_url, folder_path, i)
                if file_path:
                    downloaded_files.append(file_path)

                # 과도한 요청을 방지하기 위한 딜레이
                time.sleep(0.5)

            print(
                f"\n이미지 다운로드 완료: {len(downloaded_files)}/{len(image_urls)}개 성공"
            )

            # 이미지에 워터마크 추가 (워터마크 폴더가 있는 경우에만)
            if watermark_folder and os.path.exists(watermark_folder):
                print("\n다운로드한 이미지에 워터마크 추가 중...")
                watermarked_count = add_watermarks_to_images(
                    folder_path, watermark_folder
                )
                print(
                    f"워터마크 추가 완료: {watermarked_count}/{len(downloaded_files)}개 성공"
                )

        # 이미지 위치가 포함된 텍스트 파일 생성 - 하나의 파일만 생성
        if text_content and len(image_urls) > 0:
            print("\n텍스트와 이미지 위치 정보 생성 중...")
            content_file = create_image_positions_text(
                text_content, image_urls, content_structure, folder_path
            )
            print(f"텍스트 파일 생성 완료: {content_file}")

        # 텍스트와 이미지만 포함된 HTML 파일 생성
        if html_file:
            print("\n텍스트와 이미지만 포함된 HTML 파일 생성 중...")
            text_img_file = create_text_img_content(html_file, folder_path)
            print(f"텍스트와 이미지만 포함된 HTML 생성 완료: {text_img_file}")

        # 이미지 처리 및 content_with_images_processed.txt 생성
        print("\n이미지 포지션 처리 및 content_with_images_processed.txt 생성 중...")
        process_images.process_files(folder_path)

        print(f"\n모든 작업이 완료되었습니다. 출력 폴더: {folder_path}")
        return (blog_id, log_no, folder_path, True)
    else:
        print("데이터 추출에 실패했습니다.")
        return (None, None, None, False)


def process_blog_folder(folder_path):
    """
    이미 생성된 블로그 폴더를 처리합니다.
    텍스트와 이미지 위치 정보를 처리하고 content_with_images_processed.txt 파일을 생성합니다.

    Args:
        folder_path (str): 처리할 폴더 경로

    Returns:
        bool: 성공 여부
    """
    try:
        # 워터마크 이미지 폴더 경로
        script_dir = os.path.dirname(os.path.abspath(__file__))
        watermark_folder = os.path.join(script_dir, "photo")

        # 원본 HTML 파일 경로
        html_file_path = os.path.join(folder_path, "original_content.html")

        # 폴더가 존재하는지 확인
        if not os.path.exists(folder_path):
            print(f"오류: 폴더가 존재하지 않습니다: {folder_path}")
            return False

        # HTML 파일이 존재하는지 확인
        if not os.path.exists(html_file_path):
            print(f"오류: HTML 파일이 존재하지 않습니다: {html_file_path}")
            return False

        # 이미지에 워터마크 추가 (워터마크 폴더가 있는 경우에만)
        if os.path.exists(watermark_folder):
            print("\n이미지에 워터마크 추가 중...")
            watermarked_count = add_watermarks_to_images(folder_path, watermark_folder)
            print(f"워터마크 추가 완료: {watermarked_count}개 성공")

        # 텍스트와 이미지만 포함된 HTML 파일 생성
        print("\n텍스트와 이미지만 포함된 HTML 파일 생성 중...")
        text_img_file = create_text_img_content(html_file_path, folder_path)
        print(f"텍스트와 이미지만 포함된 HTML 생성 완료: {text_img_file}")

        # 이미지 처리 및 content_with_images_processed.txt 생성
        print("\n이미지 포지션 처리 및 content_with_images_processed.txt 생성 중...")
        process_images.process_files(folder_path)

        # 처리 완료된 파일이 있는지 확인
        processed_file_path = os.path.join(
            folder_path, "content_with_images_processed.txt"
        )
        if os.path.exists(processed_file_path):
            print(f"\n모든 작업이 완료되었습니다. 출력 파일: {processed_file_path}")
            return True
        else:
            print(f"경고: 처리된 파일이 생성되지 않았습니다.")
            return False

    except Exception as e:
        print(f"폴더 처리 중 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return False


# 메인 실행 코드
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 첫 번째 인수가 존재하는 경우
        param = sys.argv[1]

        if os.path.isdir(param):
            # 폴더 경로가 주어진 경우, 폴더 처리
            print(f"폴더 처리 모드: {param}")
            process_blog_folder(param)
        elif param.startswith("http"):
            # URL이 주어진 경우, URL 처리
            print(f"URL 처리 모드: {param}")
            process_blog_url(param)
        else:
            print(f"알 수 없는 매개변수: {param}")
            print("사용법: python download_blog.py [URL 또는 폴더경로]")
    else:
        # 기본 예제 URL 사용
        blog_url = "https://blog.naver.com/hot9676/223749658381"
        print(f"매개변수 없음, 기본 URL 사용: {blog_url}")
        process_blog_url(blog_url)
