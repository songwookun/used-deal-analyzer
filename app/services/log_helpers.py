from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PipelineLog


async def log_pipeline(
    session: AsyncSession,
    item_id: int,
    seller_id: str,
    stage: str,
    event: str,
    detail: dict | None = None,
) -> None:
    """파이프라인 단계 로그 1건 INSERT + commit."""
    log = PipelineLog(
        itemId=item_id,
        sellerId=seller_id,
        stage=stage,
        event=event,
        detail=detail,
    )
    session.add(log)
    await session.commit()
