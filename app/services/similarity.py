"""
코사인 유사도 계산.

- 단건: cosine_similarity(a, b) → float
- 일괄: cosine_similarity_batch(query, matrix) → ndarray (N,)

Phase 3-4a에서 normalize_embeddings=True 로 저장했으므로
정규화 벡터에선 cos(A, B) = A·B (dot product) 이다.
이번 모듈은 정규화 가정으로 짜되, 외부에서 정규화 안 된 벡터가 와도
동작하도록 안전한 구현(분모 포함)을 둔다.
"""
import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """단건 코사인 유사도.

    정규화되지 않은 벡터에도 안전. 분모 0인 경우 0.0 반환.
    """
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def cosine_similarity_batch(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """N개 벡터 일괄 비교.

    query: (D,)
    matrix: (N, D)
    return: scores (N,) — matrix[i]와 query의 코사인 유사도

    구현
    -----
    정규화 가정: scores = matrix @ query
    안전 구현:   각 행 / 그 행의 norm, query / query norm 으로 나눔

    여기선 안전 구현 사용. for-loop 없이 numpy vectorization.
    """
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)

    # 행별 L2 norm: (N,)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    query_norm = np.linalg.norm(query)

    if query_norm == 0:
        return np.zeros(matrix.shape[0], dtype=np.float32)

    # 분모 0 방지: norm이 0인 행은 score 0 처리
    safe_denom = matrix_norms * query_norm
    safe_denom[safe_denom == 0] = 1.0

    scores = (matrix @ query) / safe_denom
    scores[matrix_norms == 0] = 0.0
    return scores.astype(np.float32)
