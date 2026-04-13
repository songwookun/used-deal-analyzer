"""
[TASK-009] validate_worker — VALIDATE_QUEUE 소비자 (두 번째 워커)

ARCHITECTURE.md 7-2(seller_check), 7-3(item_validator) 참고.
이 워커는 2가지 검증을 순서대로 수행:
  1단계: 판매자 신뢰도 검증 (seller_check)
  2단계: 매물 유효성 검증 (item_validator)
둘 다 통과하면 ANALYZE_QUEUE로 넘긴다.
"""

"""
[요구사항 1] import

- app.core.queue_manager에서 QueueManager
- app.core.database에서 async_session_factory
- app.services.log_helpers에서 log_pipeline
"""

from app.core.queue_manager import QueueManager
from app.core.database import async_session_factory
from app.services.log_helpers import log_pipeline

"""
[요구사항 2] validate_worker 함수

- async def validate_worker(queue_mgr: QueueManager) -> None
- collect_worker와 동일한 while True + try/except/finally 패턴

- 루프 내부 흐름:
    1. item_data = await queue_mgr.validate_queue.get()

    2. try 블록 안에서:
       a) async with async_session_factory() as session:

       ── [1단계: seller_check] ──
       b) log_pipeline — stage="seller_check", event="START"

       c) 판매자 신뢰등급 판정 (item_data에서 판매자 정보 꺼내서 판단)
          - item_data에 "sellerReliability" 키가 있다고 가정
          - 등급이 "F"이면 → log_pipeline(event="SKIP", detail={"reason": "판매자 신뢰등급 F"})
                             → continue
          - 등급이 "F"가 아니면 → log_pipeline(event="SUCCESS")

       ── [2단계: item_validator] ──
       d) log_pipeline — stage="item_validator", event="START"

       e) 매물 유효성 검증 3가지:
          - item_data.get("isSold") == True → SKIP (이미 판매 완료)
          - item_data에 "maxPrice" 키가 있고, item_data["askingPrice"] > item_data["maxPrice"]
            → SKIP (가격 초과)
          - 위 조건에 안 걸리면 통과

       f) 통과 → ANALYZE_QUEUE에 put
          - await queue_mgr.analyze_queue.put(item_data)
          - log_pipeline — stage="item_validator", event="SUCCESS"

    3. except Exception as e:
       - 새 세션으로 log_pipeline — stage="validate_worker", event="FAILED"

    4. finally:
       - queue_mgr.validate_queue.task_done()
"""
async def validate_worker(queue_mgr: QueueManager) -> None:
    while True:
        item_data = await queue_mgr.validate_queue.get()
        try:
            async with async_session_factory() as session:
                # [1단계: seller_check]
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="seller_check", event="START")
                if item_data.get("sellerReliability") == "F":
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="seller_check", event="SKIP",
                                       detail={"reason": "판매자 신뢰등급 F"})
                    continue
                else:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="seller_check", event="SUCCESS")

                # [2단계: item_validator]
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="item_validator", event="START")
                if item_data.get("isSold") == True:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="item_validator", event="SKIP",
                                       detail={"reason": "이미 판매 완료"})
                    continue
                if "maxPrice" in item_data and item_data.get("askingPrice", 0) > item_data.get("maxPrice", 0):
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="item_validator", event="SKIP",
                                       detail={"reason": "가격 초과"})
                    continue

                # 통과 → ANALYZE_QUEUE에 put
                await queue_mgr.analyze_queue.put(item_data)
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="item_validator", event="SUCCESS")

        except Exception as e:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="validate_worker", event="FAILED",
                                   detail={"error": str(e)})
        finally:
            queue_mgr.validate_queue.task_done()
