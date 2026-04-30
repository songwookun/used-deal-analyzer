"""
매물 분석 서비스.

- 입력: 검증을 통과한 매물 dict + (선택) 유사 매물 검색 결과
- 출력: AnalysisResult (Pydantic 검증 통과한 객체)
- prompt_builder로 S-Prompt 조립 → LLMClient.analyze 1회 호출 → 검증 → 결과 반환
- 검증 실패 시 PriceAnalyzerError raise (failReason 코드 보유)
- 그 외 예외(LLM 네트워크 등)는 그대로 raise → analyze_worker가 catch
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.services.llm_client import LLMClient
from app.services.prompt_builder import build_s_prompt
from app.services.similar_search import SimilarItem


class Category(str, Enum):
    ELECTRONICS = "ELECTRONICS"
    FURNITURE = "FURNITURE"
    FASHION = "FASHION"
    BOOKS = "BOOKS"
    SPORTS = "SPORTS"
    BEAUTY = "BEAUTY"
    KIDS = "KIDS"
    OTHER = "OTHER"


CATEGORY_ENUM = [c.value for c in Category]


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


# 가격 sanity 임계: 호가 대비 추정가가 1/10 ~ 10배 이내여야 통과
PRICE_SANITY_MIN_RATIO = 0.1
PRICE_SANITY_MAX_RATIO = 10.0


class AnalysisResult(BaseModel):
    """LLM 응답 검증 모델. 통과한 객체만 worker로 흘러간다."""
    category: Category
    estimatedPrice: int = Field(gt=0)
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


class PriceAnalyzerError(Exception):
    """price_analyzer 도메인 검증 실패. failReason 코드 보유."""
    INVALID_JSON = "INVALID_JSON"
    INVALID_CATEGORY = "INVALID_CATEGORY"
    INVALID_CONFIDENCE = "INVALID_CONFIDENCE"
    INVALID_PRICE = "INVALID_PRICE"

    def __init__(self, fail_reason: str, detail: str = ""):
        self.fail_reason = fail_reason
        self.detail = detail
        super().__init__(f"{fail_reason}: {detail}")


# 프롬프트 빌더는 prompt_builder 모듈로 위임 (Phase 3-4c).
# 검색 결과(similar_items)가 있으면 markdown 표로 끼워넣고, 없으면 기본 프롬프트로 fallback.


def _map_validation_error(err: ValidationError) -> PriceAnalyzerError:
    """Pydantic ValidationError → 도메인 PriceAnalyzerError 매핑.

    첫 번째 에러의 loc를 보고 failReason 분류.
    """
    first = err.errors()[0]
    loc = first["loc"][0] if first["loc"] else None
    detail = f"{first.get('type', '?')} on {loc}: {first.get('msg', '')}"

    if loc == "category":
        return PriceAnalyzerError(PriceAnalyzerError.INVALID_CATEGORY, detail)
    if loc == "confidence":
        return PriceAnalyzerError(PriceAnalyzerError.INVALID_CONFIDENCE, detail)
    if loc == "estimatedPrice":
        return PriceAnalyzerError(PriceAnalyzerError.INVALID_PRICE, detail)
    return PriceAnalyzerError(PriceAnalyzerError.INVALID_JSON, detail)


def _check_price_sanity(estimated: int, asking: int) -> None:
    """호가 대비 추정가가 비현실 범위면 PriceAnalyzerError raise."""
    if asking <= 0:
        # 호가 자체가 비정상이면 sanity 체크 스킵 (askingPrice 검증은 item_validator 책임)
        return
    ratio = estimated / asking
    if not (PRICE_SANITY_MIN_RATIO <= ratio <= PRICE_SANITY_MAX_RATIO):
        raise PriceAnalyzerError(
            PriceAnalyzerError.INVALID_PRICE,
            f"ratio out of [{PRICE_SANITY_MIN_RATIO}, {PRICE_SANITY_MAX_RATIO}]: "
            f"estimated={estimated} / asking={asking} = {ratio:.4f}",
        )


async def run(
    llm_client: LLMClient,
    item_data: dict,
    similar_items: list[SimilarItem] | None = None,
) -> AnalysisResult:
    """매물 분석 1건 실행 (S-Prompt 통합).

    1) prompt_builder.build_s_prompt(item_data, similar_items) → S-Prompt
    2) LLM 호출 → raw dict
    3) AnalysisResult 검증 (필드/타입/enum/범위)
    4) 가격 sanity 체크 (호가 대비 1/10 ~ 10배)
    5) 검증 통과 시 AnalysisResult 반환

    similar_items=None 또는 [] → cold-start. RAG context 없는 기본 프롬프트.
    검증 실패 → PriceAnalyzerError (failReason 보유)
    LLM 자체 실패 → 그 예외 그대로 raise (worker가 처리)
    """
    prompt = build_s_prompt(item_data, similar_items or [], CATEGORY_ENUM)
    raw = await llm_client.analyze(prompt, schema=ANALYSIS_SCHEMA)

    if not isinstance(raw, dict):
        raise PriceAnalyzerError(
            PriceAnalyzerError.INVALID_JSON,
            f"expected dict, got {type(raw).__name__}",
        )

    try:
        result = AnalysisResult(**raw)
    except ValidationError as e:
        raise _map_validation_error(e) from e

    _check_price_sanity(result.estimatedPrice, item_data.get("askingPrice", 0))

    return result
