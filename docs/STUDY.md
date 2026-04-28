# 학습 기록

> Claude가 짠 코드를 한 줄씩 설명받으며 익힌 패턴 정리.
> 코드 안 주석은 최소, 학습 설명은 여기서.

---

## TASK 진행 현황

### Phase 1 — 기본 뼈대 (2026-04-12 ~ 04-13) ✅
- [x] TASK-001~004: 프로젝트 초기 세팅 (FastAPI + QueueManager + SQLAlchemy 비동기 DB)
- [x] TASK-005: DB 모델 정의 (8개 테이블)
- [x] TASK-006: Alembic 마이그레이션 초기화
- [x] TASK-007: pipeline_log 헬퍼
- [x] TASK-008~011: 워커 4개 구현
- [x] TASK-012: lifespan에 워커 4개 연결 + mock 파이프라인 통과

### Phase 2 — 외부 API 연동 (2026-04-15) ✅
- [x] TASK-013: ExternalClient (httpx 래퍼)
- [x] TASK-014: api_req_res_logs 자동 기록
- [x] TASK-015: 재시도 로직 (exponential backoff)
- [x] TASK-016: mock 서버
- [x] TASK-017: 타임아웃 세분화

### Phase 3 — LLM 연동 (진행 중)
- [x] Phase 3-1: 멀티 프로바이더 LLM 클라이언트 (Gemini primary + Groq fallback) ← 2026-04-26
- [ ] Phase 3-2: price_analyzer에 LLMClient 통합 + 프롬프트 설계
- [ ] Phase 3-3: 응답 검증 + confidence 분기
- [ ] Phase 3-4 (이후): RAG (임베딩 + 유사 매물 검색 + S-Prompt)

---

## 2026-04-26 (Phase 3-1: 멀티 프로바이더 LLM 클라이언트)

### Pydantic Settings — 시크릿 vs 동작 파라미터 구분
- `.env` = 시크릿 전용 (API 키, DB 비밀번호). git에 안 올림
- `config.py` = `.env`의 문자열을 파이썬 객체로 변환 + 타입 검증 + 싱글톤 (`settings = Settings()`)
- 같은 Settings 클래스 안에 두되 **기본값으로 구분**:
  - 시크릿: `GEMINI_API_KEY: str = ""` (빈 값, `.env`에 있으면 덮어씀)
  - 모델 이름/타임아웃: `GEMINI_MODEL: str = "gemini-2.5-flash"` (코드 기본값, `.env`로 오버라이드 가능)
- `.env`에 값 있으면 Pydantic이 기본값을 **덮어씀**. 기본값은 fallback (없을 때만 사용)
- 모델 이름은 시크릿 X → 코드에 박아도 됨 (공개 정보)

### .gitignore에 등록해도 이미 추적된 파일은 계속 추적됨
- `.gitignore`는 "**아직 추적 안 되는** 새 파일"만 무시
- 이미 한 번 커밋된 파일은 `.gitignore`에 등록해도 git이 계속 추적함
- 해결: `git rm --cached <파일>` → 인덱스에서만 제거, 디스크 파일 보존
- 이후 수정해도 git에 안 잡힘

### Protocol 패턴 (덕타이핑 인터페이스)
- `from typing import Protocol`
- 추상 베이스 클래스(ABC) 대안
  - ABC: 명시적 상속(`class X(ABC):`) 필요, 안 따르면 인스턴스화 시점에 에러
  - Protocol: 상속 안 해도 메서드 모양만 맞으면 OK (덕타이핑)
- 타입 체커(mypy/Pylance)가 정적으로 검증
- 본문에 `...` (Ellipsis) 만 적음 → 시그니처 정의만, 실제 동작 X
- 외부 라이브러리 클래스도 모양만 맞으면 그대로 사용 가능 → 새 프로바이더 추가 비용 ↓

### 사용자 정의 예외
- 표준 예외(`HTTPError` 등) 대신 **의도가 드러나는 예외 클래스** 만들기
- `class QuotaExceededError(Exception):` — `Exception` 상속 (절대 `BaseException` 직접 상속 X, `KeyboardInterrupt` 잡힐 위험)
- 호출자가 `except QuotaExceededError` 한 줄로 정확히 잡음 → fallback 트리거 의도가 코드에 명시
- 비즈니스 로직 예외는 무조건 `Exception` 상속

