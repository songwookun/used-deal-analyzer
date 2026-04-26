from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import NotificationLog
from app.services.log_helpers import log_pipeline


async def notify_worker(queue_mgr: QueueManager) -> None:
    """NOTIFY_QUEUE 소비 → 알림 전송(현재 mock) → notification_logs 기록."""
    while True:
        item_data = await queue_mgr.notify_queue.get()
        try:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="notification_send", event="START")

                # mock 전송 (Phase 4에서 Telegram/Discord API로 교체)
                print(f"[알림] 좋은 매물 발견! {item_data.get('title', '')} - {item_data.get('askingPrice', 0)}원")

                log = NotificationLog(
                    itemId=item_data["itemId"],
                    notifyType="TELEGRAM",
                    notifyStatus="COMPLETED",
                )
                session.add(log)
                await session.commit()

                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="notification_send", event="SUCCESS")
        except Exception as e:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="notification_send", event="FAILED",
                                   detail={"error": str(e)})
        finally:
            queue_mgr.notify_queue.task_done()
