from fastapi import APIRouter, Request


router = APIRouter(prefix="/api", tags=["test"])


@router.post("/test-pipeline")
async def test_pipeline(request: Request):
    """mock 매물 1건을 COLLECT_QUEUE에 투입 → 전체 파이프라인 통과 테스트."""
    queue_mgr = request.app.state.queue_mgr

    mock_item = {
        "itemId": 99999,
        "platform": "danggeun",
        "sellerId": "test_seller_01",
        "sellerReliability": "A",
        "title": "아이폰 15 128GB 미개봉",
        "description": "미개봉 새상품입니다",
        "askingPrice": 800000,
        "category": "ELECTRONICS",
        "isSold": False,
        "maxPrice": 1000000,
    }

    await queue_mgr.collect_queue.put(mock_item)

    return {"message": "mock 매물이 파이프라인에 투입됐습니다", "itemId": 99999}


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
