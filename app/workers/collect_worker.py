from datetime import datetime

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import Item
from app.services.item_state import ItemStatus
from app.services.log_helpers import log_pipeline


async def collect_worker(queue_mgr: QueueManager) -> None:
    """COLLECT_QUEUE 소비 → items INSERT(PENDING) → VALIDATE_QUEUE로 전달."""
    while True:
        item_data = await queue_mgr.collect_queue.get()
        try:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="item_collector", event="START")

                result = await session.execute(select(Item).where(Item.itemId == item_data["itemId"]))
                existing = result.scalar_one_or_none()
                if existing:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="item_collector", event="SKIP",
                                       detail={"reason": "이미 수집된 매물"})
                    continue

                item = Item(
                    itemId=item_data["itemId"],
                    platform=item_data.get("platform", "unknown"),
                    sellerId=item_data["sellerId"],
                    sellerReliability=item_data.get("sellerReliability"),
                    title=item_data.get("title", ""),
                    description=item_data.get("description"),
                    askingPrice=item_data.get("askingPrice", 0),
                    category="UNKNOWN",
                    status=ItemStatus.PENDING.value,
                    collectedAt=item_data.get("collectedAt", datetime.now()),
                )
                session.add(item)
                await session.commit()

                await queue_mgr.validate_queue.put(item_data)
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="item_collector", event="SUCCESS")

        except Exception as e:
            # 워커는 절대 죽지 않게 — 별도 세션으로 에러 로그만 남기고 다음 루프
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="item_collector", event="FAILED",
                                   detail={"error": str(e)})
        finally:
            # task_done() 안 부르면 join() 영원히 안 풀림
            queue_mgr.collect_queue.task_done()
