# AI 중고거래 매물 자동 분석 시스템

중고거래 플랫폼(당근, 번개장터 등)의 매물을 자동 수집하고, LLM으로 시세를 분석한 뒤, 좋은 매물을 알림으로 받아보는 비동기 파이프라인 시스템입니다.

---

## 주요 기능

- 키워드 기반 매물 자동 수집 (폴링 방식)
- 판매자 신뢰도 검증 (거래횟수, 매너온도 기반 등급 산정)
- 매물 유효성 검증 (판매 완료 여부, 가격 범위 필터링)
- LLM 기반 카테고리 분류 + 시세 추정 (OpenAI / Ollama)
- 벡터 유사도 기반 유사 매물 검색 + S-Prompt 동적 시세 분석
- 시세 대비 저렴한 매물 자동 알림 (Telegram / Discord)
- 일간 분석 리포트 생성

---

## 아키텍처

4개의 asyncio.Queue로 구성된 비동기 파이프라인입니다. 각 단계는 독립된 Worker가 처리하며, 모든 처리 과정은 pipeline_logs에 기록됩니다.

```
[크롤러/API]
     │
     ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ COLLECT_QUEUE│───▶│VALIDATE_QUEUE│───▶│ANALYZE_QUEUE │───▶│ NOTIFY_QUEUE │
│             │    │             │    │             │    │             │
│ 매물 수집    │    │ 판매자 검증  │    │ LLM 시세분석 │    │ 알림 전송    │
│             │    │ 매물 검증    │    │             │    │ 리포트 생성  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     │                   │                  │                   │
     ▼                   ▼                  ▼                   ▼
  [DB 저장]           [DB 저장]          [DB 저장]           [DB 저장]
  pipeline_log       pipeline_log       pipeline_log       pipeline_log
```

---

## 기술 스택

| 구분 | 기술 | 선택 이유 |
|------|------|-----------|
| 언어 | Python 3.11+ | 비동기 지원, LLM 생태계 |
| 웹 프레임워크 | FastAPI | 비동기 네이티브, lifespan으로 백그라운드 워커 관리 |
| ORM | SQLAlchemy 2.0 (async) | 비동기 세션, expire_on_commit 제어 |
| DB | SQLite (개발) → MariaDB (운영) | 로컬 개발 편의 → 운영 확장 |
| 큐 | asyncio.Queue | 인메모리 비동기 큐, 백프레셔(maxsize) 지원 |
| LLM | OpenAI API / Ollama | 카테고리 분류 + 시세 추정 |
| 임베딩 | sentence-transformers (all-MiniLM-L6-v2) | 매물 텍스트 벡터화, 유사 매물 검색 |
| 마이그레이션 | Alembic | 스키마 버전 관리 |
| 테스트 | pytest + pytest-asyncio | 비동기 테스트 지원 |
| 알림 | Telegram Bot API / Discord Webhook | 무료, 실시간 알림 |

---

## 디렉토리 구조

```
used-deal-analyzer/
├── app/
│   ├── main.py                    # FastAPI 앱 + lifespan (큐/워커 초기화)
│   ├── core/
│   │   ├── config.py              # Pydantic Settings (.env 자동 로드)
│   │   ├── database.py            # SQLAlchemy 비동기 엔진/세션
│   │   └── queue_manager.py       # asyncio.Queue 4개 관리
│   ├── models.py                  # SQLAlchemy 모델 (7개 테이블)
│   ├── services/
│   │   ├── item_collector.py      # 매물 수집 로직
│   │   ├── seller_check.py        # 판매자 신뢰도 검증
│   │   ├── item_validator.py      # 매물 유효성 검증
│   │   ├── preprocess.py          # 매물 텍스트 전처리
│   │   ├── embedding.py           # 텍스트 → 벡터 변환
│   │   ├── similarity.py          # 코사인 유사도 계산
│   │   ├── similar_search.py      # 유사 매물 검색
│   │   ├── prompt_builder.py      # S-Prompt 생성
│   │   ├── price_analyzer.py      # LLM 시세 분석
│   │   ├── result_save.py         # 분석 결과 DB 저장
│   │   ├── notification_send.py   # 알림 전송
│   │   ├── report_generator.py    # 일간 리포트 생성
│   │   ├── external_client.py     # 외부 API 호출 래퍼 (로깅/재시도/타임아웃)
│   │   └── log_helpers.py         # 파이프라인 로그 헬퍼
│   ├── workers/
│   │   ├── collect_worker.py      # COLLECT_QUEUE 소비자
│   │   ├── validate_worker.py     # VALIDATE_QUEUE 소비자
│   │   ├── analyze_worker.py      # ANALYZE_QUEUE 소비자
│   │   └── notify_worker.py       # NOTIFY_QUEUE 소비자
│   └── api/
│       ├── routes.py              # REST API 엔드포인트
│       └── schemas.py             # Pydantic 요청/응답 스키마
├── alembic/                       # DB 마이그레이션
├── tests/                         # 테스트
├── requirements.txt
└── .env                           # 환경변수 (git 미포함)
```

