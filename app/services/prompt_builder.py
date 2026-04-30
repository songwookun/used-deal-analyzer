"""
S-Prompt 빌더.

- RAG 검색 결과(유사 매물)를 LLM 프롬프트에 markdown 표로 끼워넣는다.
- 유사 매물이 없으면(cold-start) RAG context 없는 기본 프롬프트로 우아하게 fallback.

명명 규칙:
- "S-Prompt" = Similar-augmented Prompt (검색 사례를 참조하는 프롬프트)
"""
from app.services.similar_search import SimilarItem


def _format_price(price: int | None) -> str:
    """가격 → 사람이 읽기 쉬운 표시 (천 단위 콤마 + '원'). None이면 '?'."""
    if price is None:
        return "?"
    return f"{price:,}원"


def _build_similar_table(similar_items: list[SimilarItem]) -> str:
    """검색 결과 → markdown 표 1개. 빈 리스트면 빈 문자열."""
    if not similar_items:
        return ""

    lines = [
        "[참고: DB에 저장된 유사 매물]",
        "| 제목 | 카테고리 | 호가 | 분석된 시세 | 유사도 |",
        "|---|---|---|---|---|",
    ]
    for s in similar_items:
        lines.append(
            f"| {s.title} | {s.category or '?'} | {_format_price(s.price)} | "
            f"{_format_price(s.analyzedPrice)} | {s.score:.2f} |"
        )
    lines.append("")
    lines.append("위 사례를 참고하여 새 매물의 카테고리와 시세를 판단하세요.")
    lines.append("")
    return "\n".join(lines)


def build_s_prompt(
    item_data: dict,
    similar_items: list[SimilarItem],
    category_enum: list[str],
) -> str:
    """매물 + 검색 결과 → 한국어 LLM 프롬프트.

    similar_items=[] → RAG context 없는 기본 형태 (Phase 3-2 호환).
    """
    title = item_data.get("title", "")
    description = item_data.get("description") or "(설명 없음)"
    asking = item_data.get("askingPrice", 0)
    enum_str = ", ".join(category_enum)

    parts = ["당신은 한국 중고거래 매물 분석 전문가입니다."]

    similar_block = _build_similar_table(similar_items)
    if similar_block:
        parts.append("")
        parts.append(similar_block)

    parts.append(
        f"[새 매물]\n"
        f"- 제목: {title}\n"
        f"- 설명: {description}\n"
        f"- 호가: {asking}원\n"
    )
    parts.append(
        "지침:\n"
        f"1. category는 다음 중 하나: [{enum_str}]\n"
        "2. estimatedPrice는 시세(원, 정수). 호가가 아니라 시장 기준.\n"
        "3. confidence는 0~100 정수. 정보 부족하면 낮게.\n"
        "4. reason은 1~2문장으로 시세 근거.\n"
    )
    parts.append(
        'JSON으로만 응답: '
        '{"category":"...","estimatedPrice":<int>,"confidence":<int>,"reason":"..."}'
    )
    return "\n".join(parts)
