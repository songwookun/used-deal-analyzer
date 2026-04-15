"""
[TASK-013] ExternalClient — httpx.AsyncClient 래퍼
[TASK-014] request()에서 api_req_res_logs 자동 기록
[TASK-015] 재시도 로직 (exponential backoff)
"""
import asyncio
import time

import httpx
from typing import Any
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import async_session_factory
from app.models import ApiReqResLog

"""
ExternalClient 클래스

__init__(self, base_url: str = "")
  - self._client: httpx.AsyncClient | None = None
  - self._base_url 저장
  - __init__은 동기라 AsyncClient를 여기서 만들 수 없음 → start()에서 생성

async start(self)
  - httpx.AsyncClient 인스턴스 생성 → self._client에 저장
  - base_url, timeout=httpx.Timeout(30.0) 넘겨줘

async close(self)
  - self._client 있으면 aclose() 호출
  - 주의: close()가 아니라 aclose()야

async request(self, method: str, url: str, **kwargs: Any) -> httpx.Response
  - _client 없으면 RuntimeError
  - self._client.request(method, url, **kwargs) 호출
  - raise_for_status()로 4xx/5xx 한 번에 처리
  - response 반환

async get / post — request()에 위임하는 편의 메서드

[TASK-014] request() 안에서 api_req_res_logs 자동 기록

request()에 api_type: str = "PLATFORM_API" 파라미터 추가
  - 호출하는 쪽에서 "LLM_API", "NOTIFY_API" 등을 넘길 수 있게

request() 내부 흐름을 이렇게 바꿔:
  1. call_id = uuid4().hex 생성
  2. DB에 SENT 로그 INSERT (callId, apiType, event="SENT", requestBody 등)
  3. 시간 측정 시작 (time.time())
  4. 실제 HTTP 호출 실행
  5-a. 성공 → event="SUCCESS", httpStatus, responseBody, durationMs 기록
  5-b. 실패 → event="FAILED", httpStatus(있으면), error 내용 기록
  6. raise_for_status()는 로그 기록 후에 해야 함 (안 그러면 실패 로그를 못 남김)

필요한 import 추가:
  - uuid에서 uuid4
  - time
  - app.core.database에서 async_session_factory
  - app.models에서 ApiReqResLog

주의: item_id는 **kwargs에서 꺼내서 쓰되, httpx에는 안 넘어가게 pop 해야 함
  → item_id = kwargs.pop("item_id", None)

[TASK-015] request()에 재시도 로직 추가 (exponential backoff)

request()에 max_retries: int = 3 파라미터 추가

의사코드:
  for attempt in range(max_retries):
      try:
          response = HTTP 호출
          if 성공(2xx) → 로그 남기고 return
          if 서버 에러(5xx) → 재시도 대상
          if 클라이언트 에러(4xx) → 재시도 안 함, 바로 로그 + raise
      except 네트워크 에러 (httpx.RequestError):
          → 재시도 대상

      if 마지막 시도가 아니면:
          wait = 2 ** attempt  (1초, 2초, 4초)
          await asyncio.sleep(wait)
      else:
          마지막 시도도 실패 → FAILED 로그 남기고 raise

핵심:
  - 5xx, 네트워크 에러만 재시도 (서버 문제니까)
  - 4xx는 재시도 안 함 (클라이언트가 잘못한 거니까 다시 해도 같은 결과)
  - SENT 로그는 첫 시도에만, SUCCESS/FAILED 로그는 최종 결과에만
  - import asyncio 필요

[TASK-017] 타임아웃 세분화

지금 Timeout(30.0)은 전체 타임아웃이야 — connect/read/write 구분 없이 통으로 30초.
실무에서는 이걸 나눠:

__init__에 타임아웃 설정 파라미터 3개 추가:
  - connect_timeout: float = 5.0   (서버 연결까지 대기)
  - read_timeout: float = 30.0     (응답 읽기 대기 — LLM 호출은 오래 걸리니까 넉넉하게)
  - write_timeout: float = 10.0    (요청 전송 대기)

start()에서 httpx.Timeout 생성 시 이 값들 사용:
  httpx.Timeout(
      connect=self._connect_timeout,
      read=self._read_timeout,
      write=self._write_timeout,
  )

request()에 per_request 타임아웃 오버라이드 기능:
  kwargs에서 timeout을 pop → 있으면 그 값으로, 없으면 기본값 사용
  → self._client.request(method, url, timeout=..., **kwargs)

주의: httpx.TimeoutException은 httpx.RequestError의 하위 클래스
  → 기존 재시도 로직의 except httpx.RequestError에서 이미 잡힘, 추가 작업 없음
"""

