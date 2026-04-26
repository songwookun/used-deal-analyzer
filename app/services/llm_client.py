"""
LLM 멀티 프로바이더 클라이언트.

- GeminiProvider / GroqProvider 두 프로바이더 추상화
- LLMClient가 primary→fallback 자동 전환 (rate limit / quota 초과 감지)
- 모든 호출은 ExternalClient를 통해 이뤄짐 → api_req_res_logs에 자동 기록
"""
import json
from datetime import date
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.services.external_client import ExternalClient


class LLMProvider(Protocol):
    """모든 LLM 프로바이더가 따라야 할 인터페이스."""

    name: str

    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def call(self, prompt: str, schema: dict | None = None) -> dict: ...


class QuotaExceededError(Exception):
    """Primary 프로바이더 일일 한도/rate limit 초과 — fallback 트리거용."""


class GeminiProvider:
    """Google AI Studio (Gemini) 프로바이더."""

    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        self._client = ExternalClient(
            base_url=self.BASE_URL,
            read_timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    async def start(self) -> None:
        await self._client.start()

    async def close(self) -> None:
        await self._client.close()

    def _build_request_body(self, prompt: str, schema: dict | None) -> dict:
        """Gemini generateContent API 요청 본문 생성."""
        body: dict[str, Any] = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
            },
        }
        if schema is not None:
            body["generationConfig"]["responseSchema"] = schema
        return body

    async def call(self, prompt: str, schema: dict | None = None) -> dict:
        """Gemini API 호출. quota 초과 시 QuotaExceededError, 그 외 실패는 그대로 raise."""
        url = f"/v1beta/models/{self._model}:generateContent?key={self._api_key}"
        body = self._build_request_body(prompt, schema)

        try:
            response = await self._client.post(url, json=body, api_type="LLM_API")
        except httpx.HTTPStatusError as e:
            # Gemini quota 초과 신호 감지 → 별도 예외로 변환
            if e.response.status_code == 429:
                raise QuotaExceededError(f"Gemini rate limit: {e.response.text}") from e
            if "RESOURCE_EXHAUSTED" in e.response.text or "quota" in e.response.text.lower():
                raise QuotaExceededError(f"Gemini quota exhausted: {e.response.text}") from e
            raise

        # 정상 응답 → candidates[0].content.parts[0].text 추출 → JSON 파싱
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)


class GroqProvider:
    """Groq (OpenAI 호환) 프로바이더."""

    name = "groq"
    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        self._client = ExternalClient(
            base_url=self.BASE_URL,
            read_timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    async def start(self) -> None:
        await self._client.start()

    async def close(self) -> None:
        await self._client.close()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _build_request_body(self, prompt: str, schema: dict | None) -> dict:
        """Groq chat/completions API 요청 본문 생성. (schema는 강제 못 함, prompt에 안내 권장)"""
        _ = schema  # Protocol 시그니처 유지용. Groq는 schema 강제 미지원
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
        }
        return body

    async def call(self, prompt: str, schema: dict | None = None) -> dict:
        """Groq API 호출. quota/rate limit 시 QuotaExceededError, 그 외 실패는 그대로 raise."""
        body = self._build_request_body(prompt, schema)

        try:
            response = await self._client.post(
                "/chat/completions",
                json=body,
                headers=self._auth_headers(),
                api_type="LLM_API",
            )
        except httpx.HTTPStatusError as e:
            # Groq rate limit / quota 감지 → 별도 예외로 변환
            if e.response.status_code == 429:
                raise QuotaExceededError(f"Groq rate limit: {e.response.text}") from e
            if "rate_limit" in e.response.text.lower() or "quota" in e.response.text.lower():
                raise QuotaExceededError(f"Groq quota exhausted: {e.response.text}") from e
            raise

        # 정상 응답 → choices[0].message.content 추출 → JSON 파싱
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return json.loads(text)


class LLMClient:
    """Primary + Fallback 프로바이더 관리. quota 초과 시 자동 전환."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None):
        self.primary = primary
        self.fallback = fallback
        self._primary_quota_blocked_date: date | None = None

    async def start(self) -> None:
        await self.primary.start()
        if self.fallback is not None:
            await self.fallback.start()

    async def close(self) -> None:
        await self.primary.close()
        if self.fallback is not None:
            await self.fallback.close()

    def _is_primary_blocked_today(self) -> bool:
        """오늘 primary가 quota 차단 상태인지 판단 (자정 지나면 자동 해제)."""
        if self._primary_quota_blocked_date is None:
            return False
        return self._primary_quota_blocked_date == date.today()

    async def analyze(self, prompt: str, schema: dict | None = None) -> dict:
        """
        LLM 분석 실행.
        - 오늘 primary 차단 상태면 → 바로 fallback
        - 아니면 primary 시도 → QuotaExceededError면 차단 기록 + fallback
        - fallback 없거나 fallback도 실패면 raise
        """
        # 1. 오늘 차단 플래그 떠 있으면 바로 fallback
        if self._is_primary_blocked_today() and self.fallback is not None:
            return await self.fallback.call(prompt, schema)

        # 2. primary 시도
        try:
            return await self.primary.call(prompt, schema)
        except QuotaExceededError:
            self._primary_quota_blocked_date = date.today()
            if self.fallback is None:
                raise
            return await self.fallback.call(prompt, schema)
