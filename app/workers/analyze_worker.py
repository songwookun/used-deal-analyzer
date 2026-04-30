import json
from datetime import datetime

from app.core.database import async_session_factory
from app.core.queue_manager import QueueManager
from app.models import Item, ItemEmbedding
from app.services import preprocess, price_analyzer
from app.services.embedding import EmbeddingClient
from app.services.llm_client import LLMClient
from app.services.log_helpers import log_pipeline
from app.services.price_analyzer import PriceAnalyzerError
from app.services.similar_search import search_similar


# confidence가 이 값 미만이면 좋은 매물이라도 알림 안 보냄 (분석은 저장)
MIN_CONFIDENCE_FOR_NOTIFY = 30
# estimated 대비 호가가 이 % 이상 저렴하면 좋은 매물
GOOD_DEAL_THRESHOLD_PERCENT = -20
# RAG 검색 파라미터 (Phase 3-4c)
RAG_TOP_K = 3
RAG_MIN_SCORE = 0.5


async def analyze_worker(
    queue_mgr: QueueManager,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
) -> None:
    """ANALYZE_QUEUE 소비 → LLM 시세 분석 + 검증 → DB 저장 → 임베딩 저장 → 좋은 매물이면 NOTIFY_QUEUE."""
    while True:
        item_data = await queue_mgr.analyze_queue.get()
        try:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="START")

                # === RAG 검색 (Phase 3-4c) ===
                # 1) 텍스트 정규화 + 임베딩 1회 생성 → 검색/저장 모두 재사용
                cleaned = preprocess.clean_title(item_data.get("title", ""))
                query_vec = embedding_client.encode(cleaned) if cleaned else None

                # 2) 유사 매물 검색. 카테고리 필터 X (새 매물은 분류 전).
                #    실패해도 분석은 진행 (best-effort) → cold-start와 동일 흐름
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

                try:
                    result = await price_analyzer.run(llm_client, item_data,
                                                      similar_items=similar_items)
                except PriceAnalyzerError as e:
                    # 검증 실패 → items에 FAILED 저장 + 추적 정보 보존
                    await _save_failed_item(session, item_data, e)
                    await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                       stage="price_analyzer", event="FAILED",
                                       detail={"failReason": e.fail_reason, "detail": e.detail})
                    continue  # 다음 매물

                # 검증 통과 → 정상 흐름
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

                item = Item(
                    itemId=item_data["itemId"],
                    platform=item_data.get("platform", "unknown"),
                    sellerId=item_data["sellerId"],
                    sellerReliability=item_data.get("sellerReliability"),
                    title=item_data.get("title", ""),
                    description=item_data.get("description"),
                    askingPrice=asking,
                    estimatedPrice=estimated_price,
                    priceDiffPercent=price_diff,
                    category=category,
                    llmConfidence=llm_confidence,
                    llmReason=llm_reason,
                    status="COMPLETED",
                    collectedAt=item_data.get("collectedAt", datetime.now()),
                    analyzedAt=datetime.now(),
                )
                session.add(item)
                await session.commit()

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="result_save", event="SUCCESS")

                # 임베딩 저장 (앞에서 만든 query_vec 재사용 — 추가 encode 호출 X)
                # 임베딩 실패는 분석 자체를 실패시키지 않음 (best-effort)
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

                # 좋은 매물 + 신뢰도 충분 → NOTIFY_QUEUE
                if price_diff < GOOD_DEAL_THRESHOLD_PERCENT and llm_confidence >= MIN_CONFIDENCE_FOR_NOTIFY:
                    enriched = {
                        **item_data,
                        "estimatedPrice": estimated_price,
                        "priceDiffPercent": price_diff,
                        "category": category,
                        "llmConfidence": llm_confidence,
                        "llmReason": llm_reason,
                    }
                    await queue_mgr.notify_queue.put(enriched)

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="SUCCESS")

        except Exception as e:
            # LLM 네트워크 실패 등 도메인 예외 외 모든 에러 → pipeline_log에만 기록
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1),
                                   seller_id=item_data.get("sellerId", "unknown"),
                                   stage="price_analyzer", event="FAILED",
                                   detail={"error": str(e), "type": type(e).__name__})
        finally:
            queue_mgr.analyze_queue.task_done()


async def _save_failed_item(session, item_data: dict, err: PriceAnalyzerError) -> None:
    """검증 실패 매물도 items에 FAILED 상태로 저장 (운영 추적용)."""
    item = Item(
        itemId=item_data["itemId"],
        platform=item_data.get("platform", "unknown"),
        sellerId=item_data["sellerId"],
        sellerReliability=item_data.get("sellerReliability"),
        title=item_data.get("title", ""),
        description=item_data.get("description"),
        askingPrice=item_data.get("askingPrice", 0),
        status="FAILED",
        failStage="price_analyzer",
        failReason=err.fail_reason,
        collectedAt=item_data.get("collectedAt", datetime.now()),
        analyzedAt=datetime.now(),
    )
    session.add(item)
    await session.commit()