class ExternalClient:
    def __init__(
    self,
    base_url: str = "",
    connect_timeout: float = 5.0,
    read_timeout: float = 30.0,
    write_timeout: float = 10.0,
  ):
        self._client: httpx.AsyncClient | None = None
        self._base_url = base_url

        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout

    async def start(self):
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(
                connect=self._connect_timeout,
                read=self._read_timeout,
                write=self._write_timeout,
            ),
        )

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def _log_api_call(
        self,
        call_id: str,
        api_type: str,
        event: str,
        request_body: Any = None,
        http_status: int | None = None,
        response_body: Any = None,
        duration_ms: int | None = None,
        item_id: Any = None,
    ):
        log_entry = ApiReqResLog(
            callId=call_id,
            apiType=api_type,
            event=event,
            requestBody=request_body,
            httpStatus=http_status,
            responseBody=response_body,
            durationMs=duration_ms,
            itemId=item_id,
        )
        try:
            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()
        except SQLAlchemyError as e:
            # 로그 기록 실패 시 무시 (실서비스라면 로깅 필요)
            pass

    async def request(
            self,
            method: str,
            url: str,
            *, 
            api_type: str = "PLATFORM_API",
            max_retries: int = 3,
            **kwargs: Any
            ) -> httpx.Response:
        if not self._client:
            raise RuntimeError("ExternalClient가 시작되지 않았습니다. start()를 먼저 호출하세요.")

        call_id = uuid4().hex
        item_id = kwargs.pop("item_id", None)
        request_body = kwargs.get("json") or kwargs.get("data")

        await self._log_api_call(
            call_id=call_id,
            api_type=api_type,
            event="SENT",
            request_body=request_body,
            item_id=item_id,
        )

        request_timeout = kwargs.pop("timeout", None)

        for attempt in range(max_retries):
            start_time = time.time()
            try:
                if request_timeout is not None:
                    response = await self._client.request(method, url, timeout=request_timeout, **kwargs)
                else:
                    response = await self._client.request(method, url, **kwargs)
            except httpx.RequestError as e:
                duration_ms = int((time.time() - start_time) * 1000)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                await self._log_api_call(
                    call_id=call_id,
                    api_type=api_type,
                    event="FAILED",
                    request_body=request_body,
                    response_body=str(e),
                    duration_ms=duration_ms,
                    item_id=item_id,
                )
                raise

            duration_ms = int((time.time() - start_time) * 1000)

            status = response.status_code
            if 200 <= status < 300:
                await self._log_api_call(
                    call_id=call_id,
                    api_type=api_type,
                    event="SUCCESS",
                    request_body=request_body,
                    http_status=status,
                    response_body=response.text,
                    duration_ms=duration_ms,
                    item_id=item_id,
                )
                return response
            elif 400 <= status < 500:
                await self._log_api_call(
                    call_id=call_id,
                    api_type=api_type,
                    event="FAILED",
                    request_body=request_body,
                    http_status=status,
                    response_body=response.text,
                    duration_ms=duration_ms,
                    item_id=item_id,
                )
                response.raise_for_status()
            else:  # 5xx
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                await self._log_api_call(
                    call_id=call_id,
                    api_type=api_type,
                    event="FAILED",
                    request_body=request_body,
                    http_status=status,
                    response_body=response.text,
                    duration_ms=duration_ms,
                    item_id=item_id,
                )
                response.raise_for_status()
                return response

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

