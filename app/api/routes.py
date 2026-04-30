import random

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api", tags=["test"])


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
