# AI 중고거래 매물 자동 분석 시스템

> 회사 아키텍처(큐 4개 + 비동기 파이프라인 + LLM)를 동일하게 적용하되,
> 완전히 다른 도메인으로 실무 코딩 능력을 키우기 위한 개인 프로젝트

---

## 1. 프로젝트 개요

**도메인:** 중고거래 플랫폼(당근, 번개장터 등)에 올라온 매물을 자동 수집 → 분석 → 시세 비교 → 알림 전송하는 시스템

**왜 이 도메인인가:**
- 회사 프로젝트와 구조가 1:1로 대응됨 (수집 → 검증 → 계산 → 저장 → 전송)
- 외부 API 연동, LLM 판별, 큐 기반 비동기 처리를 모두 연습 가능
- 실제로 쓸 수 있는 결과물이 나옴 (관심 매물 알림봇)
- 포트폴리오로도 활용 가능

---

## 2. 아키텍처 매핑 (회사 구조 → 개인 프로젝트)

```
[회사 파이프라인]                    [개인 프로젝트 파이프라인]
cs_receiver (문의 수신)        →    item_collector (매물 수집)
supplier_check (셀러 검증)     →    seller_check (판매자 신뢰도 검증)
product_check (상품 검증)      →    item_validator (매물 유효성 검증)
budget_calc (예산 배정)        →    price_analyzer (시세 분석 + LLM)
result_save (결과 저장)        →    result_save (분석 결과 저장)
result_send (결과 전송)        →    notification_send (알림 전송)
reply_register (답변 등록)     →    report_generator (리포트 생성)
```

---

## 3. 큐 설계 (4개)

```
Queue-1: COLLECT_QUEUE     ← item_collector가 매물을 수집해서 넣음
Queue-2: VALIDATE_QUEUE    ← seller_check + item_validator 결과
Queue-3: ANALYZE_QUEUE     ← price_analyzer(LLM) 분석 대기
Queue-4: NOTIFY_QUEUE      ← 알림/리포트 전송 대기
```

### 흐름도

```
[크롤러/API]
     │
     ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ COLLECT_QUEUE│───▶│VALIDATE_QUEUE│───▶│ANALYZE_QUEUE │───▶│ NOTIFY_QUEUE │
│             │    │             │    │             │    │             │
│ item_       │    │ seller_check│    │ price_      │    │ notification│
│ collector   │    │ item_       │    │ analyzer    │    │ _send       │
│             │    │ validator   │    │ (LLM 호출)  │    │ report_     │
│             │    │             │    │             │    │ generator   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     │                   │                  │                   │
     ▼                   ▼                  ▼                   ▼
  [DB 저장]           [DB 저장]          [DB 저장]           [DB 저장]
  pipeline_log       pipeline_log       pipeline_log       pipeline_log
```

---

## 4. 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.11+ | 회사와 동일 |
| 웹 프레임워크 | FastAPI | 회사와 동일 |
| ORM | SQLAlchemy 2.0 | 회사와 동일 |
| DB | SQLite (개발) → MariaDB (선택) | 로컬 개발 편의상 SQLite로 시작 |
| 큐 | asyncio.Queue (인메모리) | 회사와 동일한 패턴 |
| LLM | OpenAI API 또는 Ollama(로컬) | 외부 LLM |
| 마이그레이션 | Alembic | 회사와 동일 |
| 테스트 | pytest + pytest-asyncio | |
| 알림 | Telegram Bot API 또는 Discord Webhook | 무료 |

---

## 5. 디렉토리 구조

```
used-deal-analyzer/
├── app/
│   ├── main.py                    # FastAPI 앱 + 큐 초기화 + lifespan
│   ├── core/
│   │   ├── config.py              # 설정 (Pydantic Settings)
│   │   ├── database.py            # SQLAlchemy 엔진/세션
│   │   └── queue_manager.py       # 4개 큐 관리 클래스
│   ├── models.py                  # DB 모델 전체
│   ├── services/
│   │   ├── item_collector.py      # Queue-1: 매물 수집
│   │   ├── seller_check.py        # Queue-2: 판매자 검증
│   │   ├── item_validator.py      # Queue-2: 매물 유효성
│   │   ├── price_analyzer.py      # Queue-3: 시세 분석 (LLM)
│   │   ├── result_save.py         # DB 저장
│   │   ├── notification_send.py   # Queue-4: 알림 전송
│   │   ├── report_generator.py    # Queue-4: 리포트 생성
│   │   ├── external_client.py     # 외부 API 호출 래퍼
│   │   └── log_helpers.py         # 파이프라인 로그 헬퍼
│   ├── workers/
│   │   ├── collect_worker.py      # Queue-1 소비자
│   │   ├── validate_worker.py     # Queue-2 소비자
│   │   ├── analyze_worker.py      # Queue-3 소비자
│   │   └── notify_worker.py       # Queue-4 소비자
│   └── api/
│       ├── routes.py              # REST API 엔드포인트
│       └── schemas.py             # Pydantic 스키마
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
├── alembic.ini
├── requirements.txt
└── .env
```

