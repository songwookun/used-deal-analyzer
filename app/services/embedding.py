"""
임베딩 클라이언트 (sentence-transformers 래퍼).

- 텍스트 → 384차원 float 벡터
- 모델은 앱 시작 시 1번 로드 (lifespan), 워커가 의존성으로 받음
- DB 저장은 JSON 문자열 (vector TEXT 컬럼)
- 코사인 유사도 안정성을 위해 normalize_embeddings=True (벡터 길이 1로 정규화)
"""
import json

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


class EmbeddingClient:
    """sentence-transformers 모델 1개를 lifecycle 동안 관리.

    - start(): 디스크에서 모델 로드 (~5초)
    - encode(text): 1건 → numpy ndarray (shape: [384,])
    - encode_to_json(text): DB 저장 가능한 JSON 문자열
    - close(): 리소스 해제 (현재 no-op)
    """

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.model: SentenceTransformer | None = None

    def start(self) -> None:
        """모델 로드. 동기 호출 (lifespan에서 await 없이 실행)."""
        self.model = SentenceTransformer(self.model_name)

    def close(self) -> None:
        self.model = None

    def encode(self, text: str) -> np.ndarray:
        """1건 임베딩.

        normalize_embeddings=True → 벡터 길이가 1로 정규화됨.
        이러면 코사인 유사도 = 단순 dot product 가 됨 (속도/안정성 ↑).
        """
        if self.model is None:
            raise RuntimeError("EmbeddingClient.start() must be called before encode()")
        return self.model.encode(text, normalize_embeddings=True)

    def encode_to_json(self, text: str) -> str:
        """encode 후 JSON 문자열 직렬화. SQLite TEXT 컬럼에 그대로 저장 가능."""
        vec = self.encode(text)
        return json.dumps(vec.tolist())


def json_to_vector(vector_json: str) -> np.ndarray:
    """DB에서 꺼낸 JSON 문자열 → numpy 벡터 (다음 phase 검색 시 사용)."""
    return np.array(json.loads(vector_json), dtype=np.float32)
