"""
유사 매물 검색.

흐름:
  query_vector + category 필터
    ↓ DB SELECT (item_embeddings)
    ↓ JSON → numpy matrix (N, 384)
    ↓ scores = cosine_similarity_batch(query, matrix)
    ↓ argpartition top-K + sort
    ↓ min_score 컷오프
  → list[SimilarItem]
"""
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ItemEmbedding, PastSearch
from app.services.embedding import json_to_vector
from app.services.similarity import cosine_similarity_batch


DEFAULT_TOP_K = 3
DEFAULT_MIN_SCORE = 0.5


@dataclass
class SimilarItem:
    """검색 결과 1건. session 종료 후에도 안전하게 다룸."""
    itemId: str
    title: str
    cleanedTitle: str
    score: float
    category: str | None
    price: int | None
    analyzedPrice: int | None


async def search_similar(
    session: AsyncSession,
    query_vector: np.ndarray,
    category: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    exclude_item_id: str | None = None,
) -> list[SimilarItem]:
    """item_embeddings에서 query_vector와 가장 유사한 top_k건 반환.

    - category가 주어지면 같은 카테고리만 (검색 범위 축소)
    - exclude_item_id가 주어지면 SQL에서 제외 (자기 자신 제외용)
    - 결과는 score 내림차순. min_score 미만은 컷.
    """
    # 1) 후보 SELECT — 카테고리/itemId 필터로 검색 범위 축소
    stmt = select(ItemEmbedding)
    if category is not None:
        stmt = stmt.where(ItemEmbedding.category == category)
    if exclude_item_id is not None:
        stmt = stmt.where(ItemEmbedding.itemId != exclude_item_id)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return []

    # 2) JSON → numpy matrix (N, 384)
    vectors = [json_to_vector(row.vector) for row in rows]
    matrix = np.vstack(vectors)  # shape (N, 384)

    # 3) 일괄 코사인 유사도
    scores = cosine_similarity_batch(query_vector, matrix)

    # 4) top-K 인덱스 — argpartition O(N), 그 안에서 sort
    n = scores.shape[0]
    k = min(top_k, n)
    top_idx_unsorted = np.argpartition(scores, -k)[-k:]
    top_idx = top_idx_unsorted[np.argsort(-scores[top_idx_unsorted])]

    # 5) 임계 컷 + dataclass 변환
    results: list[SimilarItem] = []
    for idx in top_idx:
        score = float(scores[idx])
        if score < min_score:
            continue
        row = rows[idx]
        results.append(SimilarItem(
            itemId=row.itemId,
            title=row.title,
            cleanedTitle=row.cleanedTitle,
            score=score,
            category=row.category,
            price=row.price,
            analyzedPrice=row.analyzedPrice,
        ))
    return results


@dataclass
class SimilarSearch:
    """past_searches 검색 결과 1건."""
    id: int
    query: str
    normalizedQuery: str
    score: float
    medianPrice: int | None
    keywordTrendLabel: str | None
    keywordChangePercent: float | None
    createdAt: object   # datetime, type 회피용 object


async def search_similar_searches(
    session: AsyncSession,
    query_vector: np.ndarray,
    top_k: int = 3,
    min_score: float = 0.4,
    exclude_id: int | None = None,
) -> list[SimilarSearch]:
    """past_searches에서 query_vector와 가장 유사한 top_k건."""
    stmt = select(PastSearch)
    if exclude_id is not None:
        stmt = stmt.where(PastSearch.id != exclude_id)
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return []

    vectors = [json_to_vector(row.embedding) for row in rows]
    matrix = np.vstack(vectors)
    scores = cosine_similarity_batch(query_vector, matrix)

    n = scores.shape[0]
    k = min(top_k, n)
    top_idx_unsorted = np.argpartition(scores, -k)[-k:]
    top_idx = top_idx_unsorted[np.argsort(-scores[top_idx_unsorted])]

    results: list[SimilarSearch] = []
    for idx in top_idx:
        score = float(scores[idx])
        if score < min_score:
            continue
        row = rows[idx]
        results.append(SimilarSearch(
            id=row.id,
            query=row.query,
            normalizedQuery=row.normalizedQuery,
            score=score,
            medianPrice=row.medianPrice,
            keywordTrendLabel=row.keywordTrendLabel,
            keywordChangePercent=row.keywordChangePercent,
            createdAt=row.createdAt,
        ))
    return results
