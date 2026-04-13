"""
[TASK-008] collect_worker — COLLECT_QUEUE 소비자 (첫 번째 워커)

ARCHITECTURE.md 7-1, 10번 섹션 Worker 코드 뼈대 참고.
COLLECT_QUEUE에서 매물을 꺼내서 중복 체크 후 VALIDATE_QUEUE로 넘기는 역할.
"""


"""
[요구사항 1] import

- asyncio
- sqlalchemy에서 select
- app.core.queue_manager에서 QueueManager
- app.core.database에서 async_session_factory
- app.models에서 Item
- app.services.log_helpers에서 log_pipeline
"""

from sqlalchemy import select
from app.core.queue_manager import QueueManager
from app.core.database import async_session_factory
from app.models import Item
from app.services.log_helpers import log_pipeline

"""
[요구사항 2] collect_worker 함수

- async def collect_worker(queue_mgr: QueueManager) -> None
- while True 무한 루프로 큐를 계속 소비

- 루프 내부 흐름:
    1. item_data = await queue_mgr.collect_queue.get()
       → item_data는 dict야. 최소 {"itemId": int, "sellerId": str, ...} 형태

    2. try 블록 안에서:
       a) async with async_session_factory() as session: 으로 DB 세션 열기

       b) log_pipeline 호출 — stage="item_collector", event="START"

       c) 중복 체크: 같은 itemId가 items 테이블에 이미 있는지 조회
          - result = await session.execute(select(Item).where(Item.itemId == item_data["itemId"]))
          - existing = result.scalar_one_or_none()
          - 이미 있으면 → log_pipeline(event="SKIP", detail={"reason": "이미 수집된 매물"})
                         → continue (다음 매물로)

       d) 중복 아니면 → VALIDATE_QUEUE에 put
          - await queue_mgr.validate_queue.put(item_data)

       e) log_pipeline 호출 — event="SUCCESS"

    3. except Exception as e:
       - log_pipeline 호출 — event="FAILED", detail={"error": str(e)}
       - 워커는 절대 죽으면 안 됨! except에서 continue

    4. finally:
       - queue_mgr.collect_queue.task_done()
       - get() 했으면 반드시 task_done() 호출해야 join()이 풀림

[주의] try-except-finally 구조 중요:
  - try: 정상 로직
  - except: 에러 나도 워커 안 죽게
  - finally: task_done()은 성공/실패 상관없이 항상 호출
"""

async def collect_worker(queue_mgr: QueueManager) -> None:
    while True:
        item_data = await queue_mgr.collect_queue.get()
        try:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="item_collector", event="START")

                result = await session.execute(select(Item).where(Item.itemId == item_data["itemId"]))
                existing = result.scalar_one_or_none()
                if existing:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="item_collector", event="SKIP",
                                       detail={"reason": "이미 수집된 매물"})
                    continue

                await queue_mgr.validate_queue.put(item_data)

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="item_collector", event="SUCCESS")

        except Exception as e:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="item_collector", event="FAILED",
                                   detail={"error": str(e)})
        finally:
            queue_mgr.collect_queue.task_done()