### 예외 체이닝 (`raise X from e`)
- `raise QuotaExceededError(...) from e` → 원본 예외(e) 보존
- 디버깅 시 traceback에 원본 → 변환된 예외 흐름이 다 보임
- 그냥 `raise X(...)` 로만 던지면 원본 컨텍스트 손실

### `raise` (인자 없음)
- `try/except` 안에서 `raise` (인자 없음) = **현재 잡고 있는 예외 그대로 다시 던짐**
- `raise QuotaExceededError(...)` 와 다름 (이건 새 예외 던지기)

### `is None` vs `== None`
- `None`은 싱글톤 → `is`로 식별 비교 (Python 컨벤션)
- `== None`도 동작은 하지만 비표준

### Gemini vs Groq API 형식 차이
| 항목 | Gemini | Groq (OpenAI 호환) |
|---|---|---|
| 인증 | URL 쿼리 `?key=...` | 헤더 `Authorization: Bearer ...` |
| 메시지 형식 | `contents: [{parts: [{text}]}]` | `messages: [{role, content}]` |
| 모델 지정 | URL 경로 `/models/{model}:generateContent` | body `{"model": "..."}` |
| 응답 위치 | `candidates[0].content.parts[0].text` | `choices[0].message.content` |
| JSON 강제 | `generationConfig.responseMimeType: "application/json"` | `response_format: {"type": "json_object"}` |
| Schema 강제 | ✅ `responseSchema` (JSON Schema 표준) | ❌ 미지원 (prompt 안내로만) |
| 시스템 메시지 | `systemInstruction` 별도 필드 | `messages`에 `{role: "system"}` |

→ 프로바이더별 API 형식이 다 달라서 **프로바이더 추상화 레이어 필수**

### Fallback vs Retry — 다른 메커니즘
- **Retry** (ExternalClient 안): 같은 프로바이더에 1초→2초→4초 다시 호출. 일시 장애(네트워크/5xx) 대상
- **Fallback** (LLMClient 안): 다른 프로바이더로 전환. quota/rate limit 대상
- 흐름 순서: 재시도 다 실패 → fallback 한 번
- 4xx는 재시도 X (어차피 같은 결과 → 즉시 위로 raise)

### 날짜 기반 자동 해제 (cleanup 코드 X)
- `self._primary_quota_blocked_date: date | None = None`
- quota 감지 시: `self._primary_quota_blocked_date = date.today()`
- 판단: `self._primary_quota_blocked_date == date.today()` → True면 차단 상태
- 자정 지나면 → `date.today()` 가 다른 날짜 → 자동으로 False → 별도 cleanup 불필요
- 메모리에만 둠 → 재시작 시 사라지지만, 재시작 직후 1회 quota 시도 = 무시할 비용

### Facade 패턴
- LLMClient = 외부 진입점 1개로 통일
- 호출자(price_analyzer)는 GeminiProvider/GroqProvider 직접 안 만짐
- 새 프로바이더 추가 시 호출자 코드 변경 X (LLMClient 내부만 확장)

### 의존성 주입 (settings 직접 안 읽고 인자로)
- `def __init__(self, api_key: str, model: str):` — 시크릿/모델을 인자로 받음
- 장점:
  - 테스트 쉬움 (가짜 키로 인스턴스 생성)
  - 의존성이 시그니처에 명시
  - 다른 프로젝트로 가져갈 때 settings 의존 X
- settings는 **인스턴스 생성하는 쪽**(LLMClient 만드는 main.py)에서 읽어서 넘김

### Pylance 미사용 인자 처리
- 함수 인자를 본문에서 안 쓰면 Pylance 경고
- 해결: `_ = arg` + 주석으로 의도 명시 (예: Protocol 시그니처 일치를 위해 받지만 본 구현에선 미사용)
- 사용 예: `GroqProvider._build_request_body`의 `schema` 인자

### URL에 키 박는 보안 위험
- Gemini는 인증을 URL 쿼리(`?key=...`)로 함 → `api_req_res_logs.requestBody`나 URL 로그에 키 그대로 남음
- 운영 단계에선 마스킹 필요 (`?key=***`)
- Groq의 `Authorization: Bearer ...` 헤더 방식이 보안상 약간 더 좋음

### `dict[str, Any]` 타입 어노테이션
- `Any` = 값 타입이 다양할 때 (str, int, list, nested dict 등)
- 어노테이션 없어도 동작은 함. 있으면 타입 체커가 잘못 쓸 게 잡아줌
- `body: dict[str, Any] = {...}` 가 그냥 `body = {...}` 보다 명시적

