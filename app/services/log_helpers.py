"""
[TASK-007] 파이프라인 로그 헬퍼 함수

워커들이 매번 PipelineLog 객체를 직접 만들면 코드가 반복돼.
공통 헬퍼 함수 하나 만들어서 워커에서는 한 줄로 로그를 남길 수 있게 해줘.
"""


"""
[요구사항 1] import

- sqlalchemy.ext.asyncio에서 AsyncSession import
- app.models에서 PipelineLog import
"""
from app.models import PipelineLog  
from sqlalchemy.ext.asyncio import AsyncSession

"""
[요구사항 2] log_pipeline 함수

- async 함수로 만들어줘
- 파라미터:
    session: AsyncSession     — DB 세션 (워커에서 넘겨줌)
    item_id: int              — 매물 ID
    seller_id: str            — 판매자 ID
    stage: str                — 파이프라인 단계 (item_collector, seller_check 등)
    event: str                — 이벤트 (START / SUCCESS / FAILED / SKIP)
    detail: dict | None = None — 추가 정보 (에러 메시지, skip 사유 등, 기본값 None)

- 함수 내부:
    1. PipelineLog 인스턴스 생성 (파라미터 그대로 매핑)
    2. session.add(log)
    3. await session.commit()

- 반환값: 없음 (None)

[참고] 워커에서 이렇게 쓸 거야:
    await log_pipeline(session, item_id=123, seller_id="user1",
                       stage="item_collector", event="START")
    await log_pipeline(session, item_id=123, seller_id="user1",
                       stage="item_collector", event="FAILED",
                       detail={"error": "API 타임아웃"})
"""

async def log_pipeline(session: AsyncSession, item_id: int, seller_id: str,
                       stage: str, event: str, detail: dict | None = None) -> None:
    log = PipelineLog(
        itemId=item_id,
        sellerId=seller_id,
        stage=stage,
        event=event,
        detail=detail
    )
    session.add(log)
    await session.commit()
