# 쇼핑 트렌드 + RAG + LLM 시세 분석 파이프라인

> **개인 학습 프로젝트.** 회사에서 사용하는 큐 기반 비동기 파이프라인 아키텍처를 직접 구현하면서 RAG / LLM / 외부 시계열 API 통합 / 운영 안정성 패턴을 익히는 게 목적입니다.
>
> **데이터 소스는 mock 매물입니다.** 실제 중고거래 플랫폼의 ToS/robots.txt 위반 가능성 때문에 매물 자체는 인위적으로 만들고, 그 위에 **시세 분석(LLM+RAG)** 과 **카테고리 트렌드(네이버 데이터랩)** 를 통합해 운영 가능한 파이프라인을 구축했습니다. 실제 매물 수집은 의도적으로 미구현.

---

## 진행 현황

| Phase | 내용 | 상태 |
|---|---|---|
| **Phase 1** | FastAPI + SQLAlchemy 비동기 + asyncio.Queue 4개 + 워커 4개 + DB 모델 + Alembic + mock 파이프라인 통과 | ✅ |
| **Phase 2** | ExternalClient (httpx 래퍼) + api_req_res_logs 자동 기록 + exponential backoff 재시도 + 타임아웃 세분화 | ✅ |
| **Phase 3-1** | 멀티 프로바이더 LLM 클라이언트 (Gemini Flash primary + Groq Llama 3.3 fallback, 자동 quota 전환) | ✅ |
| **Phase 3-2** | price_analyzer에 LLMClient 통합 + 한국어 프롬프트 설계 + Gemini responseSchema 강제 | ✅ |
| **Phase 3-3** | 응답 검증 강화 (Pydantic AnalysisResult + 도메인 예외 PriceAnalyzerError + 가격 sanity) | ✅ |
| **Phase 3-4a** | RAG 임베딩 인프라 (sentence-transformers 다국어 모델 + 한국어 노이즈 제거 preprocess) | ✅ |
| **Phase 3-4b** | 코사인 유사도 + 유사 매물 검색 (numpy vectorization + argpartition top-K) | ✅ |
| **Phase 3-4c** | prompt_builder + S-Prompt 통합 (검색 결과를 markdown 표로 LLM 프롬프트에 주입) | ✅ |
| **Phase 4-b-1** | items 라이프사이클 추적 (PENDING/PROCESSING/COMPLETED/FAILED/SKIPPED/TIMEOUT) + transition 룰 | ✅ |
| **Phase 4-b-2** | sweeper 워커 + TIMEOUT 감지 (PROCESSING이 5분 이상 박힌 매물 강제 마감) | ✅ |
| **Phase 4-c** | retry 정책 (TIMEOUT 자동 재투입 + retryCount/nextRetryAt/rawInput + exp backoff + retry_worker) | ✅ |
| **Phase 4-a** | Discord Webhook 실제 알림 발송 (Notifier Protocol + DiscordNotifier/LogNotifier) | ✅ |
| **Phase 5-a** | Graceful shutdown (asyncio.Event + wait_for polling + PENDING recovery hook) | ✅ |
| **Phase 5-b** | 헬스체크 강화 (`/health/live` + `/health/ready` + 워커 alive/DB ping/LLM quota 상태) | ✅ |
| **Phase 5-c** | 통계/운영 API `/api/stats` (status 분포 + failure 집계 + retry 통계 + 알림 + recent N) | ✅ |
| **Phase 6** | 네이버 데이터랩 카테고리 트렌드 통합 (DataLabClient + TrendCache + trend_collector_worker + LLM 프롬프트/embed/stats 주입) | ✅ |
| **Phase 7** | 도메인 피벗 — 키워드 검색 분석 (네이버 쇼핑 + 데이터랩 Keywords + RAG 누적 + LLM 종합 → SearchAnalysis) + `/api/search/{id}` 캐시 로드 (재호출 X) | ✅ |
| **Frontend** | Vite + React + lucide-react — 사이드바 + Search 페이지(검색창/결과 5섹션/Sparkline/캐시 배너) + Dashboard 페이지(검색 통계 / 트렌드 예측 분포 / 가격대 분포 / 외부 API 호출 / 최근 검색) | ✅ |
| **실행 스크립트** | macOS `start.command` + Windows `start.bat` — 더블클릭 한 번으로 백엔드 + 프론트 동시 실행 + 브라우저 자동 오픈 | ✅ |

