"""
[TASK-010] analyze_worker — ANALYZE_QUEUE 소비자 (세 번째 워커)

ARCHITECTURE.md 7-4(price_analyzer), 7-5(result_save) 참고.
LLM 분석은 아직 구현 안 됐으니까, 이번에는 mock 데이터로 분석 결과를 만들고
DB에 저장 + 좋은 매물이면 NOTIFY_QUEUE로 넘기는 흐름만 잡는다.
"""

"""
[요구사항 1] import

- app.core.queue_manager에서 QueueManager
- app.core.database에서 async_session_factory
- app.models에서 Item
- app.services.log_helpers에서 log_pipeline
- datetime에서 datetime
"""
from app.core.queue_manager import QueueManager
from app.core.database import async_session_factory
from app.models import Item
from app.services.log_helpers import log_pipeline
from datetime import datetime

"""
[요구사항 2] analyze_worker 함수

- async def analyze_worker(queue_mgr: QueueManager) -> None
- 동일한 while True + try/except/finally 패턴

- 루프 내부 흐름:
    1. item_data = await queue_mgr.analyze_queue.get()

    2. try 블록 안에서:
       a) async with async_session_factory() as session:

       ── [price_analyzer 단계] ──
       b) log_pipeline — stage="price_analyzer", event="START"

       c) LLM 분석 mock 처리 (나중에 실제 LLM으로 교체할 부분):
          - estimated_price = item_data.get("askingPrice", 0)  ← 일단 판매가 그대로
          - category = item_data.get("category", "OTHER")
          - llm_confidence = 50
          - llm_reason = "mock 분석"

       d) 시세 대비 차이(%) 계산:
          - asking = item_data.get("askingPrice", 0)
          - if estimated_price > 0:
              price_diff = round((asking - estimated_price) / estimated_price * 100, 2)
            else:
              price_diff = 0.0

       ── [result_save 단계] ──
       e) log_pipeline — stage="result_save", event="START"

       f) Item 객체 생성해서 DB 저장:
          - Item(
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
          - session.add(item) → await session.commit()

       g) log_pipeline — stage="result_save", event="SUCCESS"

       ── [좋은 매물 판별] ──
       h) 시세 대비 저렴한 매물만 NOTIFY_QUEUE로 전달:
          - if price_diff < -20:  (시세보다 20% 이상 저렴)
              await queue_mgr.notify_queue.put(item_data)

       i) log_pipeline — stage="price_analyzer", event="SUCCESS"

    3. except Exception as e:
       - 새 세션으로 log_pipeline — stage="price_analyzer", event="FAILED"

    4. finally:
       - queue_mgr.analyze_queue.task_done()
"""
async def analyze_worker(queue_mgr: QueueManager) -> None:
    while True:
        item_data = await queue_mgr.analyze_queue.get()
        try:
            async with async_session_factory() as session:
                # [price_analyzer 단계]
                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="START")

                estimated_price = item_data.get("askingPrice", 0)
                category = item_data.get("category", "OTHER")
                llm_confidence = 50
                llm_reason = "mock 분석"

                asking = item_data.get("askingPrice", 0)
                if estimated_price > 0:
                    price_diff = round((asking - estimated_price) / estimated_price * 100, 2)
                else:
                    price_diff = 0.0

                # [result_save 단계]
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

                # [좋은 매물 판별]
                if price_diff < -20:
                    await queue_mgr.notify_queue.put(item_data)

                await log_pipeline(session, item_id=item_data["itemId"], seller_id=item_data["sellerId"],
                                   stage="price_analyzer", event="SUCCESS")

        except Exception as e:
            async with async_session_factory() as session:
                await log_pipeline(session, item_id=item_data.get("itemId", -1), seller_id=item_data.get("sellerId", "unknown"),
                                   stage="price_analyzer", event="FAILED",
                                   detail={"error": str(e)})
        finally:
            queue_mgr.analyze_queue.task_done() 
    
