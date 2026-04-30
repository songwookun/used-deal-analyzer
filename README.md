# 중고거래 매물 자동 분석 시스템

> **개인 학습 프로젝트.** 회사에서 사용하는 큐 기반 비동기 파이프라인 아키텍처를 다른 도메인(중고거래)으로 1:1 재구현하면서 패턴을 익히는 게 목적입니다.

중고거래 매물을 자동 수집 → 검증 → **RAG 기반 LLM 시세 분석** → 좋은 매물 알림으로 흐르는 비동기 파이프라인입니다. 데이터 소스는 mock으로 시작해 단계적으로 실제 API/크롤링으로 교체할 예정입니다.

---

## 진행 현황

| Phase | 내용 | 상태 |
|---|---|---|
| **Phase 1** | FastAPI + SQLAlchemy 비동기 + asyncio.Queue 4개 + 워커 4개 + 8개 DB 모델 + Alembic + mock 파이프라인 통과 | ✅ |
| **Phase 2** | ExternalClient (httpx 래퍼) + api_req_res_logs 자동 기록 + exponential backoff 재시도 + 타임아웃 세분화 + mock 서버 | ✅ |
| **Phase 3-1** | 멀티 프로바이더 LLM 클라이언트 (Gemini Flash primary + Groq Llama 3.3 fallback, 자동 quota 전환) | ✅ |
| **Phase 3-2** | price_analyzer에 LLMClient 통합 + 한국어 프롬프트 설계 + Gemini responseSchema 강제 | ✅ |
| **Phase 3-3** | 응답 검증 강화 (Pydantic AnalysisResult + 도메인 예외 PriceAnalyzerError + 가격 sanity + items.FAILED 추적) | ✅ |
| **Phase 3-4a** | RAG 임베딩 인프라 (sentence-transformers 다국어 모델 + 한국 중고거래 노이즈 제거 preprocess) | ✅ |
| **Phase 3-4b** | 코사인 유사도 + 유사 매물 검색 (numpy vectorization + argpartition top-K + 임계 컷) | ✅ |
| **Phase 3-4c** | prompt_builder + S-Prompt 통합 (검색 결과를 markdown 표로 LLM 프롬프트에 주입) | ✅ |
| **Phase 4-b-1** | items 라이프사이클 추적 (collect→PENDING→PROCESSING→COMPLETED/FAILED/SKIPPED) + `Item.transition_to` 전이 룰 | ✅ |
| Phase 4-b-2 | sweeper 워커 + TIMEOUT 감지 (PROCESSING이 N분 이상 박힌 매물 강제 정리) | ⬜ |
| Phase 4-c | retry 정책 (FAILED/TIMEOUT 매물을 PENDING으로 reset 후 재투입, retryCount) | ⬜ |
| Phase 4-a | Telegram/Discord 실제 알림 발송 (notification_send 구현) | ⬜ |
| Phase 5 | 운영 안정성 (Graceful shutdown, 헬스체크, 통계 API, 일간 리포트) | ⬜ |

---

## 아키텍처

4개의 `asyncio.Queue`로 구성된 비동기 파이프라인. 각 단계는 독립된 Worker가 처리하며, 모든 처리 과정이 `pipeline_logs` 테이블에 기록됩니다.

```
[크롤러/API/Mock]
       │
       ▼
┌───────────────┐   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│ COLLECT_QUEUE │──▶│ VALIDATE_QUEUE │──▶│ ANALYZE_QUEUE  │──▶│ NOTIFY_QUEUE   │
│               │   │                │   │                │   │                │
│ collect_      │   │ seller_check   │   │ RAG + LLM 분석 │   │ notification_  │
│ worker        │   │ + item_        │   │ (Phase 3-4)    │   │ send (예정)    │
│               │   │ validator      │   │                │   │                │
└───────────────┘   └────────────────┘   └────────────────┘   └────────────────┘
       │                   │                     │                     │
       ▼                   ▼                     ▼                     ▼
   pipeline_logs       pipeline_logs       pipeline_logs       pipeline_logs
                                            api_req_res_logs    notification_logs
                                            item_embeddings
                                            (LLM_API)
```

### Phase 3-4 RAG 흐름 (analyze_worker 내부)

