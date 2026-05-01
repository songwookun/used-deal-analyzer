from typing import Protocol

from app.services.external_client import ExternalClient


GOOD_DEAL_COLOR = 0xff4444


class Notifier(Protocol):
    name: str
    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def send(self, item_data: dict) -> None: ...


class LogNotifier:
    """webhook URL이 없을 때 사용. stdout 출력만 (운영 fallback + CI)."""

    name = "log"

    async def start(self) -> None:
        return

    async def close(self) -> None:
        return

    async def send(self, item_data: dict) -> None:
        print(
            f"[알림] {item_data.get('title', '(제목 없음)')} "
            f"- 호가 {item_data.get('askingPrice', 0):,}원 "
            f"/ 시세 {item_data.get('estimatedPrice', '?')} "
            f"/ {item_data.get('priceDiffPercent', '?')}%"
        )


class DiscordNotifier:
    """Discord Webhook으로 embed 메시지 전송. ExternalClient 재사용 → api_req_res_logs 자동 기록."""

    name = "discord"

    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url
        self._client = ExternalClient()

    async def start(self) -> None:
        await self._client.start()

    async def close(self) -> None:
        await self._client.close()

    async def send(self, item_data: dict) -> None:
        payload = {"embeds": [_build_embed(item_data)]}
        await self._client.request(
            "POST",
            self._webhook_url,
            api_type="NOTIFY_API",
            json=payload,
            item_id=item_data.get("itemId"),
        )


def _build_embed(item_data: dict) -> dict:
    title = item_data.get("title", "(제목 없음)")
    asking = item_data.get("askingPrice", 0)
    estimated = item_data.get("estimatedPrice")
    diff = item_data.get("priceDiffPercent")
    category = item_data.get("category", "?")
    confidence = item_data.get("llmConfidence")
    reason = item_data.get("llmReason", "")

    fields = [
        {"name": "카테고리", "value": str(category), "inline": True},
        {"name": "호가", "value": f"{asking:,}원", "inline": True},
    ]
    if estimated is not None:
        fields.append({"name": "추정 시세", "value": f"{estimated:,}원", "inline": True})
    if diff is not None:
        fields.append({"name": "할인율", "value": f"{diff}%", "inline": True})
    if confidence is not None:
        fields.append({"name": "신뢰도", "value": f"{confidence}/100", "inline": True})
    trend = item_data.get("categoryTrend")
    if trend:
        fields.append({
            "name": "카테고리 트렌드",
            "value": f"{trend.get('label','?')} ({trend.get('changePercent', 0):+.1f}%)",
            "inline": True,
        })
    if reason:
        fields.append({"name": "분석", "value": reason[:200], "inline": False})

    return {
        "title": f"🔥 좋은 매물 발견: {title[:80]}",
        "color": GOOD_DEAL_COLOR,
        "fields": fields,
    }