---

## 아키텍처

4개의 `asyncio.Queue`로 구성된 비동기 파이프라인. 각 단계는 독립된 Worker가 처리하며, 모든 처리 과정이 `pipeline_logs` 테이블에 기록됩니다.

```
[Mock 매물 (학습용)]
       │
       ▼
┌───────────────┐   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│ COLLECT_QUEUE │──▶│ VALIDATE_QUEUE │──▶│ ANALYZE_QUEUE  │──▶│ NOTIFY_QUEUE   │
│               │   │                │   │                │   │                │
│ collect_      │   │ seller_check   │   │ RAG + LLM 분석 │   │ notify_worker  │
│ worker        │   │ + item_        │   │ + 트렌드 컨텍스트 │   │ (Discord/Log)  │
│               │   │ validator      │   │                │   │                │
└───────────────┘   └────────────────┘   └────────────────┘   └────────────────┘
       │                   │                     │                     │
       ▼                   ▼                     ▼                     ▼
   pipeline_logs       pipeline_logs       pipeline_logs       pipeline_logs
                                            api_req_res_logs    notification_logs
                                            item_embeddings     api_req_res_logs
                                            (LLM_API)           (NOTIFY_API)

[보조 워커]
sweeper_worker      → PROCESSING 5분+ 매물 TIMEOUT 마감
retry_worker        → TIMEOUT 매물 PENDING reset + 큐 재투입 (exp backoff)
trend_collector     → 1일 1회 데이터랩 호출 → category_trends + TrendCache
llm_ping_worker     → LLM 헬스체크
```

### 분석 파이프라인 (analyze_worker 내부)

```
analyze_worker
    │
    ▼
preprocess.clean_title (한국어 노이즈 제거)
    │
    ▼
EmbeddingClient.encode (multilingual-MiniLM, 384d, 1회)
    │
    ├──────────────────┐
    ▼                  ▼
similar_search        ItemEmbedding INSERT
(코사인 + top-K)
    │
    ▼ retrieved K건
TrendCache.all() ──▶ 카테고리 트렌드 dict
    │
    ▼
prompt_builder.build_s_prompt
(유사 매물 markdown 표 + 카테고리 트렌드 줄 주입)
    │
    ▼
price_analyzer.run → LLMClient.analyze (Gemini → Groq fallback)
    │
    ▼
AnalysisResult Pydantic 검증 + 가격 sanity
    │
    ▼
items UPDATE (COMPLETED / FAILED+failReason)
```

---

## 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.11+ | 비동기 + 타입 힌트 |
| 웹 프레임워크 | FastAPI | lifespan으로 워커 + 클라이언트 관리 |
| ORM | SQLAlchemy 2.0 (async) | `Mapped[T]` + `mapped_column` |
| DB | SQLite (`dev.db`) | 학습 단계 단순화. 운영 시 MariaDB/Postgres 교체 |
| 큐 | `asyncio.Queue` | 인메모리, 백프레셔(maxsize) |
| HTTP | httpx (AsyncClient) | `external_client.py`로 래핑 + 자동 로깅/재시도/타임아웃 |
| LLM Primary | **Gemini 2.5 Flash** | 무료, JSON Schema 강제 |
| LLM Fallback | **Groq Llama 3.3 70B** | 무료, OpenAI 호환 |
| 임베딩 | **`paraphrase-multilingual-MiniLM-L12-v2`** | 384차원 다국어, 로컬 호스팅 |
| 벡터 연산 | numpy | 코사인 유사도 vectorization, argpartition |
| 트렌드 | **네이버 데이터랩 쇼핑인사이트** | 카테고리별 검색량 시계열 |
| 알림 | Discord Webhook | Notifier 추상으로 LogNotifier fallback |
| 검증 | Pydantic v2 | LLM 응답 모델 + Settings |
| 마이그레이션 | Alembic | 비동기 env.py |
| 프론트엔드 | Vite + React (vanilla CSS) | 운영 대시보드, 백엔드 API 소비 |

