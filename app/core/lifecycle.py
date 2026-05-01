import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import Item
from app.services.item_state import ItemStatus


# 전역 shutdown 신호. 큐 처리 워커들이 매 루프에서 체크.
shutdown_event = asyncio.Event()

# graceful 종료 시 큐 워커가 진행 중 매물을 마무리할 최대 시간.
GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS = 30


async def recover_pending_items(queue_mgr: QueueManager) -> int:
    """startup 시 PENDING 매물을 validate_queue로 재투입. 반환: 복구 건수.

    PENDING = collect_worker가 INSERT는 했지만 validate_queue.put 직전에 종료.
    collect_queue로 보내면 중복 체크에 SKIP되어 영원히 박힘 → validate_queue로 직접.
    """
    recovered = 0
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(Item).where(Item.status == ItemStatus.PENDING.value)
        )).scalars().all()
        for item in rows:
            if item.rawInput is None:
                continue
            await queue_mgr.validate_queue.put(item.rawInput)
            recovered += 1
    return recovered
