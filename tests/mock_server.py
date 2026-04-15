"""
[TASK-016] mock 서버 — ExternalClient 테스트용 가짜 API 서버

FastAPI로 가짜 엔드포인트를 만들어서
ExternalClient의 정상/에러/재시도/타임아웃 시나리오를 테스트할 수 있게 해.
uvicorn으로 별도 포트(8001)에 띄워서 사용.
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncio

"""
app = FastAPI() 생성

의사코드:

GET /items
  → 가짜 매물 목록 반환
  → [{"itemId": 9001, "title": "맥북 프로 M3", "askingPrice": 1500000, ...}, ...]

GET /items/{item_id}
  → 특정 매물 상세 반환
  → {"itemId": item_id, "title": "...", "description": "...", ...}

POST /analyze
  → LLM 분석 결과 흉내
  → request body에서 title 받아서 가짜 estimatedPrice, category 등 반환

POST /notify
  → 알림 전송 흉내
  → {"success": True, "message": "알림 전송 완료"}

GET /error/400
  → 항상 400 반환 (4xx 테스트용)

GET /error/500
  → 항상 500 반환 (5xx 재시도 테스트용)

GET /slow
  → await asyncio.sleep(60) 후 응답 (타임아웃 테스트용, TASK-017)

실행: uvicorn tests.mock_server:app --port 8001
"""

class AnalyzeRequest(BaseModel):
    title: str


def create_mock_server():
    app = FastAPI()

    @app.get("/items")
    async def get_items():
        return [
            {
                "itemId": 9001,
                "title": "맥북 프로 M3",
                "askingPrice": 1500000,
            }
        ]

    @app.get("/items/{item_id}")
    async def get_item_detail(item_id: int):
        return {
            "itemId": item_id,
            "title": f"매물 {item_id}",
            "description": "상세 설명",
        }

    @app.post("/analyze")
    async def analyze(payload: AnalyzeRequest):
        return {
            "title": payload.title,
            "estimatedPrice": 1400000,
            "category": "노트북",
        }

    @app.post("/notify")
    async def notify():
        return {
            "success": True,
            "message": "알림 전송 완료",
        }

    @app.get("/error/400")
    async def error_400():
        return JSONResponse(
            status_code=400,
            content={"detail": "Bad Request"},
        )

    @app.get("/error/500")
    async def error_500():
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )

    @app.get("/slow")
    async def slow_response():
        await asyncio.sleep(60)
        return {"message": "느린 응답 완료"}

    return app

app = create_mock_server()