---

## 디렉토리 구조

```
used-deal-analyzer/
├── app/
│   ├── main.py                       # FastAPI 앱 + lifespan + 헬스체크 (/health/live, /ready)
│   ├── core/
│   │   ├── config.py                 # Pydantic Settings (.env 로드)
│   │   ├── database.py               # SQLAlchemy 비동기 엔진/세션
│   │   ├── queue_manager.py          # asyncio.Queue 4개 관리
│   │   └── lifecycle.py              # shutdown_event + recover_pending_items
│   ├── models.py                     # 9개 테이블 모델 (Phase 6: CategoryTrend 추가)
│   ├── services/
│   │   ├── external_client.py        # httpx 래퍼 (로깅/재시도/타임아웃)
│   │   ├── llm_client.py             # LLM 멀티 프로바이더 + fallback + health
│   │   ├── price_analyzer.py         # AnalysisResult + sanity + run()
│   │   ├── prompt_builder.py         # S-Prompt 빌더 (유사매물 표 + 트렌드 줄)
│   │   ├── preprocess.py             # 매물 텍스트 노이즈 제거
│   │   ├── embedding.py              # EmbeddingClient (sentence-transformers)
│   │   ├── similarity.py             # 코사인 유사도 (단건/일괄)
│   │   ├── similar_search.py         # 유사 매물 top-K 검색
│   │   ├── item_state.py             # ItemStatus enum + transition 매트릭스
│   │   ├── notifier.py               # Notifier Protocol + Discord/LogNotifier
│   │   ├── datalab_client.py         # 네이버 데이터랩 API 래퍼 + 매핑/라벨화
│   │   ├── trend_cache.py            # 카테고리 트렌드 메모리 캐시
│   │   ├── log_helpers.py            # pipeline_logs 헬퍼
│   │   ├── item_collector.py         # 매물 수집 (mock)
│   │   ├── seller_check.py           # 판매자 검증
│   │   ├── item_validator.py         # 매물 유효성
│   │   └── result_save.py            # 결과 저장
│   ├── workers/
│   │   ├── collect_worker.py         # COLLECT_QUEUE 소비 + items PENDING INSERT
│   │   ├── validate_worker.py        # VALIDATE_QUEUE 소비 + 정책 검증
│   │   ├── analyze_worker.py         # RAG 검색 + 트렌드 컨텍스트 + LLM 분석
│   │   ├── notify_worker.py          # NOTIFY_QUEUE 소비 + Notifier 호출
│   │   ├── llm_ping_worker.py        # LLM 헬스체크
│   │   ├── sweeper_worker.py         # PROCESSING 매물 TIMEOUT 마감
│   │   ├── retry_worker.py           # TIMEOUT 자동 재투입 + exp backoff
│   │   └── trend_collector_worker.py # 1일 1회 데이터랩 트렌드 수집
│   └── api/
│       └── routes.py                 # /api/test-pipeline, /api/stats, /api/_debug/*
├── alembic/                          # DB 마이그레이션
├── tests/                            # 테스트
├── Frontend/                         # Vite + React 프론트엔드
│   ├── src/
│   │   ├── App.jsx                   # 사이드바 + Dashboard (검색 통계)
│   │   ├── SearchPage.jsx            # 검색창 + 결과 카드 5섹션 + Sparkline
│   │   ├── App.css                   # shadcn/ui 톤 디자인 시스템
│   │   ├── index.css                 # 디자인 토큰 + 글로벌
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── start.command                     # macOS 원클릭 실행 (더블클릭 가능)
├── start.bat                         # Windows 원클릭 실행 (더블클릭 가능)
├── requirements.txt
└── .env                              # 환경변수 (git 미포함)
```

