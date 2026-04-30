"""
매물 텍스트 전처리.

- 임베딩 품질 향상을 위해 의미 없는 노이즈 제거
- "맥북 m3 14인치 (미개봉) 택배비포함" → "맥북 m3 14인치"
- 임베딩 모델은 의미 있는 토큰에 가중치를 더 잘 줌. 노이즈가 많으면 유사도 검색 정확도 ↓
"""
import re


# 한국 중고거래 관용 표현. 매물 본질과 무관한 거래 조건/상태 표시
NOISE_KEYWORDS = [
    "택배비포함",
    "택배비별도",
    "택포",
    "택불포",
    "직거래",
    "직거래만",
    "직접거래",
    "쿨거래",
    "쿨거",
    "네고가능",
    "네고불가",
    "네고",
    "급처",
    "급매",
    "급처분",
    "판매중",
    "판매완료",
    "판매합니다",
    "팝니다",
    "팔아요",
    "할인",
    "최저가",
    "최저",
    "새상품",
    "거의새것",
    "미개봉",
    "사용감없음",
]


# 괄호 안의 메타정보. 보통 상태/조건 표시 ("(미개봉)", "[새상품]", "{급처}")
BRACKET_PATTERN = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")

# 다중 공백 → 단일 공백
MULTI_SPACE_PATTERN = re.compile(r"\s+")


# 긴 키워드부터 제거해야 부분 일치(예: "직거래만" → "만") 방지
_SORTED_NOISE = sorted(NOISE_KEYWORDS, key=len, reverse=True)


def clean_title(text: str) -> str:
    """매물 제목 정규화.

    1. 소문자 변환 (맥북/MacBook 동일 처리)
    2. 괄호 안 메타정보 제거
    3. 노이즈 키워드 제거 (긴 것부터, 부분 일치 방지)
    4. 공백 정리
    """
    if not text:
        return ""

    cleaned = text.lower()
    cleaned = BRACKET_PATTERN.sub(" ", cleaned)

    for kw in _SORTED_NOISE:
        cleaned = cleaned.replace(kw.lower(), " ")

    cleaned = MULTI_SPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned
