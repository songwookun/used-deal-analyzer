"""
매물 분석 서비스.

- 입력: 검증을 통과한 매물 dict (title / description / askingPrice 등)
- 출력: {category, estimatedPrice, confidence, reason}
- LLMClient.analyze(prompt, schema) 1회 호출 → JSON 파싱 결과 그대로 반환
- 실패 시 예외 raise (호출자인 analyze_worker가 catch)
"""
from typing import Any

from app.services.llm_client import LLMClient


CATEGORY_ENUM = [
    "ELECTRONICS",
    "FURNITURE",
    "FASHION",
    "BOOKS",
    "SPORTS",
    "BEAUTY",
    "KIDS",
    "OTHER",
]


# Gemini responseSchema에 그대로 전달. Groq는 강제 못 하지만 prompt 안내로 대체.
ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORY_ENUM},
        "estimatedPrice": {"type": "integer"},
        "confidence": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["category", "estimatedPrice", "confidence", "reason"],
}


def _build_prompt(item_data: dict) -> str:
    """매물 dict → 한국어 프롬프트 (시스템 지시 + 매물 정보 + JSON 형식 안내 단일 메시지)."""
    title = item_data.get("title", "")
    description = item_data.get("description") or "(설명 없음)"
    asking_price = item_data.get("askingPrice", 0)
    enum_list = ", ".join(CATEGORY_ENUM)

    return (
        "당신은 한국 중고거래 매물 분석 전문가입니다.\n"
        "다음 매물의 카테고리와 적정 시세(원)를 판단하세요.\n\n"
        f"매물 정보:\n"
        f"- 제목: {title}\n"
        f"- 설명: {description}\n"
        f"- 호가: {asking_price}원\n\n"
        "지침:\n"
        f"1. category는 다음 중 하나: [{enum_list}]\n"
        "2. estimatedPrice는 시세(원, 정수). 호가가 아니라 시장 기준.\n"
        "3. confidence는 0~100 정수. 정보 부족하면 낮게.\n"
        "4. reason은 1~2문장으로 시세 근거.\n\n"
        'JSON으로만 응답: {"category":"...","estimatedPrice":<int>,"confidence":<int>,"reason":"..."}'
    )


async def run(llm_client: LLMClient, item_data: dict) -> dict:
    """매물 분석 1건 실행. LLM 호출 → JSON dict 반환."""
    prompt = _build_prompt(item_data)
    return await llm_client.analyze(prompt, schema=ANALYSIS_SCHEMA)
