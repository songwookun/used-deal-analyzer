import re

from app.services.external_client import ExternalClient


NAVER_BASE_URL = "https://openapi.naver.com"
SHOP_ENDPOINT = "/v1/search/shop.json"

_HTML_TAG = re.compile(r"<[^>]+>")
_AMP = re.compile(r"&(amp|lt|gt|quot|#39);")


def _strip_html(s: str) -> str:
    """네이버 쇼핑 응답 title은 <b>...</b>로 검색어 강조 + HTML entity 섞임."""
    s = _HTML_TAG.sub("", s)
    s = _AMP.sub(lambda m: {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "#39": "'"}[m.group(1)], s)
    return s.strip()


class NaverShopClient:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = ExternalClient(base_url=NAVER_BASE_URL)

    async def start(self) -> None:
        await self._client.start()

    async def close(self) -> None:
        await self._client.close()

    async def search(self, query: str, display: int = 20) -> list[dict]:
        """키워드 검색 → 정규화된 상품 dict 리스트.
        가격 0(광고/번들) 제외. HTML 태그 제거.
        """
        headers = {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
        }
        params = {"query": query, "display": min(max(display, 1), 100), "sort": "sim"}
        resp = await self._client.request(
            "GET", SHOP_ENDPOINT,
            api_type="SHOP_API", headers=headers, params=params,
        )
        data = resp.json()
        items = data.get("items", []) or []
        clean: list[dict] = []
        for it in items:
            try:
                lprice = int(it.get("lprice", "0") or 0)
            except (ValueError, TypeError):
                lprice = 0
            if lprice <= 0:
                continue
            clean.append({
                "title": _strip_html(it.get("title", "")),
                "price": lprice,
                "mallName": it.get("mallName") or "",
                "category1": it.get("category1") or "",
                "category2": it.get("category2") or "",
                "link": it.get("link") or "",
                "image": it.get("image") or "",
            })
        return clean
