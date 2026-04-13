"""
[TASK-011] notify_worker — NOTIFY_QUEUE 소비자 (네 번째 워커)

ARCHITECTURE.md 7-6(notification_send) 참고.
알림 전송도 아직 실제 API 연동 안 됐으니까,
mock으로 print 출력 + notification_logs에 기록하는 흐름만 잡는다.
"""

"""
[요구사항 1] import

- app.core.queue_manager에서 QueueManager
- app.core.database에서 async_session_factory
- app.models에서 NotificationLog
- app.services.log_helpers에서 log_pipeline
"""
from app.core.queue_manager import QueueManager
from app.core.database import async_session_factory
from app.models import NotificationLog
from app.services.log_helpers import log_pipeline

"""
[요구사항 2] notify_worker 함수

- async def notify_worker(queue_mgr: QueueManager) -> None
- 동일한 while True + try/except/finally 패턴

- 루프 내부 흐름:
    1. item_data = await queue_mgr.notify_queue.get()

    2. try 블록 안에서:
       a) async with async_session_factory() as session:

       b) log_pipeline — stage="notification_send", event="START"

       c) 알림 전송 mock 처리 (나중에 Telegram/Discord API로 교체):
          - print(f"[알림] 좋은 매물 발견! {item_data.get('title', '')} - {item_data.get('askingPrice', 0)}원")

       d) notification_logs에 기록:
          - NotificationLog(
              itemId=item_data["itemId"],
              notifyType="TELEGRAM",       ← mock이니까 고정
              notifyStatus="COMPLETED",    ← mock이니까 바로 성공 처리
            )
          - session.add(log) → await session.commit()

       e) log_pipeline — stage="notification_send", event="SUCCESS"

    3. except Exception as e:
       - 새 세션으로 log_pipeline — stage="notification_send", event="FAILED"

    4. finally:
       - queue_mgr.notify_queue.task_done()
"""
async def notify_worker(queue_mgr: QueueManager) -> None:
    while True:
        item_data = await queue_mgr.notify_queue.get()
        try:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="notification_send", event="START")
                # 알림 전송 mock 처리
                print(f"[알림] 좋은 매물 발견! {item_data.get('title', '')} - {item_data.get('askingPrice', 0)}원")
                # notification_logs에 기록
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