---

## 6. DB 설계 (7개 테이블 - 회사와 1:1 대응)

### 6-1. items (매물 마스터) ← consultations 대응

```sql
CREATE TABLE items (
    itemId          INTEGER PRIMARY KEY,        -- 매물 ID (외부 플랫폼 ID)
    platform        VARCHAR(20) NOT NULL,       -- 플랫폼 (danggeun, bunjang, etc)
    sellerId        VARCHAR(50) NOT NULL,       -- 판매자 ID
    sellerReliability VARCHAR(20),              -- 판매자 신뢰등급 (S/A/B/C/F)
    title           VARCHAR(200) NOT NULL,      -- 매물 제목
    description     TEXT,                       -- 매물 설명
    askingPrice     INTEGER NOT NULL,           -- 판매 희망가
    estimatedPrice  INTEGER,                    -- AI 추정 시세
    priceDiffPercent FLOAT,                     -- 시세 대비 차이(%)
    category        VARCHAR(30) NOT NULL,       -- 카테고리 (LLM 분류)
    llmConfidence   INTEGER,                    -- LLM 신뢰도 (0-100)
    llmReason       VARCHAR(200),               -- LLM 판별 사유
    status          VARCHAR(20) NOT NULL,       -- COMPLETED / FAILED / SKIPPED
    failStage       VARCHAR(30),                -- 실패 단계
    failReason      VARCHAR(50),                -- 실패 사유
    collectedAt     DATETIME NOT NULL,          -- 수집 시간
    analyzedAt      DATETIME,                   -- 분석 완료 시간
    notifiedAt      DATETIME,                   -- 알림 전송 시간
    createdAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 6-2. item_images (매물 이미지) ← consultation_products 대응

```sql
CREATE TABLE item_images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    itemId          INTEGER NOT NULL REFERENCES items(itemId),
    imageUrl        VARCHAR(500) NOT NULL,
    imageOrder      INTEGER NOT NULL,           -- 이미지 순서
    analysisResult  JSON,                       -- 이미지 분석 결과 (선택)
    createdAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 6-3. price_history (시세 이력) ← ad_unit_price_history 대응

```sql
CREATE TABLE price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        VARCHAR(30) NOT NULL,       -- 카테고리
    keyword         VARCHAR(100) NOT NULL,      -- 검색 키워드
    avgPrice        INTEGER NOT NULL,           -- 평균 시세
    minPrice        INTEGER,                    -- 최저가
    maxPrice        INTEGER,                    -- 최고가
    sampleCount     INTEGER NOT NULL,           -- 표본 수
    snapshotDate    DATE NOT NULL,              -- 스냅샷 날짜
    createdAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 6-4. notification_logs (알림 전송 로그) ← api_queue_logs 대응

```sql
CREATE TABLE notification_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    itemId          INTEGER NOT NULL REFERENCES items(itemId),
    notifyType      VARCHAR(20) NOT NULL,       -- TELEGRAM / DISCORD / EMAIL
    notifyStatus    VARCHAR(20) NOT NULL,       -- PENDING / COMPLETED / FAILED / TIMEOUT
    processedAt     DATETIME,
    resultDetail    JSON,
    errorDetail     JSON,
    createdAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 6-5. pipeline_logs (파이프라인 로그) ← 회사와 동일 구조

```sql
CREATE TABLE pipeline_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    itemId          INTEGER NOT NULL,
    sellerId        VARCHAR(50) NOT NULL,
    stage           VARCHAR(30) NOT NULL,       -- item_collector, seller_check, item_validator,
                                                -- price_analyzer, result_save, notification_send
    event           VARCHAR(20) NOT NULL,       -- START / SUCCESS / FAILED / SKIP
    detail          JSON,
    createdAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 6-6. api_req_res_logs (API 호출 로그) ← 회사와 동일 구조

```sql
CREATE TABLE api_req_res_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    callId          VARCHAR(36) UNIQUE NOT NULL,
    itemId          INTEGER,
    apiType         VARCHAR(20) NOT NULL,       -- PLATFORM_API, LLM_API, NOTIFY_API, PRICE_API
    event           VARCHAR(10) NOT NULL,       -- SENT / SUCCESS / FAILED
    requestBody     JSON,
    responseBody    JSON,
    httpStatus      INTEGER,
    durationMs      INTEGER,
    createdAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updatedAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 6-7. watch_keywords (감시 키워드) ← 사용자 설정

