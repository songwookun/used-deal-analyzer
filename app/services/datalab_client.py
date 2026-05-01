from datetime import date, timedelta
from statistics import mean

from app.services.external_client import ExternalClient


# 우리 8개 enum 중 7개를 네이버 쇼핑카테고리 ID에 매핑.
# OTHER는 의미 모호 → 매핑 X (트렌드 데이터 없는 채로 분석 진행).
CATEGORY_TO_NAVER_CID: dict[str, str] = {
    "ELECTRONICS": "50000003",
    "FURNITURE":   "50000004",
    "FASHION":     "50000000",
    "BOOKS":       "50000007",
    "SPORTS":      "50000008",
    "BEAUTY":      "50000002",
    "KIDS":        "50000005",
}

DATALAB_BASE_URL = "https://openapi.naver.com"
DATALAB_ENDPOINT = "/v1/datalab/shopping/categories"

WINDOW_DAYS = 14
RAISE_THRESHOLD = 15.0
DROP_THRESHOLD = -15.0


def label_for_change(change_percent: float) -> str:
    if change_percent >= RAISE_THRESHOLD:
        return "급상승"
    if change_percent <= DROP_THRESHOLD:
        return "하락"
    return "안정"


def compute_change_percent(series: list[dict]) -> float:
    """[{period, ratio}, ...] → 최근 절반 평균 vs 이전 절반 평균 변화율%."""
    if len(series) < 2:
        return 0.0
    half = len(series) // 2
    prev_avg = mean(s["ratio"] for s in series[:half])
    recent_avg = mean(s["ratio"] for s in series[half:])
    if prev_avg == 0:
        return 0.0
    return round((recent_avg - prev_avg) / prev_avg * 100, 2)


class DataLabClient:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = ExternalClient(base_url=DATALAB_BASE_URL)

    async def start(self) -> None:
        await self._client.start()

    async def close(self) -> None:
        await self._client.close()

    async def fetch_all_categories(self) -> list[dict]:
        """매핑된 카테고리들의 14일 트렌드. 실패한 카테고리는 결과에서 빠짐."""
        end_d = date.today()
        start_d = end_d - timedelta(days=WINDOW_DAYS)
        results: list[dict] = []

        for cat, cid in CATEGORY_TO_NAVER_CID.items():
            try:
                series = await self._fetch_one(cid, start_d, end_d)
            except Exception:
                continue
            change = compute_change_percent(series)
            results.append({
                "category": cat,
                "cid": cid,
                "series": series,
                "periodStart": start_d,
                "periodEnd": end_d,
                "changePercent": change,
                "label": label_for_change(change),
            })
        return results

    async def _fetch_one(self, cid: str, start_d: date, end_d: date) -> list[dict]:
        body = {
            "startDate": start_d.isoformat(),
            "endDate": end_d.isoformat(),
            "timeUnit": "date",
            "category": [{"name": cid, "param": [cid]}],
        }
        headers = {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
            "Content-Type": "application/json",
        }
        resp = await self._client.request(
            "POST", DATALAB_ENDPOINT,
            api_type="DATALAB_API",
            json=body, headers=headers,
        )
        data = resp.json()
        return data["results"][0]["data"]
