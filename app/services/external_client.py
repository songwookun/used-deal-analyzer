"""
외부 HTTP 호출 래퍼 (httpx.AsyncClient).

- api_req_res_logs 자동 기록 (SENT / SUCCESS / FAILED)
- 재시도 (5xx + 네트워크 에러, exponential backoff)
- 타임아웃 세분화 (connect / read / write)
"""
import asyncio
import time
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import async_session_factory
from app.models import ApiReqResLog


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
        # __init__은 동기라 AsyncClient 생성 못함 → start()로 분리
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
            await self._client.aclose()  # close() 아니라 aclose()

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
        except SQLAlchemyError:
            # 로그 기록 실패는 무시 (실서비스에선 별도 로깅)
            pass

    async def request(
        self,
        method: str,
        url: str,
        *,
        api_type: str = "PLATFORM_API",
        max_retries: int = 3,
        **kwargs: Any,
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
                # 네트워크 에러 / 타임아웃 → 재시도 대상
                duration_ms = int((time.time() - start_time) * 1000)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 1s → 2s → 4s
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

            if 400 <= status < 500:
                # 4xx는 재시도해도 같은 결과 → 즉시 실패
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

            # 5xx — 재시도 대상
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
