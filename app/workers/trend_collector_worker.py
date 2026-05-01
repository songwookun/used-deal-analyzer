import asyncio

from app.core.database import async_session_factory
from app.models import CategoryTrend
from app.services.datalab_client import DataLabClient
from app.services.trend_cache import TrendCache


COLLECT_INTERVAL_SECONDS = 24 * 60 * 60   # 1일


async def trend_collector_worker(
    client: DataLabClient,
    cache: TrendCache,
    interval_seconds: int = COLLECT_INTERVAL_SECONDS,
) -> None:
    """주기적으로 데이터랩에서 카테고리 트렌드 수집 → DB + 캐시 갱신."""
    # 첫 fetch는 lifespan에서 호출 후 워커는 sleep으로 진입 (즉시 중복 호출 회피)
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await collect_once(client, cache)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[trend] collect failed: {type(exc).__name__}: {exc}")


async def collect_once(client: DataLabClient, cache: TrendCache) -> int:
    """1회 수집 사이클 (lifespan startup에서도 동일 함수 호출). 반환: 갱신된 카테고리 수."""
    entries = await client.fetch_all_categories()
    if not entries:
        return 0

    async with async_session_factory() as session:
        for e in entries:
            session.add(CategoryTrend(
                category=e["category"],
                naverCid=e["cid"],
                periodStart=e["periodStart"],
                periodEnd=e["periodEnd"],
                changePercent=e["changePercent"],
                label=e["label"],
                rawSeries={"series": e["series"]},
            ))
        await session.commit()

    cache.update(entries)
    return len(entries)
