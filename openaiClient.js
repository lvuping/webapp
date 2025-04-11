/**
 * OpenAI API를 사용하여 콘텐츠를 생성합니다.
 * @param {string} system_prompt - 시스템 프롬프트
 * @param {string} user_prompt - 사용자 프롬프트
 * @param {string} api_key - OpenAI API 키
 * @param {string} [model="gpt-4o"] - 사용할 모델 이름
 * @returns {Promise<string|null>} 생성된 콘텐츠 또는 오류 시 null
 */
async function generateContent(system_prompt, user_prompt, api_key, model = "gpt-4o") {
    const url = "https://api.openai.com/v1/chat/completions";
    const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${api_key}`,
    };
    const data = {
        model: model,
        messages: [
            {
                role: "system",
                content: system_prompt,
            },
            {
                role: "user",
                content: user_prompt,
            },
        ],
        temperature: 0.75,
        max_tokens: 16384, // Note: While the Python code specifies 16384, check if this is the intended value or if a smaller default like 4096 might be more appropriate depending on usage.
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(data),
        });

        if (!response.ok) {
            // Attempt to read the error response body
            let errorBody = null;
            try {
                errorBody = await response.json();
            } catch (parseError) {
                // Ignore if the body isn't valid JSON
            }
            console.error(`OpenAI API 호출 중 오류 발생: ${response.status} ${response.statusText}`, errorBody || '');
            return null; // Return null on non-OK responses
        }

        const responseData = await response.json();

        if (responseData && responseData.choices && responseData.choices.length > 0) {
            return responseData.choices[0].message.content;
        } else {
            console.error("OpenAI API 응답 형식이 예상과 다릅니다:", responseData);
            return null;
        }
    } catch (error) {
        // Handle network errors or issues with fetch itself
        console.error("OpenAI API 호출 중 네트워크 또는 fetch 오류 발생:", error);
        // Consider if process.exit(1) is truly desired in a Node.js context
        return null;
    }
}

// Export the function for use in other modules
export { generateContent };