> 학습 노트(`docs/`)는 로컬 전용 (.gitignore).

---

## DB 설계 (9개 테이블)

| 테이블 | 역할 |
|--------|------|
| `items` | 매물 마스터 — 라이프사이클(PENDING→PROCESSING→COMPLETED/FAILED/SKIPPED/TIMEOUT) + retry(retryCount/nextRetryAt/rawInput) |
| `item_images` | 매물 이미지 |
| `item_embeddings` | 매물 384d 벡터 (RAG 검색 자원) |
| `category_trends` | **카테고리별 검색 트렌드 시계열 (네이버 데이터랩 캐시)** |
| `price_history` | 카테고리별 시세 이력 (Phase 5+ 확장 예정) |
| `notification_logs` | 알림 전송 상태 (Discord/Log) |
| `pipeline_logs` | 파이프라인 단계별 처리 로그 |
| `api_req_res_logs` | 외부 API 호출 요청/응답 (LLM_API/NOTIFY_API/DATALAB_API) |
| `watch_keywords` | 사용자 감시 키워드 + 최대 가격 |

---

## 운영 안정성 (Phase 4-b/c + 5-a/b 핵심)

### 상태 머신 (items.status)
```
PENDING ──▶ PROCESSING ──▶ COMPLETED
                       ├──▶ FAILED
                       ├──▶ SKIPPED   (정책 스킵)
                       └──▶ TIMEOUT
TIMEOUT ──▶ PENDING (retry로 한정 허용, retry_worker만)
```
모든 전이는 `Item.transition_to()` 헬퍼로 검증 — 룰 위반 시 `InvalidStateTransition`.

### sweeper + retry
- **sweeper**: 60초마다 PROCESSING 5분+ 매물 → TIMEOUT 마감
- **retry**: TIMEOUT 매물 → PENDING reset + analyze_queue 재투입 (60s/300s/1800s exp backoff, 최대 3회)
- 3회 초과 → `failReason="MAX_RETRIES_EXCEEDED"` 영구 마감

### Graceful shutdown
- SIGTERM → `shutdown_event.set()` → 큐 워커들이 다음 polling(1초)에서 자연 종료
- 진행 중 매물은 끝까지 처리 (timeout 30초 내)
- startup 시 `recover_pending_items` 훅이 PENDING 매물 → validate_queue 재투입

### 헬스체크
- `/health/live`: 항상 200 (k8s liveness probe)
- `/health/ready`: 워커 alive + DB ping + LLM quota 상태 종합. 하나라도 비정상이면 503 (k8s readiness probe)

### 운영 통계
- `/api/stats`: status 분포 / failures(byStage/byReason) / retries / notifications / **trends** / recent N

---

## 카테고리 트렌드 (Phase 6 핵심)

### 작동 흐름
1. **startup 시 1회 즉시 fetch** — 데이터랩 호출 → 7개 카테고리 14일 시계열
2. **trend_collector_worker** — 24시간마다 갱신
3. **변화율 계산** — 최근 7일 평균 vs 이전 7일 평균 → ±%
4. **라벨화** — `+15% 이상 → 급상승`, `-15% 이하 → 하락`, 그 외 → `안정`
5. **DB 저장** — `category_trends` 테이블에 시계열 누적
6. **메모리 캐시** — `TrendCache`에 최신 상태 유지 → analyze/notifier/stats가 공유

### 통합 지점
- **LLM 프롬프트**: S-Prompt에 `[참고: 카테고리 검색 트렌드] - ELECTRONICS: 급상승 (+30.0%)` 한 줄 주입
- **Discord embed**: 알림에 "카테고리 트렌드: 급상승 +30.0%" 필드 추가
- **/api/stats**: `trends` 섹션으로 노출

### Fallback
- `NAVER_DATALAB_CLIENT_ID/SECRET` 비어있으면 트렌드 워커 미시작, 분석 프롬프트에 트렌드 줄 미포함, embed에 필드 미포함

