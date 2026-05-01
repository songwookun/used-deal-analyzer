import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models import Item
from app.services.item_state import ItemStatus, InvalidStateTransition
from app.services.log_helpers import log_pipeline


# PROCESSING 상태가 이 시간 이상 지속되면 TIMEOUT 처리
TIMEOUT_THRESHOLD_SECONDS = 300
# sweeper가 한 번 도는 간격
SWEEP_INTERVAL_SECONDS = 60


async def sweeper_worker(
    threshold_seconds: int = TIMEOUT_THRESHOLD_SECONDS,
    interval_seconds: int = SWEEP_INTERVAL_SECONDS,
) -> None:
    """주기적으로 hang된 PROCESSING 매물을 TIMEOUT으로 마감."""
    while True:
        try:
            await _sweep_once(threshold_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[sweeper] sweep failed: {type(e).__name__}: {e}")
        await asyncio.sleep(interval_seconds)


async def _sweep_once(threshold_seconds: int) -> int:
    """현재 시각 - threshold보다 오래 PROCESSING으로 박힌 매물을 TIMEOUT 처리. 반환: 처리 건수."""
    cutoff = datetime.now() - timedelta(seconds=threshold_seconds)
    processed = 0
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(Item).where(
                Item.status == ItemStatus.PROCESSING.value,
                Item.updatedAt < cutoff,
            )
        )).scalars().all()

        for item in rows:
            # commit 후 expire되기 전에 캡처. 의미상으로도 "PROCESSING으로 박힌 시점"이 stuckSince.
            stuck_since = item.updatedAt
            item_id = item.itemId
            seller_id = item.sellerId
            try:
                item.transition_to(
                    ItemStatus.TIMEOUT,
                    fail_stage="sweeper",
                    fail_reason="PROCESSING_TIMEOUT",
                )
                if item.analyzedAt is None:
                    item.analyzedAt = datetime.now()
                await session.commit()
            except InvalidStateTransition:
                continue

            await log_pipeline(
                session,
                item_id=item_id,
                seller_id=seller_id,
                stage="sweeper",
                event="TIMEOUT",
                detail={"stuckSince": stuck_since.isoformat() if stuck_since else None},
            )
            processed += 1
        return processed
