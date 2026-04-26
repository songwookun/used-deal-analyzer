from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.services.log_helpers import log_pipeline


async def validate_worker(queue_mgr: QueueManager) -> None:
    """VALIDATE_QUEUE 소비 → seller_check + item_validator 2단계 검증 → ANALYZE_QUEUE로 전달."""
    while True:
        item_data = await queue_mgr.validate_queue.get()
        try:
            async with async_session_factory() as session:
                # 1단계: seller_check (판매자 신뢰등급)
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="seller_check", event="START")
                if item_data.get("sellerReliability") == "F":
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="seller_check", event="SKIP",
                                       detail={"reason": "판매자 신뢰등급 F"})
                    continue
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="seller_check", event="SUCCESS")

                # 2단계: item_validator (판매상태 + 가격 한도)
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