---

## DB 설계 (8개 테이블)

| 테이블 | 역할 |
|--------|------|
| `items` | 매물 마스터 (수집~분석~알림 전체 상태 관리) |
| `item_images` | 매물 이미지 정보 |
| `price_history` | 카테고리별 시세 이력 (스냅샷) |
| `notification_logs` | 알림 전송 상태 추적 (PENDING → COMPLETED/FAILED) |
| `pipeline_logs` | 파이프라인 단계별 처리 로그 |
| `api_req_res_logs` | 외부 API 호출 요청/응답 로그 (UUID 추적) |
| `watch_keywords` | 사용자 감시 키워드 + 최대 가격 설정 |
| `item_embeddings` | 매물 벡터 저장 (유사 매물 검색용) |

---

## 파이프라인 상세

### 1. item_collector (매물 수집)
- watch_keywords 테이블에서 감시 키워드 조회
- 키워드별 새 매물 검색 + 중복 체크
- 새 매물을 COLLECT_QUEUE에 push

### 2. seller_check (판매자 검증)
- 판매자 프로필 조회 (가입일, 거래횟수, 매너온도)
- 신뢰등급 산정: S(우수) / A(양호) / B(보통) / C(주의) / F(위험)
- F등급 → SKIP 처리 (사기 의심)

### 3. item_validator (매물 검증)
- 판매 완료 여부, 가격 범위, 이미지 유무 확인
- 통과 시 ANALYZE_QUEUE로 전달

### 4. price_analyzer (LLM 시세 분석)
- LLM API 호출 → 카테고리 분류 + 상태 판별 + 시세 추정
- price_history와 비교하여 시세 차이(%) 계산
- 좋은 매물만 NOTIFY_QUEUE로 전달

### 5. notification_send (알림 전송)
- 시세 대비 저렴한 매물 → Telegram/Discord 알림
- 전송 실패 시 재시도 (exponential backoff)

### 6. report_generator (리포트 생성)
- 일간 수집/분석 통계, 카테고리별 시세 동향, 추천 매물 Top N

---

## 벡터 유사도 기반 시세 분석 (S-Prompt)

### 개요

매물 제목/설명을 벡터화하여 과거 유사 매물을 검색하고, S-Prompt 방식으로 LLM에 유사 사례를 동적 삽입하여 시세 분석 정확도를 향상시킵니다.

### 처리 흐름

```
[기존] 매물 → LLM이 처음부터 시세 판단 (하드코딩 프롬프트)

[변경] 매물 → 벡터화 → 유사 매물 3건 검색 → S-Prompt + LLM 판단
```

```
새 매물 입력
    ↓
[preprocess] 불필요 텍스트 제거 (택배비 포함, 직거래 등)
    ↓
[embedding] sentence-transformers로 384차원 벡터 변환
    ↓
[similar_search] DB에서 코사인 유사도 상위 3건 검색
    ↓
[prompt_builder] S-Prompt 생성 (유사 사례 3건 + 새 매물)
    ↓
[price_analyzer] LLM 시세 분석 → 결과 반환
    ↓
[DB 저장] item_embeddings에 벡터 저장 (다음 검색용)
```

### 수학적 기반: 코사인 유사도

```
벡터 내적:    AᵀB = Σ(Aᵢ × Bᵢ)
벡터 크기:    ||A|| = √(Σ Aᵢ²)
코사인 유사도: cos(θ) = AᵀB / (||A|| × ||B||)

결과: 0.0 (무관) ~ 1.0 (동일)
```

### item_embeddings 테이블

