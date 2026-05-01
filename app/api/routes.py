import json
import random
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models import ApiReqResLog, Item, NotificationLog, PastSearch
from app.services.datalab_client import compute_change_percent, label_for_change
from app.services.item_state import ItemStatus
from app.services.preprocess import clean_title
from app.services.search_analyzer import (
    SearchAnalyzerError,
    compute_price_stats,
)
from app.services.search_analyzer import run as analyze_search
from app.services.similar_search import search_similar_searches


router = APIRouter(prefix="/api", tags=["test"])

RECENT_DEFAULT = 10
RECENT_MAX = 100


_MOCK_TEMPLATES = [
    {"title": "아이폰 15 128GB 미개봉", "description": "미개봉 새상품입니다",
     "askingPrice": 800000, "category": "ELECTRONICS", "maxPrice": 1300000},
    {"title": "맥북 m3 14인치 박스풀셋", "description": "직거래만, 1년 사용",
     "askingPrice": 1800000, "category": "ELECTRONICS", "maxPrice": 2500000},
    {"title": "이케아 책상 화이트", "description": "이사로 처분, 흠집 없음",
     "askingPrice": 50000, "category": "FURNITURE", "maxPrice": 100000},
]


@router.post("/_debug/test-pipeline")
async def test_pipeline(
    request: Request,
    seller: str = "A",
    sold: bool = False,
    over_price: bool = False,
):
    """[디버그] mock 매물 1건을 COLLECT_QUEUE에 투입. (Phase 7 이후 강등)

    Query params (검증/디버깅용):
    - seller: 판매자 신뢰등급 (A/B/F). F면 validate에서 SKIPPED.
    - sold: True면 isSold=True → SKIPPED
    - over_price: True면 askingPrice를 maxPrice 초과로 → SKIPPED
    """
    queue_mgr = request.app.state.queue_mgr

    base = random.choice(_MOCK_TEMPLATES)
    item_id = random.randint(100_000, 999_999)
    asking = base["maxPrice"] + 1 if over_price else base["askingPrice"]
    mock_item = {
        "itemId": item_id,
        "platform": "danggeun",
        "sellerId": f"test_seller_{random.randint(1, 99):02d}",
        "sellerReliability": seller,
        "isSold": sold,
        **base,
        "askingPrice": asking,
    }

    await queue_mgr.collect_queue.put(mock_item)

    return {"message": "mock 매물이 파이프라인에 투입됐습니다",
            "itemId": item_id, "title": base["title"],
            "seller": seller, "sold": sold, "over_price": over_price}


@router.get("/stats")
async def stats(request: Request, recent: int = RECENT_DEFAULT) -> dict:
    """검색 도메인 대시보드 집계 (past_searches + category_trends 기준).

    보안 메모: 운영 배포 시 토큰 헤더(X-Stats-Token) 검증 추가 필요.
    """
    n = max(1, min(recent, RECENT_MAX))
    today_start = datetime.combine(date.today(), datetime.min.time())

    async with async_session_factory() as session:
        # 1) 누적 / 오늘
        total_searches = (await session.execute(
            select(func.count(PastSearch.id))
        )).scalar_one()
        today_searches = (await session.execute(
            select(func.count(PastSearch.id))
            .where(PastSearch.createdAt >= today_start)
        )).scalar_one()

        # 2) 트렌드 예측 분포 (LLM이 매긴 RISING/STEADY/FALLING)
        rows = (await session.execute(select(PastSearch.llmAssessment))).all()
        forecast_counts = {"RISING": 0, "STEADY": 0, "FALLING": 0}
        bucket_counts = {"under_10k": 0, "10k_100k": 0, "100k_1m": 0, "over_1m": 0}
        for (assessment,) in rows:
            if isinstance(assessment, dict):
                f = assessment.get("trendForecast")
                if f in forecast_counts:
                    forecast_counts[f] += 1

        # 3) 가격대 분포
        price_rows = (await session.execute(
            select(PastSearch.medianPrice).where(PastSearch.medianPrice.is_not(None))
        )).all()
        for (p,) in price_rows:
            if p is None:
                continue
            if p < 10_000:
                bucket_counts["under_10k"] += 1
            elif p < 100_000:
                bucket_counts["10k_100k"] += 1
            elif p < 1_000_000:
                bucket_counts["100k_1m"] += 1
            else:
                bucket_counts["over_1m"] += 1

        # 4) 인기 검색어 (normalizedQuery 빈도 top 10)
        top_rows = (await session.execute(
            select(PastSearch.normalizedQuery,
                   func.count(PastSearch.id).label("c"),
                   func.max(PastSearch.query).label("last_query"))
            .group_by(PastSearch.normalizedQuery)
            .order_by(func.count(PastSearch.id).desc(), func.max(PastSearch.id).desc())
            .limit(10)
        )).all()
        top_queries = [
            {"normalizedQuery": nq, "count": c, "lastQuery": lq}
            for nq, c, lq in top_rows
        ]

        # 5) 외부 API 호출 통계
        api_rows = (await session.execute(
            select(ApiReqResLog.apiType,
                   ApiReqResLog.event,
                   func.count(ApiReqResLog.id))
            .group_by(ApiReqResLog.apiType, ApiReqResLog.event)
        )).all()
        api_calls: dict[str, dict[str, int]] = {}
        for api_type, event, count in api_rows:
            api_calls.setdefault(api_type, {})[event] = count

        # 6) 최근 검색 N건
        recent_rows = (await session.execute(
            select(PastSearch).order_by(PastSearch.createdAt.desc()).limit(n)
        )).scalars().all()

    trend_cache = getattr(request.app.state, "trend_cache", None)
    trends = trend_cache.all() if trend_cache is not None else {}

    return {
        "asOf": datetime.now().isoformat(),
        "searches": {
            "total": total_searches,
            "today": today_searches,
            "byForecast": forecast_counts,
            "byPriceBucket": bucket_counts,
        },
        "topQueries": top_queries,
        "categoryTrends": trends,
        "apiCalls": api_calls,
        "recent": [
            {
                "id": r.id,
                "query": r.query,
                "medianPrice": r.medianPrice,
                "resultsCount": r.resultsCount,
                "keywordTrendLabel": r.keywordTrendLabel,
                "keywordChangePercent": r.keywordChangePercent,
                "trendForecast": (r.llmAssessment or {}).get("trendForecast"),
                "createdAt": r.createdAt.isoformat() if r.createdAt else None,
            }
            for r in recent_rows
        ],
    }