---

## RAG 시스템 (Phase 3-4 핵심)

1. `preprocess.clean_title` — 한국어 노이즈 키워드 제거 (택배비포함/직거래만/네고/괄호 메타 등)
2. `EmbeddingClient.encode` — 384d 정규화 벡터 (`normalize_embeddings=True`)
3. `similar_search.search_similar` — `item_embeddings`에서 top-K
   - numpy 행렬곱 코사인 유사도
   - `argpartition`으로 O(N) top-K 추출 + 정렬
   - 임계 컷(`min_score=0.5`)
4. `prompt_builder.build_s_prompt` — 검색 결과 markdown 표 + 트렌드 줄 → LLM 프롬프트
5. `price_analyzer.run` — Gemini → AnalysisResult 검증 → 가격 sanity
6. 임베딩 저장 (1회 생성한 query_vec 재사용) → 다음 분석의 검색 자원

---

## LLM 클라이언트 (Phase 3-1 핵심)

- **Primary (Gemini 2.5 Flash)**: JSON Schema 강제로 응답 형태 보장
- **Fallback (Groq Llama 3.3 70B)**: Primary quota 소진 시 자동 전환
- **자동 복구**: 차단 플래그를 날짜로 기록 → 자정 지나면 자동 해제
- Quota 소진 감지: HTTP 429 / `RESOURCE_EXHAUSTED` (Gemini) / `rate_limit_exceeded` (Groq)

---

## 응답 검증 (Phase 3-3 핵심)

LLM 응답을 그대로 믿지 않고 도메인 검증:

- **타입/필드/enum**: Pydantic `AnalysisResult`
  - category ∈ 8개 enum
  - estimatedPrice > 0
  - 0 ≤ confidence ≤ 100
  - reason 비어있지 않음
- **가격 sanity**: 호가 대비 추정가가 1/10 ~ 10배 범위
- **실패 분류** (`failReason`): `INVALID_JSON` / `INVALID_CATEGORY` / `INVALID_CONFIDENCE` / `INVALID_PRICE`

검증 실패 매물도 `items` 테이블에 보존 → `SELECT failReason, COUNT(*) FROM items WHERE status='FAILED' GROUP BY failReason`로 LLM 품질 추적.

---

## 실행 방법

### 원클릭 (추천)

```bash
# macOS — Finder에서 더블클릭 또는 터미널에서:
./start.command

# Windows — 탐색기에서 더블클릭 또는 cmd에서:
start.bat
```

→ 백엔드(8000) + 프론트엔드(5173) 새 터미널 창에 자동 실행 + 브라우저 자동 오픈.
첫 실행 시 `npm install`도 자동.

### 수동 (필요할 때만)

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정 (.env 파일 생성)
cat > .env << 'EOF'
DATABASE_URL=sqlite+aiosqlite:///./dev.db
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
DISCORD_WEBHOOK_URL=                       # 비우면 LogNotifier (stdout)
NAVER_DATALAB_CLIENT_ID=                   # 비우면 트렌드 기능 비활성
NAVER_DATALAB_CLIENT_SECRET=
NAVER_SHOP_CLIENT_ID=                      # 비우면 데이터랩 키로 fallback
NAVER_SHOP_CLIENT_SECRET=
EOF

# 3. DB 마이그레이션
alembic upgrade head

# 4. 백엔드 실행 (첫 시작 시 임베딩 모델 ~5초 + DataLab 초기 fetch)
uvicorn app.main:app --reload   # → http://localhost:8000

# 5. 프론트엔드 실행 — 별도 터미널
cd web
npm install                      # 첫 실행만
npm run dev                      # → http://localhost:5173

# 6. (디버그) mock 매물 1건 파이프라인 통과
curl -X POST http://localhost:8000/api/_debug/test-pipeline

# 디버그 옵션:
#   ?seller=F        → SKIPPED (LOW_RELIABILITY)
#   ?sold=true       → SKIPPED (ALREADY_SOLD)
#   ?over_price=true → SKIPPED (PRICE_OVER_LIMIT)

