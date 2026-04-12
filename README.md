# AI 중고거래 매물 자동 분석 시스템

중고거래 플랫폼(당근, 번개장터 등)의 매물을 자동 수집하고, LLM으로 시세를 분석한 뒤, 좋은 매물을 알림으로 받아보는 비동기 파이프라인 시스템입니다.

---

## 주요 기능

- 키워드 기반 매물 자동 수집 (폴링 방식)
- 판매자 신뢰도 검증 (거래횟수, 매너온도 기반 등급 산정)
- 매물 유효성 검증 (판매 완료 여부, 가격 범위 필터링)
- LLM 기반 카테고리 분류 + 시세 추정 (OpenAI / Ollama)
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

## DB 설계 (7개 테이블)

| 테이블 | 역할 |
|--------|------|
| `items` | 매물 마스터 (수집~분석~알림 전체 상태 관리) |
| `item_images` | 매물 이미지 정보 |
| `price_history` | 카테고리별 시세 이력 (스냅샷) |
| `notification_logs` | 알림 전송 상태 추적 (PENDING → COMPLETED/FAILED) |
| `pipeline_logs` | 파이프라인 단계별 처리 로그 |
| `api_req_res_logs` | 외부 API 호출 요청/응답 로그 (UUID 추적) |
| `watch_keywords` | 사용자 감시 키워드 + 최대 가격 설정 |

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
