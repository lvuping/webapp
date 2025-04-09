import os
import openai
import argparse
from pathlib import Path
import traceback
import re


def replace_phone_numbers(content):
    """
    전화번호를 찾아서 지정된 번호로 교체합니다.
    """
    # 전화번호 패턴 (010-XXXX-XXXX)
    phone_pattern = r"010-\d{4}-\d{4}"
    # 교체할 전화번호
    new_phone = "010-8678-2065"

    # 전화번호 교체
    modified_content = re.sub(phone_pattern, new_phone, content)
    return modified_content


def read_prompt_file(system_prompt_path, user_prompt_path):
    """
    프롬프트 파일을 읽어 내용을 반환합니다.
    """
    try:
        # 상위 디렉토리로 이동하는 횟수 조정
        current_dir = os.path.dirname(os.path.abspath(__file__))  # 현재 파일의 디렉토리
        print(current_dir)
        system_prompt_absolute_path = os.path.join(current_dir, system_prompt_path)
        user_prompt_absolute_path = os.path.join(current_dir, user_prompt_path)
        with open(system_prompt_absolute_path, "r", encoding="utf-8") as file:
            system_content = file.read()
        with open(user_prompt_absolute_path, "r", encoding="utf-8") as file:
            user_content = file.read()
        return system_content, user_content
    except FileNotFoundError as e:
        print(f"오류: '{e.filename}' 파일을 찾을 수 없습니다.")
        exit(1)
    except Exception as e:
        print(f"파일 읽기 중 오류 발생: {e}")
        exit(1)


def generate_content(system_prompt, user_prompt, api_key, model="gpt-4o"):
    """
    OpenAI API를 사용하여 콘텐츠를 생성합니다.
    """
    try:
        client = openai.OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.75,
            max_tokens=16384,
        )

        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API 호출 중 오류 발생: {e}")
        exit(1)


def save_generated_content_to_folders(content, folders):
    """
    생성된 콘텐츠를 각 폴더에 저장하고 폴더 이름을 [처리후]로 변경합니다.

    Args:
        content (str): 저장할 생성된 콘텐츠
        folders (list): 콘텐츠를 저장할 폴더 경로 목록
    """
    try:
        # HTML 태그 제거
        content = re.sub(r"<[^>]+>", "", content)

        for folder_path in folders:
            output_path = os.path.join(folder_path, "output.md")
            processed_content_path = os.path.join(
                folder_path, "content_with_images_processed.txt"
            )

            # 전화번호 교체 로직 추가
            content = replace_phone_numbers(content)

            # 항상 콘텐츠 새로 저장 (기존 파일이 있어도 덮어씀)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"생성된 콘텐츠 저장 완료: {output_path}")

            # content_with_images_processed.txt 파일 저장
            with open(processed_content_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"처리된 콘텐츠 저장 완료: {processed_content_path}")

            # 폴더 이름 변경 ([처리전] -> [처리후])
            folder_name = os.path.basename(folder_path)
            new_folder_name = folder_name.replace("[처리전]", "[처리후]")
            new_folder_path = os.path.join(
                os.path.dirname(folder_path), new_folder_name
            )

            os.rename(folder_path, new_folder_path)
            print(f"폴더 이름 변경 완료: {folder_path} -> {new_folder_path}")
    except Exception as e:
        print(f"결과 저장 및 폴더 이름 변경 오류: {e}")


def main():
    parser = argparse.ArgumentParser(description="OpenAI API를 사용하여 콘텐츠 생성")
    parser.add_argument(
        "--system_prompt",
        type=str,
        default="docs/system_prompt.md",
        help="시스템 프롬프트 파일 경로",
    )
    parser.add_argument(
        "--user_prompt",
        type=str,
        default="docs/user_prompt.md",
        help="사용자 프롬프트 파일 경로",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="output/generated_post.md",
        help="출력 파일 경로",
    )
    parser.add_argument(
        "--model", type=str, default="gpt-4o", help="사용할 OpenAI 모델"
    )
    args = parser.parse_args()

    # 프롬프트 파일 읽기
    system_prompt, user_prompt = read_prompt_file(args.system_prompt, args.user_prompt)

    # 콘텐츠 생성
    print(f"{args.model} 모델을 사용하여 콘텐츠 생성 중...")
    generated_content, processing_folders = generate_content_with_openai(
        args.system_prompt, args.user_prompt, args.model
    )

    # 폴더가 존재하면 결과 저장
    if processing_folders:
        save_generated_content_to_folders(generated_content, processing_folders)
    else:
        print("[처리전] 폴더가 없어 결과를 저장하지 않습니다.")

    # 결과 출력
    print("\n생성된 콘텐츠:")
    print("=" * 80)
    print(generated_content)
    print("=" * 80)

    # None이 아닐 경우에만 파일에 저장
    if generated_content is not None:
        # 결과 파일 저장 (특정 경로에 저장)
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(generated_content)
        print(f"결과가 {args.output}에 저장되었습니다.")
    else:
        print("생성된 콘텐츠가 없어 파일을 저장하지 않습니다.")


if __name__ == "__main__":
    main()