```
analyze_worker
    │
    ▼
preprocess.clean_title (한국 중고거래 노이즈 제거)
    │
    ▼
EmbeddingClient.encode (sentence-transformers, 384d, 1회 생성)
    │
    ├──────────────────────────────┐
    ▼                              ▼
similar_search                  ItemEmbedding INSERT
(item_embeddings 비교 +         (벡터 재사용)
 코사인 유사도 + top-K)
    │
    ▼ retrieved K건
prompt_builder.build_s_prompt
(markdown 표로 검색 결과 주입,
 cold-start 시 우아한 degradation)
    │
    ▼
price_analyzer.run
    │
    ▼
LLMClient.analyze (Gemini → Groq fallback)
    │
    ▼
AnalysisResult Pydantic 검증 + 가격 sanity (Phase 3-3)
    │
    ▼ 검증 통과 / 실패
items INSERT (COMPLETED / FAILED+failReason)
```

---

## 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.11+ | 비동기 + 타입 힌트 |
| 웹 프레임워크 | FastAPI | lifespan으로 백그라운드 워커 + LLM/임베딩 클라이언트 관리 |
| ORM | SQLAlchemy 2.0 (async) | `Mapped[T]` + `mapped_column` |
| DB | SQLite (`dev.db`) | 학습 단계 단순화. 운영 시 MariaDB/Postgres 교체 가능 |
| 큐 | `asyncio.Queue` | 인메모리, 백프레셔(maxsize) |
| HTTP 클라이언트 | httpx (AsyncClient) | `external_client.py`로 래핑 |
| LLM (Primary) | **Gemini 2.5 Flash** (Google AI Studio) | 무료, JSON Schema 강제 지원 |
| LLM (Fallback) | **Groq Llama 3.3 70B** | 무료, OpenAI 호환 API |
| **임베딩** | **sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2`** | 384차원 다국어, 로컬 호스팅 |
| 벡터 연산 | numpy | 코사인 유사도 vectorization, argpartition top-K |
| 검증 | Pydantic v2 | LLM 응답 모델(`AnalysisResult`) + Settings |
| 마이그레이션 | Alembic | autogenerate + 비동기 env.py |

---

## 디렉토리 구조

```
used-deal-analyzer/
├── app/
│   ├── main.py                    # FastAPI 앱 + lifespan (LLM + 임베딩 클라이언트 + 워커)
│   ├── core/
│   │   ├── config.py              # Pydantic Settings (.env 로드)
│   │   ├── database.py            # SQLAlchemy 비동기 엔진/세션
│   │   └── queue_manager.py       # asyncio.Queue 4개 관리
│   ├── models.py                  # 8개 테이블 모델
│   ├── services/
│   │   ├── external_client.py     # httpx 래퍼 (로깅/재시도/타임아웃)
│   │   ├── llm_client.py          # LLM 멀티 프로바이더 + fallback        (Phase 3-1)
│   │   ├── price_analyzer.py      # AnalysisResult + sanity + run()       (Phase 3-2/3/4c)
│   │   ├── prompt_builder.py      # S-Prompt 빌더 (markdown 표)          (Phase 3-4c)
│   │   ├── preprocess.py          # 매물 텍스트 노이즈 제거               (Phase 3-4a)
│   │   ├── embedding.py           # EmbeddingClient (sentence-transformers) (Phase 3-4a)
│   │   ├── similarity.py          # 코사인 유사도 (단건 + 일괄)           (Phase 3-4b)
│   │   ├── similar_search.py      # 유사 매물 top-K 검색                  (Phase 3-4b)
│   │   ├── log_helpers.py         # pipeline_logs 헬퍼
│   │   ├── item_collector.py      # 매물 수집
│   │   ├── seller_check.py        # 판매자 검증
│   │   ├── item_validator.py      # 매물 유효성
│   │   ├── result_save.py         # 결과 저장
│   │   ├── notification_send.py   # (Phase 4 예정)
│   │   └── report_generator.py    # (Phase 5 예정)
│   ├── workers/
│   │   ├── collect_worker.py      # COLLECT_QUEUE 소비
│   │   ├── validate_worker.py     # VALIDATE_QUEUE 소비
│   │   ├── analyze_worker.py      # ANALYZE_QUEUE 소비 + RAG 검색 + LLM 분석 + 임베딩 저장
│   │   ├── notify_worker.py       # NOTIFY_QUEUE 소비 (현재 mock 알림)
│   │   └── llm_ping_worker.py     # LLM 헬스체크 워커
│   └── api/
│       ├── routes.py              # /api/test-pipeline (mock 매물 투입), /api/_debug/llm-ping
│       └── schemas.py             # (Phase 4에서 채울 예정)
├── alembic/                       # DB 마이그레이션
├── tests/                         # 테스트
├── requirements.txt
└── .env                           # 환경변수 (git 미포함)
```

> 학습 노트(`docs/`)는 로컬 전용입니다 (`.gitignore` 처리).

---

## DB 설계 (8개 테이블)

| 테이블 | 역할 |
|--------|------|
| `items` | 매물 마스터 — 수집~분석~알림 전체 상태. Phase 3-3부터 검증 실패 매물도 `status="FAILED"` + `failReason`으로 추적 |
| `item_images` | 매물 이미지 |
| `price_history` | 카테고리별 시세 이력 (스냅샷) |
| `notification_logs` | 알림 전송 상태 추적 |
| `pipeline_logs` | 파이프라인 단계별 처리 로그 (Phase 3-4부터 `rag_search` 단계 추가) |
| `api_req_res_logs` | 외부 API 호출 요청/응답 로그 (UUID 추적, LLM 호출 포함) |
| `watch_keywords` | 사용자 감시 키워드 + 최대 가격 |
| **`item_embeddings`** | **매물 384d 벡터 (JSON 직렬화) + cleanedTitle/category/price — Phase 3-4 RAG 검색 자원** |

---

## RAG 시스템 (Phase 3-4 핵심)

### 작동 흐름
1. 매물 텍스트 → `preprocess.clean_title` (한국 중고거래 노이즈 키워드 제거: 택배비포함/직거래만/쿨거래/네고/괄호 메타 등)
2. `EmbeddingClient.encode` → 384차원 정규화 벡터 (multilingual-MiniLM, `normalize_embeddings=True`)
3. `similar_search.search_similar` — `item_embeddings`에서 top-K 후보 추출
   - numpy 일괄 행렬곱(`matrix @ query`)으로 코사인 유사도 계산
   - `argpartition`으로 O(N) top-K 추출 후 정렬
   - 임계(`min_score=0.5`) 컷오프
4. `prompt_builder.build_s_prompt` — 검색 결과를 markdown 표로 LLM 프롬프트에 주입
   - DB 0건이면 자동으로 cold-start 프롬프트로 fallback
5. `price_analyzer.run` — Gemini → AnalysisResult 검증 → 가격 sanity 체크
6. 분석 성공 시 임베딩(이미 1회 생성한 query_vec 재사용)을 `item_embeddings`에 저장 → 다음 분석의 검색 자원이 됨

### 검증된 효과
- LLM이 `reason` 필드에 "기존 DB의 유사 매물과 완전히 일치" 같은 문구로 검색 결과를 명시적으로 참조
- 같은 매물 재분석 시 confidence 향상 관찰 (cold-start 90 → RAG 95)
- 의미 검색: "애플 노트북" 쿼리로도 "맥북 m3" 매칭, "키보드"로도 노트북 매물 약하게 매칭

---

## LLM 클라이언트 (Phase 3-1 핵심)

### 동작 방식
- **Primary (Gemini 2.5 Flash)**: 정확도 우선, JSON Schema 강제로 응답 형태 보장
- **Fallback (Groq Llama 3.3 70B)**: Primary가 일일 quota 소진 시 자동 전환
- **자동 복구**: 차단 플래그를 날짜로 기록 → 자정 지나면 자동 해제 (별도 cleanup 코드 X)

### 사용 예시
```python
from app.services.llm_client import GeminiProvider, GroqProvider, LLMClient
from app.services.price_analyzer import run as analyze
from app.core.config import settings

