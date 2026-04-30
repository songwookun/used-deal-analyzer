from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import Item
from app.services.item_state import ItemStatus, InvalidStateTransition
from app.services.log_helpers import log_pipeline


async def _load_item(session, item_id: int) -> Item | None:
    return (await session.execute(
        select(Item).where(Item.itemId == item_id)
    )).scalar_one_or_none()


async def validate_worker(queue_mgr: QueueManager) -> None:
    """VALIDATE_QUEUE 소비 → seller_check + item_validator 2단계 검증 → ANALYZE_QUEUE로 전달."""
    while True:
        item_data = await queue_mgr.validate_queue.get()
        try:
            async with async_session_factory() as session:
                item = await _load_item(session, item_data["itemId"])
                if item is None:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="validate_worker", event="FAILED",
                                       detail={"reason": "items row 없음"})
                    continue

                item.transition_to(ItemStatus.PROCESSING)
                await session.commit()

                # 1단계: seller_check (판매자 신뢰등급)
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="seller_check", event="START")
                if item_data.get("sellerReliability") == "F":
                    item.transition_to(ItemStatus.SKIPPED,
                                       fail_stage="seller_check",
                                       fail_reason="LOW_RELIABILITY")
                    await session.commit()
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
                    item.transition_to(ItemStatus.SKIPPED,
                                       fail_stage="item_validator",
                                       fail_reason="ALREADY_SOLD")
                    await session.commit()
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="item_validator", event="SKIP",
                                       detail={"reason": "이미 판매 완료"})
                    continue
                if "maxPrice" in item_data and item_data.get("askingPrice", 0) > item_data.get("maxPrice", 0):
                    item.transition_to(ItemStatus.SKIPPED,
                                       fail_stage="item_validator",
                                       fail_reason="PRICE_OVER_LIMIT")
                    await session.commit()
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
                item_id = item_data.get("itemId")
                if isinstance(item_id, int):
                    item = await _load_item(session, item_id)
                    if item is not None:
                        try:
                            item.transition_to(ItemStatus.FAILED,
                                               fail_stage="validate_worker",
                                               fail_reason=type(e).__name__)
                            await session.commit()
                        except InvalidStateTransition:
                            pass
        finally:
            queue_mgr.validate_queue.task_done()