```sql
CREATE TABLE watch_keywords (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         VARCHAR(100) NOT NULL,      -- 감시할 키워드 (ex: "맥북 m3", "아이패드 프로")
    category        VARCHAR(30),
    maxPrice        INTEGER,                    -- 이 가격 이하면 알림
    isActive        BOOLEAN DEFAULT TRUE,
    createdAt       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. 서비스별 상세 로직

### 7-1. item_collector (← cs_receiver 대응)

```
역할: 중고거래 매물을 수집하여 COLLECT_QUEUE에 넣기

1. 주기적(폴링)으로 중고 플랫폼 API/크롤링 실행
2. watch_keywords 테이블에서 감시 키워드 조회
3. 키워드별로 새 매물 검색
4. 이미 수집된 매물인지 중복 체크 (← 회사의 중복 폴링 방지와 동일)
5. 새 매물이면 COLLECT_QUEUE에 push
6. pipeline_log 기록 (stage: item_collector, event: START/SUCCESS/SKIP)

SKIP 조건:
- 이미 수집된 매물 (중복)
- 감시 키워드에 해당하지 않는 카테고리
```

### 7-2. seller_check (← supplier_check 대응)

```
역할: 판매자 신뢰도 검증

1. COLLECT_QUEUE에서 매물 꺼내기
2. 판매자 프로필 조회 (가입일, 거래횟수, 매너온도 등)
3. 신뢰등급 산정: S(우수) / A(양호) / B(보통) / C(주의) / F(위험)
4. F등급이면 SKIP 처리 (사기 의심)
5. VALIDATE_QUEUE에 push
6. pipeline_log 기록

SKIP 조건:
- 판매자 신뢰등급 F (사기 의심)
- 판매자 정보 조회 불가
```

### 7-3. item_validator (← product_check 대응)

```
역할: 매물 유효성 검증

1. VALIDATE_QUEUE에서 매물 꺼내기
2. 매물 상태 확인 (이미 판매됨인지)
3. 가격 범위 검증 (watch_keywords.maxPrice 초과 시 SKIP)
4. 이미지 유무 확인
5. 통과하면 ANALYZE_QUEUE에 push
6. pipeline_log 기록

SKIP 조건:
- 이미 판매 완료된 매물
- maxPrice 초과
- 이미지 없음 (선택)
```

### 7-4. price_analyzer (← budget_calc 대응) :star: LLM 사용

```
역할: LLM으로 매물 분석 + 시세 비교

1. ANALYZE_QUEUE에서 매물 꺼내기
2. LLM API 호출 (OpenAI or Ollama)
   - 프롬프트: 매물 제목+설명 → 카테고리 분류 + 상태 판별 + 시세 추정
   - 응답: { category, condition, estimatedPrice, confidence, reason }
3. price_history에서 해당 카테고리 최근 시세 조회
4. 시세 대비 차이(%) 계산
5. result_save 호출
6. NOTIFY_QUEUE에 push (좋은 매물인 경우만)
7. pipeline_log 기록

LLM 프롬프트 예시:
"다음 중고 매물의 카테고리, 상품 상태(S/A/B/C), 예상 시세를 판별해주세요.
 제목: {title}
 설명: {description}
 판매가: {askingPrice}원
 JSON으로 응답하세요."
```

### 7-5. result_save (← 회사와 동일)

```
역할: 분석 결과를 DB에 저장

1. items 테이블에 INSERT (또는 UPDATE)
2. item_images 테이블에 이미지 정보 저장
3. 이미 처리된 매물이면 SKIP (← 회사의 중복 저장 방지와 동일)
4. pipeline_log 기록
```

### 7-6. notification_send (← result_send 대응)

```
역할: 좋은 매물 발견 시 알림 전송

