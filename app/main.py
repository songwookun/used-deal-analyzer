from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import asyncio

from app.core.queue_manager import QueueManager


@asynccontextmanager
async def lifespan(app: FastAPI):
   """
    [요구사항]

    1. 앱 시작 시 (yield 위쪽)
       - QueueManager 인스턴스를 생성해주세요
       - app.state.queue_mgr에 저장해주세요 (API에서 접근할 수 있게)
       - print로 "큐 매니저 초기화 완료" 출력
   """
   queue_mgr = QueueManager(maxsize=100)
   app.state.queue_mgr = queue_mgr
   print("큐 매니저 초기화 완료")

   """
    2. yield
       - 이 줄을 기준으로 위 = 시작, 아래 = 종료입니다
       - yield는 그대로 두세요
   """
   
   yield

   """
    3. 앱 종료 시 (yield 아래쪽)
       - queue_mgr.shutdown()을 await로 호출해주세요
       - print로 "큐 매니저 종료 완료" 출력
   """
   await queue_mgr.shutdown()
   print("큐 매니저 종료 완료")

app = FastAPI(
    title="중고거래 매물 자동 분석 시스템",
    lifespan=lifespan,
)

@app.get("/health")
async def health_check(request: Request):
    """
    [요구사항]

    - 기존 {"status": "ok"}에 큐 상태도 추가해주세요
    - request.app.state.queue_mgr.get_status()를 호출해서 같이 리턴
    - 예: {"status": "ok", "queues": {"collect": 0, "validate": 0, ...}}
    """
    return {"status": "ok", "queues": request.app.state.queue_mgr.get_status()}
