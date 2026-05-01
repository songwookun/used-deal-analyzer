import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import Item
from app.services.item_state import ItemStatus, InvalidStateTransition
from app.services.log_helpers import log_pipeline


# retry 시도 횟수별 다음 시도까지 대기 (초). 길이 = MAX_RETRIES.
RETRY_DELAYS_SECONDS = [60, 300, 1800]
MAX_RETRIES = len(RETRY_DELAYS_SECONDS)
RETRY_INTERVAL_SECONDS = 30


def _backoff_delay(retry_count: int) -> int:
    idx = min(retry_count, MAX_RETRIES - 1)
    return RETRY_DELAYS_SECONDS[idx]


async def retry_worker(
    queue_mgr: QueueManager,
    interval_seconds: int = RETRY_INTERVAL_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> None:
    """주기적으로 재시도 가능한 TIMEOUT 매물을 PENDING으로 reset 후 큐에 재투입."""
    while True:
        try:
            await _retry_once(queue_mgr, max_retries)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[retry] sweep failed: {type(e).__name__}: {e}")
        await asyncio.sleep(interval_seconds)


async def _retry_once(queue_mgr: QueueManager, max_retries: int) -> int:
    """반환: 재투입 건수."""
    now = datetime.now()
    requeued = 0

    async with async_session_factory() as session:
        rows = (await session.execute(
            select(Item).where(
                Item.status == ItemStatus.TIMEOUT.value,
                Item.retryCount < max_retries,
                (Item.nextRetryAt.is_(None)) | (Item.nextRetryAt <= now),
            )
        )).scalars().all()

        for item in rows:
            raw_input = item.rawInput
            item_id = item.itemId
            seller_id = item.sellerId
            current_count = item.retryCount

            if raw_input is None:
                item.failReason = "NO_RAW_INPUT"
                item.retryCount = max_retries
                await session.commit()
                continue

            # sweeper가 막 마감해 nextRetryAt이 NULL인 매물은 첫 backoff 후로 미룸 (즉시 retry 방지)
            if item.nextRetryAt is None:
                item.nextRetryAt = now + timedelta(seconds=_backoff_delay(current_count))
                await session.commit()
                continue

            try:
                item.transition_to(ItemStatus.PENDING)
                item.retryCount = current_count + 1
                # 다음 retry까지 대기 시간 (또 실패해서 TIMEOUT되면 사용)
                item.nextRetryAt = now + timedelta(
                    seconds=_backoff_delay(current_count + 1)
                )
                item.failStage = None
                item.failReason = None
                await session.commit()
            except InvalidStateTransition:
                continue

            await queue_mgr.analyze_queue.put(raw_input)
            await log_pipeline(
                session, item_id=item_id, seller_id=seller_id,
                stage="retry", event="REQUEUE",
                detail={"attempt": current_count + 1, "queue": "analyze"},
            )
            requeued += 1

        # 재시도 한도에 도달한 매물은 failReason을 MAX_RETRIES_EXCEEDED로 마감
        exhausted = (await session.execute(
            select(Item).where(
                Item.status == ItemStatus.TIMEOUT.value,
                Item.retryCount >= max_retries,
                (Item.failReason.is_(None)) | (Item.failReason == "PROCESSING_TIMEOUT"),
            )
        )).scalars().all()
        for item in exhausted:
            ex_id = item.itemId
            ex_seller = item.sellerId
            ex_count = item.retryCount
            item.failReason = "MAX_RETRIES_EXCEEDED"
            await session.commit()
            await log_pipeline(
                session, item_id=ex_id, seller_id=ex_seller,
                stage="retry", event="EXHAUSTED",
                detail={"retryCount": ex_count},
            )

        return requeued
