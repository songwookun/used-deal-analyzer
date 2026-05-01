import asyncio
import json
from datetime import datetime

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.lifecycle import shutdown_event
from app.core.queue_manager import QueueManager
from app.models import Item, ItemEmbedding
from app.services import preprocess, price_analyzer
from app.services.embedding import EmbeddingClient
from app.services.item_state import ItemStatus, InvalidStateTransition
from app.services.llm_client import LLMClient
from app.services.log_helpers import log_pipeline
from app.services.price_analyzer import PriceAnalyzerError
from app.services.similar_search import search_similar
from app.services.trend_cache import TrendCache


# confidence가 이 값 미만이면 좋은 매물이라도 알림 안 보냄 (분석은 저장)
MIN_CONFIDENCE_FOR_NOTIFY = 30
# estimated 대비 호가가 이 % 이상 저렴하면 좋은 매물
GOOD_DEAL_THRESHOLD_PERCENT = -20
# RAG 검색 파라미터 (Phase 3-4c)
RAG_TOP_K = 3
RAG_MIN_SCORE = 0.5


async def _load_item(session, item_id: int) -> Item | None:
    return (await session.execute(
        select(Item).where(Item.itemId == item_id)
    )).scalar_one_or_none()


async def analyze_worker(
    queue_mgr: QueueManager,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    trend_cache: TrendCache | None = None,
) -> None:
    """ANALYZE_QUEUE 소비 → PROCESSING UPDATE → RAG + LLM 분석 → COMPLETED/FAILED UPDATE → 임베딩 저장 → NOTIFY."""
    while not shutdown_event.is_set():
        try:
            item_data = await asyncio.wait_for(
                queue_mgr.analyze_queue.get(), timeout=1.0
            )
        except asyncio.TimeoutError:
            continue
        try:
            async with async_session_factory() as session:
                item = await _load_item(session, item_data["itemId"])
                if item is None:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="price_analyzer", event="FAILED",
                                       detail={"reason": "items row 없음"})
                    continue

                try:
                    item.transition_to(ItemStatus.PROCESSING)
                except InvalidStateTransition:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="price_analyzer", event="SKIP",
                                       detail={"reason": f"이미 종착 상태({item.status})"})
                    continue
                await session.commit()

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="START")

                # === RAG 검색 (Phase 3-4c) ===
                cleaned = preprocess.clean_title(item_data.get("title", ""))
                query_vec = embedding_client.encode(cleaned) if cleaned else None

                similar_items = []
                if query_vec is not None:
                    try:
                        similar_items = await search_similar(
                            session,
                            query_vec,
                            top_k=RAG_TOP_K,
                            min_score=RAG_MIN_SCORE,
                        )
                    except Exception as search_err:
                        await log_pipeline(session, item_id=item_data["itemId"],
                                           seller_id=item_data["sellerId"],
                                           stage="rag_search", event="FAILED",
                                           detail={"error": str(search_err)})

                if similar_items:
                    await log_pipeline(session, item_id=item_data["itemId"],
                                       seller_id=item_data["sellerId"],
                                       stage="rag_search", event="SUCCESS",
                                       detail={"count": len(similar_items),
                                               "top_score": round(similar_items[0].score, 4)})

                # === LLM 분석 ===
                trend_summary = trend_cache.all() if trend_cache is not None else None
                try:
                    result = await price_analyzer.run(
                        llm_client, item_data,
                        similar_items=similar_items,
                        trend_summary=trend_summary,
                    )
                except PriceAnalyzerError as e:
                    item.transition_to(ItemStatus.FAILED,
                                       fail_stage="price_analyzer",
                                       fail_reason=e.fail_reason)
                    item.analyzedAt = datetime.now()
                    await session.commit()
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="price_analyzer", event="FAILED",
                                       detail={"failReason": e.fail_reason, "detail": e.detail})
                    continue

                # === 분석 통과 → COMPLETED ===
                category = result.category.value
                estimated_price = result.estimatedPrice
                llm_confidence = result.confidence
                llm_reason = result.reason

                asking = item_data.get("askingPrice", 0)
                if estimated_price > 0:
                    price_diff = round((asking - estimated_price) / estimated_price * 100, 2)
                else:
                    price_diff = 0.0

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="result_save", event="START")

                item.estimatedPrice = estimated_price
                item.priceDiffPercent = price_diff
                item.category = category
                item.llmConfidence = llm_confidence
                item.llmReason = llm_reason
                item.analyzedAt = datetime.now()
                item.transition_to(ItemStatus.COMPLETED)
                await session.commit()

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="result_save", event="SUCCESS")

                # === 임베딩 저장 (best-effort) ===
                try:
                    if query_vec is not None and cleaned:
                        vector_json = json.dumps(query_vec.tolist())
                        embed = ItemEmbedding(
                            itemId=str(item_data["itemId"]),
                            title=item_data.get("title", ""),
                            cleanedTitle=cleaned,
                            category=category,
                            price=asking,
                            analyzedPrice=estimated_price,
                            vector=vector_json,
                        )
                        session.add(embed)
                        await session.commit()
                except Exception as embed_err:
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="embedding", event="FAILED",
                                       detail={"error": str(embed_err), "type": type(embed_err).__name__})

                # === 좋은 매물 NOTIFY ===
                if price_diff < GOOD_DEAL_THRESHOLD_PERCENT and llm_confidence >= MIN_CONFIDENCE_FOR_NOTIFY:
                    enriched = {
                        **item_data,
                        "estimatedPrice": estimated_price,
                        "priceDiffPercent": price_diff,
                        "category": category,
                        "llmConfidence": llm_confidence,
                        "llmReason": llm_reason,
                    }
                    if trend_cache is not None:
                        trend = trend_cache.get(category)
                        if trend:
                            enriched["categoryTrend"] = trend
                    await queue_mgr.notify_queue.put(enriched)

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="SUCCESS")

        except Exception as e:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1),
                                   seller_id=item_data.get("sellerId", "unknown"),
                                   stage="price_analyzer", event="FAILED",
                                   detail={"error": str(e), "type": type(e).__name__})
                item_id = item_data.get("itemId")
                if isinstance(item_id, int):
                    item = await _load_item(session, item_id)
                    if item is not None:
                        try:
                            item.transition_to(ItemStatus.FAILED,
                                               fail_stage="price_analyzer",
                                               fail_reason=type(e).__name__)
                            item.analyzedAt = datetime.now()
                            await session.commit()
                        except InvalidStateTransition:
                            pass
        finally:
            queue_mgr.analyze_queue.task_done()
