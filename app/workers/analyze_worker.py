from datetime import datetime

from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import Item
from app.services.log_helpers import log_pipeline


async def analyze_worker(queue_mgr: QueueManager) -> None:
    """ANALYZE_QUEUE 소비 → LLM 분석(현재 mock) → DB 저장 → 좋은 매물이면 NOTIFY_QUEUE로 전달."""
    while True:
        item_data = await queue_mgr.analyze_queue.get()
        try:
            async with async_session_factory() as session:
                # price_analyzer (현재 mock — Phase 3-2에서 실제 LLM으로 교체)
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="START")

                estimated_price = item_data.get("askingPrice", 0)
                category = item_data.get("category", "OTHER")
                llm_confidence = 50
                llm_reason = "mock 분석"

                asking = item_data.get("askingPrice", 0)
                if estimated_price > 0:
                    price_diff = round((asking - estimated_price) / estimated_price * 100, 2)
                else:
                    price_diff = 0.0

                # result_save
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="result_save", event="START")

                item = Item(
                    itemId=item_data["itemId"],
                    platform=item_data.get("platform", "unknown"),
                    sellerId=item_data["sellerId"],
                    sellerReliability=item_data.get("sellerReliability"),
                    title=item_data.get("title", ""),
                    description=item_data.get("description"),
                    askingPrice=asking,
                    estimatedPrice=estimated_price,
                    priceDiffPercent=price_diff,
                    category=category,
                    llmConfidence=llm_confidence,
                    llmReason=llm_reason,
                    status="COMPLETED",
                    collectedAt=item_data.get("collectedAt", datetime.now()),
                    analyzedAt=datetime.now(),
                )
                session.add(item)
                await session.commit()

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="result_save", event="SUCCESS")

                # 좋은 매물(시세보다 20% 이상 저렴)만 NOTIFY_QUEUE로
                if price_diff < -20:
                    await queue_mgr.notify_queue.put(item_data)

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="SUCCESS")

        except Exception as e:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="price_analyzer", event="FAILED",
                                   detail={"error": str(e)})
        finally:
            queue_mgr.analyze_queue.task_done()
