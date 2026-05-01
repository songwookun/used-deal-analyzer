"""Phase 7 검색 분석.

shop_results + keyword_trend + similar_searches + price_stats → SearchAnalysis (Pydantic).
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.services.llm_client import LLMClient
from app.services.search_prompt_builder import build_search_prompt


class SearchAnalyzerError(Exception):
    INVALID_JSON = "INVALID_JSON"
    INVALID_FORECAST = "INVALID_FORECAST"
    NO_RESULTS = "NO_RESULTS"

    def __init__(self, fail_reason: str, detail: str = ""):
        self.fail_reason = fail_reason
        self.detail = detail
        super().__init__(f"{fail_reason}: {detail}")


class TrendForecast(str, Enum):
    RISING = "RISING"
    STEADY = "STEADY"
    FALLING = "FALLING"


class Alternative(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    price: int = Field(ge=0)
    mallName: str = ""
    why: str = Field(min_length=1, max_length=200)


class SearchAnalysis(BaseModel):
    categoryRank: str = Field(min_length=1, max_length=300)
    valueAssessment: str = Field(min_length=1, max_length=300)
    alternatives: list[Alternative] = Field(default_factory=list, max_length=5)
    trendForecast: TrendForecast
    trendForecastReason: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=800)


SEARCH_SCHEMA = {
    "type": "object",
    "required": ["categoryRank", "valueAssessment", "alternatives",
                 "trendForecast", "trendForecastReason", "reason"],
    "properties": {
        "categoryRank": {"type": "string"},
        "valueAssessment": {"type": "string"},
        "alternatives": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "price", "mallName", "why"],
                "properties": {
                    "title": {"type": "string"},
                    "price": {"type": "integer"},
                    "mallName": {"type": "string"},
                    "why": {"type": "string"},
                },
            },
        },
        "trendForecast": {"type": "string", "enum": ["RISING", "STEADY", "FALLING"]},
        "trendForecastReason": {"type": "string"},
        "reason": {"type": "string"},
    },
}


def compute_price_stats(items: list[dict]) -> dict:
    prices = [it["price"] for it in items if it.get("price", 0) > 0]
    if not prices:
        return {"count": 0}
    sorted_p = sorted(prices)
    median = sorted_p[len(sorted_p) // 2]
    return {
        "count": len(prices),
        "min": sorted_p[0],
        "max": sorted_p[-1],
        "median": median,
    }


async def run(
    llm_client: LLMClient,
    query: str,
    shop_results: list[dict],
    trend_series: list[dict],
    trend_label: str | None,
    trend_change_percent: float | None,
    similar_searches: list[dict],
    price_stats: dict,
) -> SearchAnalysis:
    if not shop_results:
        raise SearchAnalyzerError(SearchAnalyzerError.NO_RESULTS,
                                   "쇼핑 검색 결과가 비어있음")

    prompt = build_search_prompt(
        query, shop_results, trend_series,
        trend_label, trend_change_percent,
        similar_searches, price_stats,
    )
    raw = await llm_client.analyze(prompt, schema=SEARCH_SCHEMA)
    if not isinstance(raw, dict):
        raise SearchAnalyzerError(
            SearchAnalyzerError.INVALID_JSON,
            f"expected dict, got {type(raw).__name__}",
        )

    try:
        return SearchAnalysis(**raw)
    except ValidationError as e:
        err = e.errors()[0]
        loc = err["loc"][0] if err["loc"] else "?"
        if loc == "trendForecast":
            raise SearchAnalyzerError(SearchAnalyzerError.INVALID_FORECAST, str(err))
        raise SearchAnalyzerError(SearchAnalyzerError.INVALID_JSON, str(err))
