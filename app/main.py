import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api.routes import router
from app.core.config import settings
from app.core.queue_manager import QueueManager
from app.services.llm_client import GeminiProvider, GroqProvider, LLMClient
from app.workers.analyze_worker import analyze_worker
from app.workers.collect_worker import collect_worker
from app.workers.llm_ping_worker import llm_ping_worker
from app.workers.notify_worker import notify_worker
from app.workers.validate_worker import validate_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue_mgr = QueueManager(maxsize=100)
    app.state.queue_mgr = queue_mgr
    print("큐 매니저 초기화 완료")

    gemini = GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
    groq = GroqProvider(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
    llm_client = LLMClient(primary=gemini, fallback=groq)
    await llm_client.start()
    app.state.llm_client = llm_client
    print("LLM 클라이언트 초기화 완료 (primary=gemini, fallback=groq)")

    workers = [
        asyncio.create_task(collect_worker(queue_mgr)),
        asyncio.create_task(validate_worker(queue_mgr)),
        asyncio.create_task(analyze_worker(queue_mgr, llm_client)),
        asyncio.create_task(notify_worker(queue_mgr)),
        asyncio.create_task(llm_ping_worker(queue_mgr, llm_client)),
    ]
    print("워커 4개 시작 완료")
    print("LLM ping 워커 시작 완료")

    yield

    for w in workers:
        w.cancel()
    # return_exceptions=True 안 하면 CancelledError가 위로 터져서 종료 로직 깨짐
    await asyncio.gather(*workers, return_exceptions=True)
    await llm_client.close()
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
