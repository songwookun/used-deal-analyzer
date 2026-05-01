import asyncio

from app.core.database import async_session_factory
from app.core.lifecycle import shutdown_event
from app.core.queue_manager import QueueManager
from app.models import NotificationLog
from app.services.log_helpers import log_pipeline
from app.services.notifier import Notifier


async def notify_worker(queue_mgr: QueueManager, notifier: Notifier) -> None:
    """NOTIFY_QUEUE 소비 → notifier.send() → notification_logs 기록."""
    while not shutdown_event.is_set():
        try:
            item_data = await asyncio.wait_for(
                queue_mgr.notify_queue.get(), timeout=1.0
            )
        except asyncio.TimeoutError:
            continue
        try:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1),
                                   seller_id=item_data.get("sellerId", "unknown"),
                                   stage="notification_send", event="START")

                await notifier.send(item_data)

                log = NotificationLog(
                    itemId=item_data["itemId"],
                    notifyType=notifier.name.upper(),
                    notifyStatus="COMPLETED",
                )
                session.add(log)
                await session.commit()

                await log_pipeline(session, item_id=item_data.get("itemId", -1),
                                   seller_id=item_data.get("sellerId", "unknown"),
                                   stage="notification_send", event="SUCCESS")
        except Exception as e:
            async with async_session_factory() as session:
                log = NotificationLog(
                    itemId=item_data.get("itemId", -1),
                    notifyType=notifier.name.upper(),
                    notifyStatus="FAILED",
                    errorDetail={"error": str(e), "type": type(e).__name__},
                )
                session.add(log)
                await session.commit()
                await log_pipeline(session, item_id=item_data.get("itemId", -1),
                                   seller_id=item_data.get("sellerId", "unknown"),
                                   stage="notification_send", event="FAILED",
                                   detail={"error": str(e), "type": type(e).__name__})
        finally:
            queue_mgr.notify_queue.task_done()
