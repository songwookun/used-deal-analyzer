from datetime import datetime

from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import Item
from app.services import price_analyzer
from app.services.llm_client import LLMClient
from app.services.log_helpers import log_pipeline


# confidence가 이 값 미만이면 좋은 매물이라도 알림 안 보냄 (분석은 저장)
MIN_CONFIDENCE_FOR_NOTIFY = 30
# estimated 대비 호가가 이 % 이상 저렴하면 좋은 매물
GOOD_DEAL_THRESHOLD_PERCENT = -20


async def analyze_worker(queue_mgr: QueueManager, llm_client: LLMClient) -> None:
    """ANALYZE_QUEUE 소비 → LLM 시세 분석 → DB 저장 → 좋은 매물이면 NOTIFY_QUEUE."""
    while True:
        item_data = await queue_mgr.analyze_queue.get()
        try:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="START")

                analysis = await price_analyzer.run(llm_client, item_data)

                category = analysis["category"]
                estimated_price = int(analysis["estimatedPrice"])
                llm_confidence = int(analysis["confidence"])
                llm_reason = analysis["reason"]

                asking = item_data.get("askingPrice", 0)
                if estimated_price > 0:
                    price_diff = round((asking - estimated_price) / estimated_price * 100, 2)
                else:
                    price_diff = 0.0

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

                # 좋은 매물 + 신뢰도 충분 → NOTIFY_QUEUE
                if price_diff < GOOD_DEAL_THRESHOLD_PERCENT and llm_confidence >= MIN_CONFIDENCE_FOR_NOTIFY:
                    enriched = {
                        **item_data,
                        "estimatedPrice": estimated_price,
                        "priceDiffPercent": price_diff,
                        "category": category,
                        "llmConfidence": llm_confidence,
                        "llmReason": llm_reason,
                    }
                    await queue_mgr.notify_queue.put(enriched)

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="SUCCESS")

        except Exception as e:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1),
                                   seller_id=item_data.get("sellerId", "unknown"),
                                   stage="price_analyzer", event="FAILED",
                                   detail={"error": str(e), "type": type(e).__name__})
        finally:
            queue_mgr.analyze_queue.task_done()
