import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.lifecycle import (
    GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
    recover_pending_items,
    shutdown_event,
)
from app.core.queue_manager import QueueManager
from app.services.datalab_client import DataLabClient
from app.services.embedding import EmbeddingClient
from app.services.llm_client import GeminiProvider, GroqProvider, LLMClient
from app.services.notifier import DiscordNotifier, LogNotifier, Notifier
from app.services.trend_cache import TrendCache
from app.workers.analyze_worker import analyze_worker
from app.workers.collect_worker import collect_worker
from app.workers.llm_ping_worker import llm_ping_worker
from app.workers.notify_worker import notify_worker
from app.workers.retry_worker import retry_worker
from app.workers.sweeper_worker import sweeper_worker
from app.workers.trend_collector_worker import collect_once as trend_collect_once
from app.workers.trend_collector_worker import trend_collector_worker
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

    embedding_client = EmbeddingClient()
    embedding_client.start()  # 동기 호출 (모델 로드 ~5초). 첫 분석 지연 방지 위해 lifespan에서 1회 로드
    app.state.embedding_client = embedding_client
    print("임베딩 클라이언트 초기화 완료 (paraphrase-multilingual-MiniLM-L12-v2, 384d)")

    notifier: Notifier = (
        DiscordNotifier(settings.DISCORD_WEBHOOK_URL)
        if settings.DISCORD_WEBHOOK_URL
        else LogNotifier()
    )
    await notifier.start()
    app.state.notifier = notifier
    print(f"알림 클라이언트 초기화 완료 ({notifier.name})")

    # Phase 6: 데이터랩 트렌드 (선택)
    trend_cache = TrendCache()
    app.state.trend_cache = trend_cache
    datalab_client: DataLabClient | None = None
    if settings.NAVER_DATALAB_CLIENT_ID and settings.NAVER_DATALAB_CLIENT_SECRET:
        datalab_client = DataLabClient(
            settings.NAVER_DATALAB_CLIENT_ID,
            settings.NAVER_DATALAB_CLIENT_SECRET,
        )
        await datalab_client.start()
        try:
            initial = await trend_collect_once(datalab_client, trend_cache)
            print(f"DataLab 트렌드 클라이언트 시작 + 초기 수집 {initial}개")
        except Exception as exc:
            print(f"DataLab 초기 수집 실패: {type(exc).__name__}: {exc}")
    else:
        print("DataLab 키 없음 → 트렌드 기능 비활성")

    queue_workers_dict = {
        "collect": asyncio.create_task(collect_worker(queue_mgr)),
        "validate": asyncio.create_task(validate_worker(queue_mgr)),
        "analyze": asyncio.create_task(analyze_worker(queue_mgr, llm_client, embedding_client, trend_cache)),
        "notify": asyncio.create_task(notify_worker(queue_mgr, notifier)),
    }
    aux_workers_dict = {
        "llm_ping": asyncio.create_task(llm_ping_worker(queue_mgr, llm_client)),
        "sweeper": asyncio.create_task(sweeper_worker()),
        "retry": asyncio.create_task(retry_worker(queue_mgr)),
    }
    if datalab_client is not None:
        aux_workers_dict["trend"] = asyncio.create_task(
            trend_collector_worker(datalab_client, trend_cache)
        )
    app.state.workers_meta = {**queue_workers_dict, **aux_workers_dict}
    queue_workers = list(queue_workers_dict.values())
    aux_workers = list(aux_workers_dict.values())
    print("워커 4개 + LLM ping + sweeper + retry 시작 완료")

    recovered = await recover_pending_items(queue_mgr)
    if recovered:
        print(f"[recovery] PENDING 매물 {recovered}건 validate_queue 재투입")

    yield

    print("[shutdown] graceful 종료 시작")
    shutdown_event.set()

    _done, pending = await asyncio.wait(
        queue_workers, timeout=GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
    )
    if pending:
        print(f"[shutdown] {len(pending)}개 큐 워커 timeout 초과 → 강제 cancel")
        for w in pending:
            w.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    for w in aux_workers:
        w.cancel()
    await asyncio.gather(*aux_workers, return_exceptions=True)

    embedding_client.close()
    await llm_client.close()
    await notifier.close()
    if datalab_client is not None:
        await datalab_client.close()
    await queue_mgr.shutdown()
    print("[shutdown] 완료")


app = FastAPI(
    title="중고거래 매물 자동 분석 시스템",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health_check(request: Request):
    return {"status": "ok", "queues": request.app.state.queue_mgr.get_status()}


@app.get("/health/live", include_in_schema=False)
async def health_live():
    """프로세스 alive만 확인 (k8s liveness probe용). 항상 200."""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready(request: Request, response: Response):
    """모든 의존성 정상일 때만 200, 하나라도 비정상이면 503 (k8s readiness probe용)."""
    queue_mgr = request.app.state.queue_mgr
    llm_client = request.app.state.llm_client
    workers_meta: dict = getattr(request.app.state, "workers_meta", {})

    queues = queue_mgr.get_status()

    workers = {name: ("dead" if t.done() else "alive")
               for name, t in workers_meta.items()}
    any_dead = any(v == "dead" for v in workers.values())

    db_state = "ok"
    try:
        async with async_session_factory() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=1.0)
    except Exception as e:
        db_state = f"error:{type(e).__name__}"

    llm_state = llm_client.get_health_state()
    llm_ok = (llm_state["primary"] in {"available", "exhausted"} and
              llm_state["fallback"] in {"available", "none"})

    overall_ok = (not any_dead) and (db_state == "ok") and llm_ok
    if not overall_ok:
        response.status_code = 503

    return {
        "status": "ok" if overall_ok else "degraded",
        "components": {
            "queues": queues,
            "workers": workers,
            "db": db_state,
            "llm": llm_state,
        },
    }