@router.post("/_debug/notify-test", status_code=202)
async def notify_test(request: Request):
    """notify_worker 검증용. NOTIFY_QUEUE에 가짜 매물 던지기."""
    queue_mgr = request.app.state.queue_mgr
    fake_item = {
        "itemId": random.randint(900000, 999999),
        "sellerId": "debug",
        "title": "[디버그] 좋은 매물 테스트",
        "askingPrice": 100000,
        "estimatedPrice": 200000,
        "priceDiffPercent": -50.0,
        "category": "ELECTRONICS",
        "llmConfidence": 95,
        "llmReason": "디버그 알림 검증용",
    }
    await queue_mgr.notify_queue.put(fake_item)
    return {"queued": fake_item["itemId"]}


@router.post("/_debug/llm-ping", status_code=202)
async def llm_ping(request: Request, payload: dict):
    """LLM 헬스체크/검증용. 큐에 prompt만 던지고 즉시 202 반환. 결과는 콘솔 + api_req_res_logs."""
    queue_mgr = request.app.state.queue_mgr
    msg = {
        "prompt": payload.get("prompt", "안녕, 한 줄로 자기소개"),
        "force_fallback": bool(payload.get("force_fallback", False)),
    }
    await queue_mgr.llm_ping_queue.put(msg)
    return {"message": "llm_ping_queue에 투입됨", "queued": msg}


