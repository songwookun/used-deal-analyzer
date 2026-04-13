"""
[TASK-012] 테스트용 API 엔드포인트

mock 데이터를 COLLECT_QUEUE에 넣어서 전체 파이프라인 1회 통과를 확인하는 용도.
"""

"""
[요구사항 1] import

- fastapi에서 APIRouter, Request
"""
from fastapi import APIRouter, Request

"""
[요구사항 2] router 생성

- router = APIRouter(prefix="/api", tags=["test"])
"""

router = APIRouter(prefix="/api", tags=["test"])

"""
[요구사항 3] POST /api/test-pipeline 엔드포인트

- @router.post("/test-pipeline")
- async def test_pipeline(request: Request):

- 함수 내부:
    1. request.app.state.queue_mgr 로 큐 매니저 가져오기

    2. mock 매물 데이터 dict 생성:
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

    3. await queue_mgr.collect_queue.put(mock_item)

    4. return {"message": "mock 매물이 파이프라인에 투입됐습니다", "itemId": 99999}
"""
@router.post("/test-pipeline")
async def test_pipeline(request: Request):
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
