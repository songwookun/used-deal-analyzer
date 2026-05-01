from threading import RLock


class TrendCache:
    """카테고리 트렌드의 메모리 캐시. analyze/notifier/stats가 공유."""

    def __init__(self):
        self._lock = RLock()
        self._data: dict[str, dict] = {}

    def update(self, entries: list[dict]) -> None:
        with self._lock:
            for e in entries:
                self._data[e["category"]] = {
                    "label": e["label"],
                    "changePercent": e["changePercent"],
                    "periodStart": e["periodStart"].isoformat(),
                    "periodEnd": e["periodEnd"].isoformat(),
                }

    def get(self, category: str) -> dict | None:
        with self._lock:
            entry = self._data.get(category)
            return dict(entry) if entry else None

    def all(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}
