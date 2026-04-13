from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import asyncio

from app.core.queue_manager import QueueManager


"""
[TASK-012] lifespan에 워커 4개 연결

ARCHITECTURE.md 10번 섹션 main.py 뼈대 참고.
"""

"""
[요구사항 0] 워커 4개 import

- app.workers.collect_worker에서 collect_worker
- app.workers.validate_worker에서 validate_worker
- app.workers.analyze_worker에서 analyze_worker
- app.workers.notify_worker에서 notify_worker
"""
from app.workers.collect_worker import collect_worker
from app.workers.validate_worker import validate_worker
from app.workers.analyze_worker import analyze_worker
from app.workers.notify_worker import notify_worker
from app.api.routes import router

"""
   [요구사항 1] 워커 4개를 asyncio.create_task로 시작

   - workers 리스트에 4개 태스크 생성:
     workers = [
         asyncio.create_task(collect_worker(queue_mgr)),
         asyncio.create_task(validate_worker(queue_mgr)),
         asyncio.create_task(analyze_worker(queue_mgr)),
         asyncio.create_task(notify_worker(queue_mgr)),
     ]
   - print로 "워커 4개 시작 완료" 출력
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    queue_mgr = QueueManager(maxsize=100)
    app.state.queue_mgr = queue_mgr
    print("큐 매니저 초기화 완료")

    # 워커 4개를 리스트로 생성
    workers = [
        asyncio.create_task(collect_worker(queue_mgr)),
        asyncio.create_task(validate_worker(queue_mgr)),
        asyncio.create_task(analyze_worker(queue_mgr)),
        asyncio.create_task(notify_worker(queue_mgr)),
    ]
    print("워커 4개 시작 완료")

    yield

    """
   [요구사항 2] 앱 종료 시 워커 정리

   - 워커는 while True 무한루프라서 자동으로 안 꺼짐
   - for w in workers: w.cancel() 로 각 태스크 취소 요청
   - await asyncio.gather(*workers, return_exceptions=True)
     → return_exceptions=True 해야 CancelledError가 예외로 안 터짐
   - await queue_mgr.shutdown()
   - print로 "워커 종료 완료" 출력
   """

    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
    await queue_mgr.shutdown()
    print("워커 종료 완료")

app = FastAPI(
    title="중고거래 매물 자동 분석 시스템",
    lifespan=lifespan,
)
app.include_router(router)

@app.get("/health")
async def health_check(request: Request):
    """
    [요구사항]

    - 기존 {"status": "ok"}에 큐 상태도 추가해주세요
    - request.app.state.queue_mgr.get_status()를 호출해서 같이 리턴
    - 예: {"status": "ok", "queues": {"collect": 0, "validate": 0, ...}}
    """
    return {"status": "ok", "queues": request.app.state.queue_mgr.get_status()}