1. NOTIFY_QUEUE에서 매물 꺼내기
2. 알림 조건 확인 (시세 대비 20% 이상 저렴한 경우 등)
3. Telegram Bot API 또는 Discord Webhook으로 알림 전송
4. notification_logs에 기록
5. 전송 실패 시 재시도 로직 (← 회사의 큐 폴링과 동일)
6. pipeline_log 기록
```

### 7-7. report_generator (← reply_register 대응)

```
역할: 일간 분석 리포트 생성

1. 하루 동안 수집/분석된 매물 통계
2. 카테고리별 시세 동향
3. 추천 매물 Top N
4. Telegram/Discord로 리포트 전송
```

---

## 8. 외부 API 매핑

```
[회사 API]          [개인 프로젝트 API]           [실제 사용 가능한 서비스]
EXT-01 (문의조회)  → PLATFORM_API (매물 조회)   → 공개 API 또는 mock 서버
EXT-02 (셀러조회)  → SELLER_API (판매자 조회)   → 공개 API 또는 mock 서버
EXT-03 (상품조회)  → DETAIL_API (매물 상세)     → 공개 API 또는 mock 서버
EXT-04 (광고조회)  → PRICE_API (시세 조회)      → 자체 price_history 테이블
EXT-05 (결과전송)  → LLM_API (LLM 분석)        → OpenAI API / Ollama
EXT-06 (큐조회)    → NOTIFY_API (알림 전송)     → Telegram Bot API
EXT-07 (답변등록)  → REPORT_API (리포트 전송)   → Discord Webhook
```

**Tip:** 처음에는 mock 서버로 시작하고, 익숙해지면 실제 API로 교체

---

## 9. 핵심 학습 포인트 (단계별)

### Phase 1: 기본 뼈대 (1주차)

```
목표: FastAPI + SQLAlchemy + 4개 큐 + Worker 루프 동작

[ ] FastAPI 앱 세팅 (lifespan으로 큐/워커 시작)
[ ] SQLAlchemy 모델 정의 (7개 테이블)
[ ] Alembic 마이그레이션 초기화
[ ] queue_manager.py: asyncio.Queue 4개 생성/관리
[ ] Worker 4개: 각 큐에서 get() → 로직 → 다음 큐에 put()
[ ] pipeline_log 헬퍼 함수
[ ] mock 데이터로 전체 파이프라인 1회 통과 확인
```

**이 단계에서 익히는 것:**
- asyncio.Queue의 put/get 패턴
- async def worker 무한 루프 패턴
- FastAPI lifespan에서 백그라운드 태스크 시작
- SQLAlchemy async session 관리

### Phase 2: 외부 API 연동 (2주차)

```
목표: external_client 패턴 + API 로그 기록

[ ] external_client.py: httpx.AsyncClient 래퍼
[ ] api_req_res_logs 자동 기록 (SENT/SUCCESS/FAILED)
[ ] 재시도 로직 (exponential backoff)
[ ] mock 서버 만들기 (FastAPI 별도 앱)
[ ] 타임아웃 처리
```

**이 단계에서 익히는 것:**
- httpx 비동기 HTTP 클라이언트
- API 호출 래핑 패턴 (로깅, 재시도, 타임아웃)
- callId(UUID) 기반 추적

### Phase 3: LLM 연동 (3주차)

```
목표: price_analyzer에 실제 LLM 연동

[ ] OpenAI API 연동 (또는 Ollama 로컬)
[ ] 프롬프트 설계 (카테고리 분류 + 시세 추정)
[ ] JSON 응답 파싱 + 신뢰도 검증
[ ] confidence 기반 분기 처리
[ ] LLM 호출도 api_req_res_logs에 기록
```

**이 단계에서 익히는 것:**
- LLM API 연동 패턴
- 구조화된 출력(JSON mode) 처리
- confidence 기반 의사결정 로직

### Phase 4: 알림 + 에러 처리 (4주차)

```
목표: 실제 알림 전송 + 장애 대응 패턴

[ ] Telegram Bot 생성 + 메시지 전송
[ ] notification_logs 상태 관리 (PENDING → COMPLETED/FAILED)
[ ] 큐 폴링으로 PENDING 상태 추적 (← 회사 패턴 동일)
[ ] TIMEOUT 감지 로직
[ ] 중복 처리 방지 (이미 처리된 매물 SKIP)
[ ] 반복 폴링 방지 (메모리 캐시) ← 회사에서 구현한 그 패턴
```

**이 단계에서 익히는 것:**
- 상태 머신 패턴 (PENDING → PROCESSING → COMPLETED/FAILED)
- 폴링 + 타임아웃 패턴
- 메모리 캐시로 중복 방지

### Phase 5: 운영 안정성 (5주차)

```
목표: 모니터링 + 로그 분석

