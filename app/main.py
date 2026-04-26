import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.routes import router
from app.core.queue_manager import QueueManager
from app.workers.analyze_worker import analyze_worker
from app.workers.collect_worker import collect_worker
from app.workers.notify_worker import notify_worker
from app.workers.validate_worker import validate_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue_mgr = QueueManager(maxsize=100)
    app.state.queue_mgr = queue_mgr
    print("큐 매니저 초기화 완료")

    workers = [
        asyncio.create_task(collect_worker(queue_mgr)),
        asyncio.create_task(validate_worker(queue_mgr)),
        asyncio.create_task(analyze_worker(queue_mgr)),
        asyncio.create_task(notify_worker(queue_mgr)),
    ]
    print("워커 4개 시작 완료")

    yield

    for w in workers:
        w.cancel()
    # return_exceptions=True 안 하면 CancelledError가 위로 터져서 종료 로직 깨짐
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
    return {"status": "ok", "queues": request.app.state.queue_mgr.get_status()}