# 7. 헬스체크 / 통계
curl http://localhost:8000/health/ready | python -m json.tool
curl http://localhost:8000/api/stats | python -m json.tool

# 또는 브라우저에서 http://localhost:5173 — 대시보드에서 위 동작 모두 확인
```

### 프론트엔드 대시보드

http://localhost:5173 에서 확인 가능:
- 헤더 좌측 점: ready(초록) / degraded(노랑) / unreachable(빨강)
- `Run normal item` / `F seller` / `Sold` / `Over price` 버튼 — 매물 투입 단축
- **Status** 6 타일 — PENDING/PROCESSING/COMPLETED/FAILED/SKIPPED/TIMEOUT 분포
- **Trends** 7 카드 — 데이터랩 카테고리 트렌드 (라벨 + 변화율%)
- **Failures** 칩 — 실패/스킵 사유별 카운트
- **Recent items** 테이블 — itemId / status / 가격 / 할인율(색상 강조) / retry / 분석 시각
- 자동 3초 갱신

스타일 톤은 Vercel/Linear 미니멀 (흰 배경 + hairline border + monospace 숫자).

### 결과 확인 (SQL)

```sql
-- 분석 결과
SELECT itemId, title, category, status, retryCount, failReason
FROM items ORDER BY updatedAt DESC LIMIT 10;

-- 트렌드 시계열
SELECT category, label, changePercent, periodStart, periodEnd, fetchedAt
FROM category_trends ORDER BY id DESC LIMIT 10;

-- 외부 API 호출 (LLM/Notify/DataLab 통합)
SELECT apiType, event, httpStatus, durationMs
FROM api_req_res_logs ORDER BY id DESC LIMIT 20;
```

### 키 발급
- **Gemini**: https://aistudio.google.com → "Get API Key"
- **Groq**: https://console.groq.com → "API Keys"
- **Discord Webhook**: 채널 설정 → 연동 → 웹후크 → URL 복사
- **네이버 데이터랩**: https://developers.naver.com → 애플리케이션 등록 → 데이터랩(쇼핑인사이트) 권한 추가

### Mac 24/7 운영 시
```bash
caffeinate -i uvicorn app.main:app
```

---

## 회사 시스템 매핑 (학습 목적)

| 회사 파이프라인 | 본 프로젝트 |
|---|---|
| `cs_receiver` (문의 수신) | `collect_worker` (mock 매물 수집) |
| `supplier_check` (셀러 검증) | `validate_worker` (seller_check) |
| `product_check` (상품 검증) | `validate_worker` (item_validator) |
| `budget_calc` (예산 배정) | `analyze_worker` (RAG + 트렌드 + LLM 시세 분석) |
| `result_save` (결과 저장) | `analyze_worker` (items UPDATE) |
| `result_send` (결과 전송) | `notify_worker` (Discord/Log) |
| `cleanup_worker` (재시도/타임아웃 정리) | `sweeper_worker` + `retry_worker` |
| `health_check` | `/health/live` + `/health/ready` |

---

## 추후 확장

- 동일 워커 N개 동시 실행 (concurrency 확대)
- `asyncio.Queue` → Redis Queue (영속성) — 큐 잔여물 셧다운 시 유실 본질적 해결
- Docker Compose로 DB + 앱 통합
- 임베딩 한국어 특화 모델 비교 (ko-sroberta, BGE-M3)
- Re-ranking (cross-encoder) + Hybrid search (벡터 + BM25)
- Streamlit / 간단 React 대시보드 (`/api/stats` 시각화)
- 트렌드 키워드 단위 (현재 카테고리 단위 → 데이터랩 keywords 엔드포인트 추가)
- 단위/통합 테스트 추가 (현재 임시 스크립트 검증만)

> ⚠️ 본 프로젝트는 학습용입니다. 실제 중고거래/쇼핑 플랫폼의 ToS와 robots.txt를 위반하는 무단 크롤링은 포함하지 않습니다. 매물 데이터는 항상 mock입니다.