```sql
CREATE TABLE item_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    itemId TEXT NOT NULL,
    title TEXT NOT NULL,
    cleanedTitle TEXT NOT NULL,
    category TEXT,
    price INTEGER,
    analyzedPrice INTEGER,
    vector TEXT NOT NULL,
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### S-Prompt 구조

```
[고정부 — 역할 + 유형 + 규칙]
너는 중고거래 시세 분석 전문가다.
유사 매물을 참고하여 시세를 추정해.

## 카테고리
- ELECTRONICS: 전자기기
- FASHION: 의류/잡화
- FURNITURE: 가구/인테리어
- HOBBY: 취미/게임/스포츠
- OTHER: 기타

## 주의
- 미개봉/새상품은 시세 +10~20%
- 상태 불량 표기 시 시세 -20~30%

[동적부 — 유사 사례 3건]
1. "아이폰 15 128GB 새상품" → 85만원 (유사도 0.95)
2. "아이폰 15 256GB 미개봉" → 95만원 (유사도 0.88)
3. "아이폰 15 128GB S급" → 78만원 (유사도 0.85)

[파라미터 — 새 매물]
"아이폰 15 128GB 미개봉 풀박스"

[출력 형식]
{"category": "ELECTRONICS", "estimatedPrice": 83만원, "confidence": 0.9}
```

### 핵심 코드

**preprocess.py** — 매물 텍스트 전처리
```python
NOISE_PATTERNS = [
    "택배비 포함", "택배비 별도", "직거래", "택배거래",
    "네고 가능", "네고 불가", "급처", "떨이",
    "연락주세요", "문의주세요", "댓글주세요",
]

def cleanTitle(title: str) -> str:
    cleaned = title
    for pattern in NOISE_PATTERNS:
        cleaned = cleaned.replace(pattern, "")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()
```

**embedding.py** — 텍스트 → 벡터 변환
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

def textToVector(text: str) -> list[float]:
    return model.encode(text).tolist()
```

**similarity.py** — 코사인 유사도 계산
```python
import math

def cosineSimilarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    normA = math.sqrt(sum(x * x for x in a))
    normB = math.sqrt(sum(x * x for x in b))
    if normA == 0 or normB == 0:
        return 0.0
    return dot / (normA * normB)
```

**similar_search.py** — 유사 매물 검색
```python
from app.services.similarity import cosineSimilarity

def findSimilarItems(newVector: list[float], allEmbeddings: list[dict], limit: int = 3) -> list[dict]:
    scored = []
    for item in allEmbeddings:
        score = cosineSimilarity(newVector, item["vector"])
        scored.append({**item, "similarity": round(score, 4)})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]
```

**prompt_builder.py** — S-Prompt 생성
```python
def buildAnalysisPrompt(title: str, similarItems: list[dict]) -> str:
    prompt = """너는 중고거래 시세 분석 전문가다.
유사 매물을 참고하여 새 매물의 카테고리와 적정 시세를 추정해.

## 카테고리
- ELECTRONICS: 전자기기 (스마트폰, 노트북, 태블릿 등)
- FASHION: 의류/잡화 (옷, 신발, 가방 등)
- FURNITURE: 가구/인테리어
- HOBBY: 취미/게임/스포츠
- OTHER: 기타

## 주의
- 미개봉/새상품은 시세 +10~20%
- 상태 불량/하자 표기 시 시세 -20~30%
- 유사 매물이 없으면 일반 시세 기준으로 추정

## 유사 매물
"""
    for i, item in enumerate(similarItems, 1):
        prompt += f"""{i}. "{item['cleanedTitle']}" → {item.get('analyzedPrice', '미분석')}원 (유사도: {item['similarity']})
"""

    prompt += f"""
## 새 매물
{title}

## 응답 (JSON만, 다른 텍스트 없이)
{{"category": "카테고리코드", "estimatedPrice": 추정가격(숫자), "priceRange": {{"min": 최저, "max": 최고}}, "confidence": 0.0~1.0, "reason": "판단 근거"}}"""

    return prompt
```

---

## 실행 방법

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env

# DB 마이그레이션
alembic upgrade head

# 서버 실행
uvicorn app.main:app --reload
```

---

## 추후 확장 계획

- 동일 워커 N개 동시 실행으로 동시성 처리 확대
- asyncio.Queue → Redis Queue로 교체 (영속성 확보)
- Docker Compose로 DB + 앱 + Redis 구성
- GitHub Actions CI/CD 파이프라인 구축
- Streamlit 대시보드로 분석 결과 시각화