primary = GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
fallback = GroqProvider(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
client = LLMClient(primary=primary, fallback=fallback)
await client.start()

# Phase 3-4c: similar_items까지 받는 시그니처
result = await analyze(client, item_data, similar_items=retrieved)  # AnalysisResult
# result.category, result.estimatedPrice, result.confidence, result.reason
```

### Quota 소진 감지 신호
- HTTP 429 (Too Many Requests)
- 응답 본문에 `RESOURCE_EXHAUSTED` (Gemini) / `rate_limit_exceeded` (Groq) / `quota` 포함

---

## 응답 검증 (Phase 3-3 핵심)

LLM 응답을 그대로 믿지 않고 도메인 검증을 거침. 실패하면 `items.status="FAILED"` + `failReason`으로 추적 가능하게 저장.

### 검증 단계
- **타입/필드/enum**: Pydantic `AnalysisResult` 모델
  - `category` ∈ 8개 enum
  - `estimatedPrice > 0`
  - `0 ≤ confidence ≤ 100`
  - `reason` 비어있지 않음
- **가격 sanity**: 호가 대비 추정가가 1/10 ~ 10배 범위 (도메인 룰)
- **실패 분류** (`failReason` 컬럼에 저장): `INVALID_JSON` / `INVALID_CATEGORY` / `INVALID_CONFIDENCE` / `INVALID_PRICE`

검증 실패 매물도 `items` 테이블에 보존하므로 운영 시 `SELECT failReason, COUNT(*) FROM items WHERE status='FAILED' GROUP BY failReason`로 LLM 품질 추적.

---

## 실행 방법

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정 (.env 파일 생성)
cat > .env << 'EOF'
DATABASE_URL=sqlite+aiosqlite:///./dev.db
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
EOF

# 3. DB 마이그레이션
alembic upgrade head

# 4. 서버 실행 (첫 시작 시 임베딩 모델 ~5초 로딩)
uvicorn app.main:app --reload

# 5. mock 매물 1건 파이프라인 통과 (RAG 포함)
curl -X POST http://localhost:8000/api/test-pipeline

# 6. 큐 상태 확인
curl http://localhost:8000/health
```

### 결과 확인 (SQL)

```sql
-- 분석 결과
SELECT itemId, title, category, askingPrice, estimatedPrice,
       priceDiffPercent, llmConfidence, status, failReason
FROM items ORDER BY analyzedAt DESC LIMIT 5;

-- RAG 임베딩 누적
SELECT itemId, cleanedTitle, category, length(vector) AS vec_len
FROM item_embeddings ORDER BY id DESC LIMIT 5;

-- RAG 검색 단계 로그
SELECT itemId, json_extract(detail,'$.count') AS hits,
       json_extract(detail,'$.top_score') AS top_score
FROM pipeline_logs WHERE stage='rag_search' ORDER BY id DESC LIMIT 10;

-- LLM API 호출
SELECT callId, event, httpStatus, durationMs
FROM api_req_res_logs WHERE apiType='LLM_API' ORDER BY id DESC LIMIT 5;
```

### 무료 LLM 키 발급
- **Gemini**: https://aistudio.google.com → "Get API Key"
- **Groq**: https://console.groq.com → "API Keys" → "Create API Key"

### Mac 24/7 운영 시
잠자기 모드 들어가면 워커 정지 → `caffeinate`로 실행 권장:
```bash
caffeinate -i uvicorn app.main:app
```

---

## 회사 시스템 매핑 (학습 목적)

| 회사 파이프라인 | 본 프로젝트 |
|---|---|
| `cs_receiver` (문의 수신) | `item_collector` (매물 수집) |
| `supplier_check` (셀러 검증) | `seller_check` (판매자 검증) |
| `product_check` (상품 검증) | `item_validator` (매물 유효성) |
| `budget_calc` (예산 배정) | `price_analyzer` (RAG + LLM 시세 분석) |
| `result_save` (결과 저장) | `result_save` |
| `result_send` (결과 전송) | `notification_send` (Phase 4 예정) |
| `reply_register` (답변 등록) | `report_generator` (Phase 5 예정) |

---

## 추후 확장 (Phase 5 이후)

- 동일 워커 N개 동시 실행 (concurrency 확대)
- `asyncio.Queue` → Redis Queue (영속성)
- Docker Compose로 DB + 앱 통합
- 실제 데이터 소스 연동 (네이버 쇼핑 검색 API 등)
- 임베딩 한국어 특화 모델 비교 (ko-sroberta-multitask, BGE-M3)
- Re-ranking (cross-encoder) + Hybrid search (벡터 + BM25)
- Streamlit 대시보드 (분석 결과 시각화)

> ⚠️ 본 프로젝트는 학습용으로, 실제 중고거래 플랫폼의 ToS와 robots.txt를 위반하는 무단 크롤링은 포함하지 않습니다.