@router.post("/search")
async def search(request: Request, q: str):
    """Phase 7: 키워드 검색 종합 분석.
    네이버 쇼핑 검색 + 데이터랩 키워드 트렌드 + RAG(과거 검색) + LLM 종합 → SearchAnalysis.
    검색 결과는 past_searches에 누적 (다음 RAG 자원).
    """
    q = (q or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="q too long (max 100)")

    shop_client = request.app.state.shop_client
    datalab_client = request.app.state.datalab_client
    llm_client = request.app.state.llm_client
    embedding_client = request.app.state.embedding_client

    if shop_client is None:
        raise HTTPException(status_code=503,
                            detail="네이버 쇼핑 키 미설정. .env에 NAVER_SHOP_CLIENT_ID/SECRET 추가 필요")

    # 1) 네이버 쇼핑 검색 (401은 권한 누락, 친절한 메시지)
    try:
        shop_results = await shop_client.search(q, display=20)
    except Exception as exc:
        msg = str(exc)
        if "401" in msg:
            raise HTTPException(
                status_code=503,
                detail=("네이버 쇼핑 검색 API 권한 없음 (401). "
                        "네이버 개발자 센터(developers.naver.com/apps) → 본인 애플리케이션 → "
                        "'사용 API 추가' → '검색' 활성화 후 재시도."),
            )
        raise HTTPException(status_code=502, detail=f"네이버 쇼핑 호출 실패: {msg}")

    # 2) 데이터랩 키워드 트렌드 (선택)
    trend_series: list = []
    trend_label: str | None = None
    trend_change: float | None = None
    if datalab_client is not None:
        try:
            trend_series = await datalab_client.fetch_keyword_trend(q)
        except Exception:
            trend_series = []
    if trend_series:
        trend_change = compute_change_percent(trend_series)
        trend_label = label_for_change(trend_change)

    # 3) 임베딩 + RAG
    cleaned = clean_title(q) or q.lower().strip()
    query_vec = embedding_client.encode(cleaned)
    similar_dataclasses = []
    if query_vec is not None:
        async with async_session_factory() as session:
            similar_dataclasses = await search_similar_searches(
                session, query_vec, top_k=3, min_score=0.4,
            )
    similar_for_prompt = [
        {
            "query": s.query,
            "score": s.score,
            "medianPrice": s.medianPrice,
            "keywordTrendLabel": s.keywordTrendLabel,
            "keywordChangePercent": s.keywordChangePercent,
        }
        for s in similar_dataclasses
    ]

    # 4) 가격 통계
    price_stats = compute_price_stats(shop_results)

    # 5) LLM 종합 분석
    try:
        analysis = await analyze_search(
            llm_client, q, shop_results, trend_series,
            trend_label, trend_change, similar_for_prompt, price_stats,
        )
    except SearchAnalyzerError as e:
        raise HTTPException(status_code=502,
                            detail={"failReason": e.fail_reason, "detail": e.detail})

    analysis_dict = analysis.model_dump(mode="json")

    # 6) past_searches INSERT
    median_price = price_stats.get("median")
    embedding_json = json.dumps(query_vec.tolist())
    async with async_session_factory() as session:
        ps = PastSearch(
            query=q, normalizedQuery=cleaned, embedding=embedding_json,
            resultsCount=len(shop_results),
            medianPrice=median_price,
            keywordTrendLabel=trend_label,
            keywordChangePercent=trend_change,
            llmAssessment=analysis_dict,
            rawResults={"items": shop_results[:10]},
            rawTrend={"series": trend_series},
        )
        session.add(ps)
        await session.commit()
        new_id = ps.id

    return {
        "id": new_id,
        "query": q,
        "normalizedQuery": cleaned,
        "shopResults": shop_results[:10],
        "shopResultsTotal": len(shop_results),
        "trend": {
            "label": trend_label,
            "changePercent": trend_change,
            "series": trend_series,
        },
        "priceStats": price_stats,
        "similarSearches": similar_for_prompt,
        "analysis": analysis_dict,
    }


@router.get("/search/recent")
async def search_recent(limit: int = 10):
    """최근 past_searches N건 (다음 검색 시 자동완성/히스토리용)."""
    n = max(1, min(limit, 50))
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(PastSearch).order_by(PastSearch.createdAt.desc()).limit(n)
        )).scalars().all()
    return [
        {
            "id": r.id,
            "query": r.query,
            "medianPrice": r.medianPrice,
            "keywordTrendLabel": r.keywordTrendLabel,
            "keywordChangePercent": r.keywordChangePercent,
            "createdAt": r.createdAt.isoformat() if r.createdAt else None,
        }
        for r in rows
    ]


@router.get("/search/{search_id}")
async def search_by_id(search_id: int):
    """저장된 과거 검색 1건 그대로 반환 (네이버/LLM 재호출 X)."""
    async with async_session_factory() as session:
        row = (await session.execute(
            select(PastSearch).where(PastSearch.id == search_id)
        )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="search not found")

    raw_results = row.rawResults or {}
    raw_trend = row.rawTrend or {}
    shop_results = raw_results.get("items", []) if isinstance(raw_results, dict) else []
    trend_series = raw_trend.get("series", []) if isinstance(raw_trend, dict) else []

    if shop_results:
        prices = [it["price"] for it in shop_results if it.get("price", 0) > 0]
        price_stats = {
            "count": row.resultsCount,
            "median": row.medianPrice,
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
        }
    else:
        price_stats = {"count": 0}

    return {
        "id": row.id,
        "query": row.query,
        "normalizedQuery": row.normalizedQuery,
        "shopResults": shop_results,
        "shopResultsTotal": row.resultsCount,
        "trend": {
            "label": row.keywordTrendLabel,
            "changePercent": row.keywordChangePercent,
            "series": trend_series,
        },
        "priceStats": price_stats,
        "similarSearches": [],
        "analysis": row.llmAssessment or {},
        "cached": True,
        "cachedAt": row.createdAt.isoformat() if row.createdAt else None,
    }