[ ] 운영 확인 쿼리 작성 (← 오늘 한 것과 동일!)
[ ] 일별 통계 API 엔드포인트
[ ] pipeline_logs 30일 자동 삭제
[ ] Graceful shutdown (큐에 남은 작업 완료 후 종료)
[ ] 헬스체크 엔드포인트
```

---

## 10. Worker 코드 뼈대 (참고용)

이건 회사 코드가 아니라 일반적인 asyncio 큐 패턴입니다:

```python
# workers/collect_worker.py (뼈대)
import asyncio
from app.core.queue_manager import QueueManager
from app.services.log_helpers import log_pipeline

async def collect_worker(queue_mgr: QueueManager, db_session_factory):
    """Queue-1 소비자: COLLECT_QUEUE에서 매물을 꺼내 검증 큐로 전달"""
    while True:
        item_data = await queue_mgr.collect_queue.get()
        try:
            async with db_session_factory() as session:
                await log_pipeline(session, item_data["itemId"], "item_collector", "START")

                # 중복 체크
                if await is_duplicate(session, item_data["itemId"]):
                    await log_pipeline(session, item_data["itemId"], "item_collector", "SKIP",
                                       {"reason": "이미 수집된 매물"})
                    continue

                # 다음 큐로 전달
                await queue_mgr.validate_queue.put(item_data)
                await log_pipeline(session, item_data["itemId"], "item_collector", "SUCCESS")

        except Exception as e:
            # 에러 로그 기록 후 계속 (워커 죽으면 안됨)
            await log_pipeline(session, item_data["itemId"], "item_collector", "FAILED",
                               {"error": str(e)})
        finally:
            queue_mgr.collect_queue.task_done()
```

```python
# core/queue_manager.py (뼈대)
import asyncio

class QueueManager:
    def __init__(self, maxsize: int = 100):
        self.collect_queue = asyncio.Queue(maxsize=maxsize)   # Queue-1
        self.validate_queue = asyncio.Queue(maxsize=maxsize)  # Queue-2
        self.analyze_queue = asyncio.Queue(maxsize=maxsize)   # Queue-3
        self.notify_queue = asyncio.Queue(maxsize=maxsize)    # Queue-4

    async def shutdown(self):
        """Graceful shutdown: 모든 큐가 비워질 때까지 대기"""
        await self.collect_queue.join()
        await self.validate_queue.join()
        await self.analyze_queue.join()
        await self.notify_queue.join()
```

```python
# main.py (뼈대)
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: 큐 매니저 + 워커 생성
    queue_mgr = QueueManager()
    workers = [
        asyncio.create_task(collect_worker(queue_mgr, get_session)),
        asyncio.create_task(validate_worker(queue_mgr, get_session)),
        asyncio.create_task(analyze_worker(queue_mgr, get_session)),
        asyncio.create_task(notify_worker(queue_mgr, get_session)),
    ]
    app.state.queue_mgr = queue_mgr

    yield

    # 종료: 워커 정리
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

app = FastAPI(lifespan=lifespan)
```

---

## 11. 운영 확인 쿼리 (Phase 5에서 직접 만들어볼 것)

오늘 회사 운영 DB 점검할 때 썼던 쿼리를 이 프로젝트에도 그대로 적용:

```sql
-- 일별 매물 처리 현황
SELECT DATE(createdAt) AS 날짜, COUNT(*) AS 전체,
       SUM(status='COMPLETED') AS 완료,
       SUM(status='FAILED') AS 실패,
       SUM(status='SKIPPED') AS 스킵
FROM items
GROUP BY DATE(createdAt);

-- PENDING 체류 건 확인
SELECT * FROM notification_logs
WHERE notifyStatus IN ('PENDING', 'TIMEOUT');

-- 파이프라인 단계별 현황
SELECT stage, event, COUNT(*) FROM pipeline_logs
WHERE createdAt >= DATE_SUB(NOW(), INTERVAL 1 DAY)
GROUP BY stage, event;
```

---

## 12. 추후 확장 아이디어

- **여러 워커 동시 실행:** `asyncio.create_task`로 같은 워커 N개 → 동시성 처리
- **Redis Queue로 교체:** 인메모리 큐 → Redis 기반으로 영속성 추가
- **Docker Compose:** DB + 앱 + Redis 한방 구성
- **GitHub Actions CI:** 테스트 자동화
- **Streamlit 대시보드:** 분석 결과 시각화