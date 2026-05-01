"""Phase 7 검색 도메인 LLM 프롬프트 빌더.

상품 N개 + 키워드 트렌드 14일 + 과거 유사 검색 K건 + 가격 통계 → 한국어 종합 분석 프롬프트.
"""
from statistics import mean
from typing import Any


def _format_price(p: int | None) -> str:
    if p is None:
        return "?"
    return f"{p:,}원"


def _build_shop_table(items: list[dict], limit: int = 10) -> str:
    head = [
        "[검색된 상품 (네이버 쇼핑, top 10)]",
        "| # | 제목 | 가격 | 판매처 | 카테고리 |",
        "|---|---|---|---|---|",
    ]
    for i, it in enumerate(items[:limit], 1):
        head.append(
            f"| {i} | {it['title'][:40]} | {_format_price(it.get('price'))} "
            f"| {it.get('mallName', '')} | {it.get('category1', '')} > {it.get('category2', '')} |"
        )
    return "\n".join(head)


def _build_trend_summary(series: list[dict], change_percent: float | None, label: str | None) -> str:
    if not series:
        return "[키워드 검색 트렌드: 데이터 없음]"
    head = ["[키워드 검색 트렌드 (네이버 데이터랩, 최근 14일)]"]
    if label and change_percent is not None:
        head.append(f"- 라벨: {label}, 변화율(7일 평균 vs 이전 7일): {change_percent:+.1f}%")
    avg = mean(s["ratio"] for s in series)
    last = series[-1]["ratio"]
    head.append(f"- 평균 검색지수: {avg:.1f} / 최근 일자: {last:.1f}")
    return "\n".join(head)


def _build_similar_block(similar: list) -> str:
    if not similar:
        return ""
    lines = [
        "[참고: 과거 유사 검색 (RAG)]",
        "| 키워드 | 유사도 | 그 시점 트렌드 | 그 시점 중앙가 |",
        "|---|---|---|---|",
    ]
    for s in similar:
        lines.append(
            f"| {s['query']} | {s['score']:.2f} | "
            f"{s.get('keywordTrendLabel') or '?'} | {_format_price(s.get('medianPrice'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def _build_price_stats_block(stats: dict) -> str:
    if not stats or stats.get("count", 0) == 0:
        return "[가격 통계: 데이터 없음]"
    return (
        "[가격 통계 (검색된 상품 기준)]\n"
        f"- 표본: {stats['count']}건\n"
        f"- 최저가: {_format_price(stats.get('min'))}\n"
        f"- 중앙가: {_format_price(stats.get('median'))}\n"
        f"- 최고가: {_format_price(stats.get('max'))}"
    )


def build_search_prompt(
    query: str,
    shop_results: list[dict],
    trend_series: list[dict],
    trend_label: str | None,
    trend_change_percent: float | None,
    similar_searches: list,
    price_stats: dict,
) -> str:
    parts = [
        "당신은 한국 쇼핑 트렌드/가성비 분석 전문가입니다.",
        f"\n사용자 검색 키워드: \"{query}\"\n",
        _build_shop_table(shop_results),
        "",
        _build_trend_summary(trend_series, trend_change_percent, trend_label),
        "",
        _build_price_stats_block(price_stats),
        "",
        _build_similar_block(similar_searches),
        "지침:",
        "1. categoryRank: 검색 트렌드 + 카테고리(category1)를 보고 이 키워드가 카테고리 내 어디쯤인지 한 줄.",
        "2. valueAssessment: 중앙가/최저가/최고가를 보고 가성비 한 줄 (예: '중앙가는 16만원대, 최저가가 12만원이라 가성비 모델이 존재').",
        "3. alternatives: 검색된 상품 중 호환/대체 가능한 다른 모델 0~3개. 같은 모델 중복 X. 각 항목에 why(짧은 근거).",
        "4. trendForecast: RISING / STEADY / FALLING 중 하나. 시계열 + 과거 유사 검색 패턴을 함께 봄.",
        "5. trendForecastReason: 위 forecast 근거 한 줄.",
        "6. reason: 종합 분석 2~3문장.",
        "",
        'JSON으로만 응답:',
        '{"categoryRank":"...","valueAssessment":"...","alternatives":[{"title":"...","price":N,"mallName":"...","why":"..."}],"trendForecast":"RISING|STEADY|FALLING","trendForecastReason":"...","reason":"..."}',
    ]
    return "\n".join(parts)
