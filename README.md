# 중고거래 매물 자동 분석 시스템

> **개인 학습 프로젝트.** 회사에서 사용하는 큐 기반 비동기 파이프라인 아키텍처를 다른 도메인(중고거래)으로 1:1 재구현하면서 패턴을 익히는 게 목적입니다.

중고거래 매물을 자동 수집 → 검증 → LLM 시세 분석 → 좋은 매물 알림으로 흐르는 비동기 파이프라인입니다. 데이터 소스는 mock으로 시작해 단계적으로 실제 API/크롤링으로 교체할 예정입니다.

---

## 진행 현황

| Phase | 내용 | 상태 |
|---|---|---|
| **Phase 1** | FastAPI + SQLAlchemy 비동기 + asyncio.Queue 4개 + 워커 4개 + 8개 DB 모델 + Alembic + mock 파이프라인 통과 | ✅ 완료 |
| **Phase 2** | ExternalClient (httpx 래퍼) + api_req_res_logs 자동 기록 + exponential backoff 재시도 + 타임아웃 세분화 + mock 서버 | ✅ 완료 |
| **Phase 3-1** | 멀티 프로바이더 LLM 클라이언트 (Gemini Flash primary + Groq Llama 3.3 fallback, 자동 quota 전환) | ✅ 완료 |
| Phase 3-2 | price_analyzer에 LLMClient 통합 + 프롬프트 설계 + JSON Schema 응답 검증 | ⬜ |
| Phase 3-3 | confidence 기반 분기 처리 | ⬜ |
| Phase 3-4 | RAG (임베딩 + 벡터 유사도 검색 + S-Prompt) | ⬜ |
| Phase 4 | Telegram/Discord 실제 알림 + 상태 머신 (PENDING → COMPLETED/FAILED) | ⬜ |
| Phase 5 | 운영 안정성 (Graceful shutdown, 헬스체크, 통계 API) | ⬜ |

학습 노트는 [`docs/STUDY.md`](docs/STUDY.md) 참고.

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
│ collect_      │   │ seller_check   │   │ price_analyzer │   │ notification_  │
│ worker        │   │ + item_        │   │ (LLM 호출)     │   │ send           │
│               │   │ validator      │   │                │   │                │
└───────────────┘   └────────────────┘   └────────────────┘   └────────────────┘
       │                   │                     │                     │
       ▼                   ▼                     ▼                     ▼
   pipeline_logs       pipeline_logs       pipeline_logs       pipeline_logs
                                            api_req_res_logs    notification_logs
                                            (LLM_API)
```

### LLM 호출 (Phase 3-1)

```
analyze_worker
    │
    ▼
LLMClient.analyze(prompt, schema)
    │
    ├─ 오늘 primary quota 차단 플래그 → 바로 fallback
    │
    └─ primary 시도
         │
         ├─ 성공 → dict 반환
         ├─ QuotaExceededError → 차단 기록 + fallback
         └─ 다른 에러 → raise
                │
                ▼
   ┌──────────────────┐    ┌──────────────────┐
   │ GeminiProvider   │    │ GroqProvider     │
   │ (Google AI       │    │ (OpenAI 호환)    │
   │  Studio)         │    │                  │
   └──────────────────┘    └──────────────────┘
              │                    │
              └────────┬───────────┘
                       ▼
              ExternalClient (httpx + 자동 로깅 + 재시도 + 타임아웃)
                       │
                       ▼
              api_req_res_logs (apiType="LLM_API")