### lifespan에서 LLMClient 의존성 조립
- 시크릿/모델은 `settings`에서 읽고 → Provider 인스턴스 → LLMClient → `app.state.llm_client`
- 워커가 시작되기 **전에** `await llm_client.start()` 끝내고 state에 저장 (반대 순서면 워커가 None 들고 시작 위험)
- 종료 순서: 워커 cancel → `llm_client.close()` → `queue_mgr.shutdown()`
  - 워커 살아 있을 때 LLM 닫으면 호출 중 소켓 닫히는 경합

### 검증/디버그 도구도 큐 기반으로
- 운영 워커(`analyze_worker`)에 검증 코드 끼우지 말고 **별도 큐 + 별도 워커 + 별도 파일**
  - 같이 두면 운영 코드 손댈 때 검증 코드가 같이 깨짐
- `llm_ping_queue`(부가 큐) + `llm_ping_worker`(부가 워커) + `POST /api/_debug/llm-ping`(부가 엔드포인트)
- 운영 매물 파이프라인(collect→validate→analyze→notify)과 완전 독립 → 한쪽이 막혀도 다른 쪽 영향 X

### 202 Accepted (큐에 던지고 즉시 반환)
- 엔드포인트가 비동기 처리에 위임할 땐 `200 OK` 아니라 `status_code=202`
- 시맨틱: "받았고, 처리는 비동기로". 결과는 다른 채널(콘솔/DB/별도 조회 API)
- FastAPI: `@router.post("/path", status_code=202)`

### 검증 워커의 "친구" 권한 (`_protected` 변수 직접 set)
- 일반적으로 밑줄 변수(`_primary_quota_blocked_date`)는 외부에서 안 건드림
- 검증 워커는 예외: 본질이 "내부 상태를 강제 조작해서 fallback 경로 실행"
- 운영 워커는 절대 안 건드림 → 캡슐화 위반은 검증 워커 한 곳에 가둠

### 의존성 주입 시그니처 두 가지
- 큐만 필요: `async def collect_worker(queue_mgr: QueueManager)` (Phase 1 패턴)
- 큐 + 외부 의존성: `async def llm_ping_worker(queue_mgr: QueueManager, llm_client: LLMClient)`
- `app.state` 통해 가져오는 것보다 인자 주입이 결합도 ↓ + 테스트 쉬움
- Phase 3-2의 analyze_worker도 `llm_client` 인자 받도록 리팩터 예정 → 일관성

---

## 2026-04-15 (Phase 2: 외부 API 연동)

### httpx.AsyncClient 래퍼 패턴
- `__init__`은 동기 → AsyncClient를 바로 못 만듦 → `start()`/`close()` 분리 패턴
- `aclose()`로 닫아야 함 (`close()` 아님)
- `raise_for_status()`로 4xx/5xx를 한 곳에서 처리 → 호출자는 성공만 신경 쓰면 됨

### API 로그 자동 기록
- kwargs에서 커스텀 파라미터(item_id 등)는 `pop()`으로 빼야 httpx에 안 넘어감
- `raise_for_status()`는 로그 기록 **후에** 호출 — 안 그러면 실패 로그를 못 남김
- 4xx/5xx 체크는 `response.is_success` 또는 status_code 범위로 직접 분기

### Exponential Backoff 재시도
- 5xx, 네트워크 에러만 재시도 (서버 문제) / 4xx는 재시도 X (클라이언트 문제)
- 대기 시간: `2 ** attempt` (1초 → 2초 → 4초)
- `httpx.RequestError`로 네트워크 에러 잡음 (TimeoutException도 하위 클래스라 같이 잡힘)

### 타임아웃 세분화
- `httpx.Timeout(connect=, read=, write=)` 로 용도별 분리
- per-request 오버라이드: kwargs에서 pop한 값이 None이면 timeout을 안 넘겨서 기본값 유지

### FastAPI 에러 응답
- Flask처럼 `return {}, 400` 튜플 안 됨 → `JSONResponse(status_code=400, content={})` 사용
- POST body 받으려면 Pydantic BaseModel 파라미터로 선언

---

## 2026-04-13 (Phase 1: DB 모델 + 워커)

