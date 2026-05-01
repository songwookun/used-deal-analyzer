import random
from datetime import datetime

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models import Item, NotificationLog
from app.services.item_state import ItemStatus


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


@router.post("/test-pipeline")
async def test_pipeline(
    request: Request,
    seller: str = "A",
    sold: bool = False,
    over_price: bool = False,
):
    """mock 매물 1건을 COLLECT_QUEUE에 투입.

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
    """운영 대시보드용 집계 (status 분포 / failure / retry / notification / trends / recent N).

    보안 메모: 운영 배포 시 토큰 헤더(X-Stats-Token) 검증 추가 필요.
    """
    n = max(1, min(recent, RECENT_MAX))

    async with async_session_factory() as session:
        rows = (await session.execute(
            select(Item.status, func.count(Item.itemId)).group_by(Item.status)
        )).all()
        status_counts = {s.value: 0 for s in ItemStatus}
        for status, count in rows:
            status_counts[status] = count

        fail_stage_rows = (await session.execute(
            select(Item.failStage, func.count(Item.itemId))
            .where(Item.failStage.is_not(None))
            .group_by(Item.failStage)
        )).all()
        fail_reason_rows = (await session.execute(
            select(Item.failReason, func.count(Item.itemId))
            .where(Item.failReason.is_not(None))
            .group_by(Item.failReason)
        )).all()

        total_retried = (await session.execute(
            select(func.count(Item.itemId)).where(Item.retryCount > 0)
        )).scalar_one()
        completed_after_retry = (await session.execute(
            select(func.count(Item.itemId))
            .where(Item.retryCount > 0, Item.status == ItemStatus.COMPLETED.value)
        )).scalar_one()
        exhausted = (await session.execute(
            select(func.count(Item.itemId))
            .where(Item.failReason == "MAX_RETRIES_EXCEEDED")
        )).scalar_one()

        notify_total = (await session.execute(
            select(func.count(NotificationLog.id))
        )).scalar_one()
        notify_status_rows = (await session.execute(
            select(NotificationLog.notifyStatus, func.count(NotificationLog.id))
            .group_by(NotificationLog.notifyStatus)
        )).all()

        recent_items = (await session.execute(
            select(Item)
            .order_by(Item.analyzedAt.desc().nulls_last(), Item.itemId.desc())
            .limit(n)
        )).scalars().all()

    trend_cache = getattr(request.app.state, "trend_cache", None)
    trends = trend_cache.all() if trend_cache is not None else {}

    return {
        "asOf": datetime.now().isoformat(),
        "statusCounts": status_counts,
        "failures": {
            "byStage": {s: c for s, c in fail_stage_rows},
            "byReason": {r: c for r, c in fail_reason_rows},
        },
        "retries": {
            "totalRetried": total_retried,
            "completedAfterRetry": completed_after_retry,
            "exhausted": exhausted,
        },
        "notifications": {
            "total": notify_total,
            "byStatus": {s: c for s, c in notify_status_rows},
        },
        "trends": trends,
        "recent": [
            {
                "itemId": it.itemId, "title": it.title, "status": it.status,
                "category": it.category, "askingPrice": it.askingPrice,
                "estimatedPrice": it.estimatedPrice,
                "priceDiffPercent": it.priceDiffPercent,
                "failStage": it.failStage, "failReason": it.failReason,
                "retryCount": it.retryCount,
                "analyzedAt": it.analyzedAt.isoformat() if it.analyzedAt else None,
                "collectedAt": it.collectedAt.isoformat() if it.collectedAt else None,
            }
            for it in recent_items
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