```

---

## 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.11+ | 비동기 + 타입 힌트 |
| 웹 프레임워크 | FastAPI | lifespan으로 백그라운드 워커 관리 |
| ORM | SQLAlchemy 2.0 (async) | `Mapped[T]` + `mapped_column` |
| DB | SQLite (`dev.db`) | 학습 단계 단순화. 운영 시 MariaDB 교체 가능 |
| 큐 | `asyncio.Queue` | 인메모리, 백프레셔(maxsize) |
| HTTP 클라이언트 | httpx (AsyncClient) | `external_client.py`로 래핑 |
| LLM (Primary) | **Gemini 2.5 Flash** (Google AI Studio) | 무료, JSON Schema 강제 지원 |
| LLM (Fallback) | **Groq Llama 3.3 70B** | 무료, OpenAI 호환 API |
| 임베딩 | sentence-transformers `all-MiniLM-L6-v2` *(Phase 3-4)* | 384차원, 로컬 |
| 마이그레이션 | Alembic | autogenerate + 비동기 env.py |
| 설정 | Pydantic Settings | `.env` 자동 로드 |

---

## 디렉토리 구조

```
used-deal-analyzer/
├── app/
│   ├── main.py                    # FastAPI 앱 + lifespan
│   ├── core/
│   │   ├── config.py              # Pydantic Settings (.env 로드)
│   │   ├── database.py            # SQLAlchemy 비동기 엔진/세션
│   │   └── queue_manager.py       # asyncio.Queue 4개 관리
│   ├── models.py                  # 8개 테이블 모델
│   ├── services/
│   │   ├── external_client.py     # httpx 래퍼 (로깅/재시도/타임아웃)
│   │   ├── llm_client.py          # ✨ LLM 멀티 프로바이더 + fallback (Phase 3-1)
│   │   ├── log_helpers.py         # pipeline_logs 헬퍼
│   │   ├── item_collector.py      # (예정)
│   │   ├── seller_check.py        # (예정)
│   │   ├── item_validator.py      # (예정)
│   │   ├── price_analyzer.py      # (예정 — Phase 3-2)
│   │   ├── result_save.py         # (예정)
│   │   ├── notification_send.py   # (예정 — Phase 4)
│   │   └── report_generator.py    # (예정)
│   ├── workers/
│   │   ├── collect_worker.py      # COLLECT_QUEUE 소비
│   │   ├── validate_worker.py     # VALIDATE_QUEUE 소비
│   │   ├── analyze_worker.py      # ANALYZE_QUEUE 소비 (현재 mock 분석)
│   │   └── notify_worker.py       # NOTIFY_QUEUE 소비 (현재 mock 알림)
│   └── api/
│       ├── routes.py              # /api/test-pipeline (mock 투입)
│       └── schemas.py             # (Phase 3-2 채울 예정)
├── alembic/                       # DB 마이그레이션
├── tests/                         # 테스트
├── docs/
│   ├── ARCHITECTURE.md            # 전체 설계 (큐/DB/서비스 매핑)
│   ├── DEV_RULES.md               # 개발 룰 (5단계 워크플로우)
│   ├── STUDY.md                   # 학습 노트 (날짜별)
│   ├── research.md                # 일감별 리서치 누적
│   └── code_design.md             # 일감별 코드 설계 누적
├── requirements.txt
└── .env                           # 환경변수 (git 미포함)
```

---

## DB 설계 (8개 테이블)

| 테이블 | 역할 |
|--------|------|
| `items` | 매물 마스터 (수집~분석~알림 전체 상태) |
| `item_images` | 매물 이미지 |
| `price_history` | 카테고리별 시세 이력 (스냅샷) |
| `notification_logs` | 알림 전송 상태 추적 |
| `pipeline_logs` | 파이프라인 단계별 처리 로그 |
| `api_req_res_logs` | 외부 API 호출 요청/응답 로그 (UUID 추적, LLM 호출 포함) |
| `watch_keywords` | 사용자 감시 키워드 + 최대 가격 |
| `item_embeddings` | 매물 벡터 (Phase 3-4 RAG용) |

---

## LLM 클라이언트 (Phase 3-1 핵심)

### 동작 방식
- **Primary (Gemini 2.5 Flash)**: 정확도 우선, JSON Schema 강제로 응답 형태 보장
- **Fallback (Groq Llama 3.3 70B)**: Primary가 일일 quota 소진 시 자동 전환
- **자동 복구**: 차단 플래그를 날짜로 기록 → 자정 지나면 자동 해제 (별도 cleanup 코드 X)

### 사용 예시
```python
from app.services.llm_client import GeminiProvider, GroqProvider, LLMClient
from app.core.config import settings

primary = GeminiProvider(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_MODEL)
fallback = GroqProvider(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
client = LLMClient(primary=primary, fallback=fallback)

await client.start()
result = await client.analyze(
    prompt="매물 분석 prompt...",
    schema={"type": "object", "properties": {...}},
)
# result = {"category": "ELECTRONICS", "estimatedPrice": 850000, ...}
await client.close()
```

### Quota 소진 감지 신호
- HTTP 429 (Too Many Requests)
- 응답 본문에 `RESOURCE_EXHAUSTED` (Gemini) / `rate_limit_exceeded` (Groq) / `quota` 포함

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

# 4. 서버 실행
uvicorn app.main:app --reload

# 5. mock 매물 1건 파이프라인 통과 테스트
curl -X POST http://localhost:8000/api/test-pipeline

# 6. 큐 상태 확인
curl http://localhost:8000/health
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

## 개발 룰 (5단계 워크플로우)

이 프로젝트는 [`docs/DEV_RULES.md`](docs/DEV_RULES.md)의 5단계 워크플로우를 따릅니다:

1. **리서치** → `docs/research.md`에 옵션 비교 누적
2. **코드 설계** → `docs/code_design.md`에 파일/함수 구조 정리
3. **코드 구현** → 한 블록씩 설명 후 사용자 확인 → 구현 (반복)
4. **피드백** → 셀프 점검 + STUDY.md에 학습 정리
5. **코드 리뷰** → 전체 코드 + 설계 문서 일관성 점검

학습은 코드 안 주석이 아닌 **STUDY.md** 기준입니다. 코드 안 주석은 "왜"가 비자명한 곳에만 한 줄.

---

## 회사 시스템 매핑 (학습 목적)

| 회사 파이프라인 | 본 프로젝트 |
|---|---|
| `cs_receiver` (문의 수신) | `item_collector` (매물 수집) |
| `supplier_check` (셀러 검증) | `seller_check` (판매자 검증) |
| `product_check` (상품 검증) | `item_validator` (매물 유효성) |
| `budget_calc` (예산 배정) | `price_analyzer` (LLM 시세 분석) |
| `result_save` (결과 저장) | `result_save` |
| `result_send` (결과 전송) | `notification_send` |
| `reply_register` (답변 등록) | `report_generator` |

---

## 추후 확장 (Phase 5 이후)

- 동일 워커 N개 동시 실행 (concurrency 확대)
- `asyncio.Queue` → Redis Queue (영속성)
- Docker Compose로 DB + 앱 통합
- 실제 데이터 소스 연동 (네이버 쇼핑 검색 API, 번개장터 크롤링 등)
- Streamlit 대시보드 (분석 결과 시각화)

> ⚠️ 본 프로젝트는 학습용으로, 실제 중고거래 플랫폼의 ToS와 robots.txt를 위반하는 무단 크롤링은 포함하지 않습니다.