### SQLAlchemy 2.0 모델 정의
- `DeclarativeBase` 상속해서 Base 클래스 만듦
- `Mapped[타입]` + `mapped_column()` 조합으로 컬럼 정의
- nullable 컬럼은 `Mapped[타입 | None]`으로 선언해야 SQLAlchemy가 정확히 인식
- `String(20)` 처럼 길이 지정 — SQLite에서는 무시되지만 MariaDB 마이그레이션 대비
- `server_default=func.now()` → DB 레벨 기본값 (INSERT 시 DB가 넣어줌)
- `onupdate=func.now()` → UPDATE 시 자동 갱신 (SQLAlchemy ORM 레벨)
- `default=True` → 파이썬 레벨 기본값 (SQLite Boolean 호환)

### Alembic 비동기 설정
- `alembic init alembic`으로 초기화
- env.py에서 `async_engine_from_config` + `connection.run_sync()` 패턴 사용
- `target_metadata = Base.metadata` 연결해야 autogenerate가 모델 감지
- `config.set_main_option("sqlalchemy.url", ...)` 으로 alembic.ini 하드코딩 대신 .env 사용
- `alembic revision --autogenerate -m "메시지"` → 마이그레이션 자동 생성
- `alembic upgrade head` → 마이그레이션 적용

### Worker 패턴 (while True + try/except/finally)
- `await queue.get()` → try 블록에서 로직 → finally에서 `task_done()`
- `task_done()`은 성공/실패 상관없이 반드시 호출 (안 하면 `join()`이 영원히 안 풀림)
- except에서 새 세션 열어서 에러 로그 남김 (기존 세션이 깨졌을 수 있으니까)
- 워커는 절대 죽으면 안 됨 → except에서 continue

### asyncio.create_task로 워커 시작/종료
- lifespan yield 위: `asyncio.create_task(worker(queue_mgr))` 로 워커 시작
- lifespan yield 아래: `w.cancel()` → `asyncio.gather(*workers, return_exceptions=True)`
- `return_exceptions=True` 안 하면 CancelledError가 터져서 종료 로직이 깨짐

### APIRouter로 엔드포인트 분리
- `APIRouter(prefix="/api")` 로 라우터 생성
- `app.include_router(router)` 로 main에 연결
- `request.app.state.queue_mgr` 로 lifespan에서 만든 객체 접근

---

## 2026-04-12 (Phase 1: 큐 + lifespan + 설정)

### asyncio.Queue
- `put()` : 큐에 넣기 (꽉 차면 대기)
- `get()` : 큐에서 꺼내기 (비어있으면 대기)
- `task_done()` : 꺼낸 거 처리 끝났다고 알림
- `join()` : 큐가 완전히 빌 때까지 대기 (연결이 아니라 "기다림")
- `qsize()` : 현재 큐에 들어있는 개수
- `maxsize` : 큐 최대 크기 — 초과 시 put()이 자동 대기 (백프레셔)

### self
- `self.변수명` = 인스턴스 변수 (밖에서 접근 가능)
- `self` 없으면 지역변수 (함수 끝나면 사라짐)
- 오타 주의: `slef` 같은 실수하면 런타임 에러

### FastAPI lifespan
- `yield` 위 = 앱 시작 시 실행 (큐 생성, DB 연결 등)
- `yield` 아래 = 앱 종료 시 실행 (큐 비우기, 정리 등)
- `app.state` = 앱 전체에서 공유하는 저장소
- 엔드포인트에서는 `request.app.state.변수명`으로 접근

### Pydantic Settings (config.py)
- `BaseSettings`를 상속하면 `.env` 파일에서 자동으로 값을 읽어옴
- `model_config = {"env_file": ".env"}` 설정 필요
- 모듈 레벨에서 `settings = Settings()` 하면 싱글톤처럼 동작 (Python이 모듈을 1번만 로드하니까)

### SQLAlchemy 비동기 설정 (database.py)
- `create_async_engine()` : DB 연결 통로. echo=True면 SQL이 콘솔에 찍힘
- `async_sessionmaker()` : 세션을 찍어내는 공장. 호출할 때마다 새 세션 생성
- `expire_on_commit=False` : 커밋 후에도 객체 속성에 바로 접근 가능 (비동기 환경에서 필수)
- `get_session()` : FastAPI Depends()에서 쓸 의존성 주입용 함수

### shutdown 순서가 중요한 이유
- 파이프라인이 collect → validate → analyze → notify 순서로 흐름
- 위에서부터 순서대로 join()해야 중간에 작업이 유실되지 않음
- notify를 먼저 join하면 collect에 남은 작업이 흘러갈 곳이 없어짐
