# 학습 기록

---

## 2026-04-12 (1일차)

### 완료한 TASK
- [x] TASK-001: 프로젝트 초기 세팅 (디렉토리 구조 + FastAPI 뼈대)
- [x] TASK-002: QueueManager 클래스 구현
- [x] TASK-003: FastAPI lifespan에 QueueManager 연결
- [x] TASK-004: SQLAlchemy 비동기 DB 설정 (config.py + database.py)

## 2026-04-13 (2일차)
### 남은 TASK (Phase 1) — ✅ Phase 1 완료!
- [x] TASK-005: DB 모델 정의 (models.py - 8개 테이블)
- [x] TASK-006: Alembic 마이그레이션 초기화
- [x] TASK-007: pipeline_log 헬퍼 함수 (log_helpers.py)
- [x] TASK-008: collect_worker 구현 (첫 번째 워커)
- [x] TASK-009: validate_worker 구현
- [x] TASK-010: analyze_worker 구현
- [x] TASK-011: notify_worker 구현
- [x] TASK-012: lifespan에 워커 4개 연결 + mock 데이터로 전체 파이프라인 1회 통과

---

## 2026-04-15 (3일차)
### 완료한 TASK (Phase 2) — ✅ Phase 2 완료!
- [x] TASK-013: external_client.py (httpx.AsyncClient 래퍼)
- [x] TASK-014: api_req_res_logs 자동 기록
- [x] TASK-015: 재시도 로직 (exponential backoff)
- [x] TASK-016: mock 서버 만들기
- [x] TASK-017: 타임아웃 처리

### 오늘 배운 것(2026-04-15)

#### httpx.AsyncClient 래퍼 패턴
- `__init__`은 동기 → AsyncClient를 바로 못 만듦 → `start()`/`close()` 분리 패턴
- `aclose()`로 닫아야 함 (`close()` 아님)
- `raise_for_status()`로 4xx/5xx를 한 곳에서 처리 → 호출하는 쪽은 성공만 신경 쓰면 됨

#### API 로그 자동 기록
- kwargs에서 커스텀 파라미터는 `pop()`으로 빼야 httpx에 안 넘어감
- `raise_for_status()`는 로그 기록 **후에** 호출 — 안 그러면 실패 로그를 못 남김
- 4xx/5xx 체크는 `response.is_success` 또는 status_code 범위로 직접 분기

#### Exponential Backoff 재시도
- 5xx, 네트워크 에러만 재시도 (서버 문제) / 4xx는 재시도 안 함 (클라이언트 문제)
- 대기 시간: `2 ** attempt` (1초 → 2초 → 4초)
- `httpx.RequestError`로 네트워크 에러 잡음 (TimeoutException도 하위 클래스라 같이 잡힘)

#### 타임아웃 세분화
- `httpx.Timeout(connect=, read=, write=)` 로 용도별 분리
- per-request 오버라이드: kwargs에서 pop한 값이 None이면 timeout을 아예 안 넘겨서 기본값 유지

#### FastAPI 에러 응답
- Flask처럼 `return {}, 400` 튜플 안 됨 → `JSONResponse(status_code=400, content={})` 사용
- POST body 받으려면 Pydantic BaseModel 파라미터로 선언

### 오늘 배운 것(2026-04-13)

#### SQLAlchemy 2.0 모델 정의
- `DeclarativeBase` 상속해서 Base 클래스 만듦
- `Mapped[타입]` + `mapped_column()` 조합으로 컬럼 정의
- nullable 컬럼은 `Mapped[타입 | None]`으로 선언해야 SQLAlchemy가 정확히 인식
- `String(20)` 처럼 길이 지정 — SQLite에서는 무시되지만 MariaDB 마이그레이션 대비
- `server_default=func.now()` → DB 레벨 기본값 (INSERT 시 DB가 넣어줌)
- `onupdate=func.now()` → UPDATE 시 자동 갱신 (SQLAlchemy ORM 레벨)
- `default=True` → 파이썬 레벨 기본값 (SQLite Boolean 호환)

#### Alembic 비동기 설정
- `alembic init alembic`으로 초기화
- env.py에서 `async_engine_from_config` + `connection.run_sync()` 패턴 사용
- `target_metadata = Base.metadata` 연결해야 autogenerate가 모델 감지
- `config.set_main_option("sqlalchemy.url", ...)` 으로 alembic.ini 하드코딩 대신 .env 사용
- `alembic revision --autogenerate -m "메시지"` → 마이그레이션 자동 생성
- `alembic upgrade head` → 마이그레이션 적용

#### Worker 패턴 (while True + try/except/finally)
- `await queue.get()` → try 블록에서 로직 → finally에서 `task_done()`
- `task_done()`은 성공/실패 상관없이 반드시 호출 (안 하면 `join()`이 영원히 안 풀림)
- except에서 새 세션 열어서 에러 로그 남김 (기존 세션이 깨졌을 수 있으니까)
- 워커는 절대 죽으면 안 됨 → except에서 continue

#### asyncio.create_task로 워커 시작/종료
- lifespan yield 위: `asyncio.create_task(worker(queue_mgr))` 로 워커 시작
- lifespan yield 아래: `w.cancel()` → `asyncio.gather(*workers, return_exceptions=True)`
- `return_exceptions=True` 안 하면 CancelledError가 터져서 종료 로직이 깨짐

#### APIRouter로 엔드포인트 분리
- `APIRouter(prefix="/api")` 로 라우터 생성
- `app.include_router(router)` 로 main에 연결
- `request.app.state.queue_mgr` 로 lifespan에서 만든 객체 접근

### 오늘 배운 것(2026-04-12)
#### asyncio.Queue
- `put()` : 큐에 넣기 (꽉 차면 대기)
- `get()` : 큐에서 꺼내기 (비어있으면 대기)
- `task_done()` : 꺼낸 거 처리 끝났다고 알림
- `join()` : 큐가 완전히 빌 때까지 대기 (연결이 아니라 "기다림")
- `qsize()` : 현재 큐에 들어있는 개수
- `maxsize` : 큐 최대 크기 — 초과 시 put()이 자동 대기 (백프레셔)

#### self
- `self.변수명` = 인스턴스 변수 (밖에서 접근 가능)
- `self` 없으면 지역변수 (함수 끝나면 사라짐)
- 오타 주의: `slef` 같은 실수하면 런타임 에러

#### FastAPI lifespan
- `yield` 위 = 앱 시작 시 실행 (큐 생성, DB 연결 등)
- `yield` 아래 = 앱 종료 시 실행 (큐 비우기, 정리 등)
- `app.state` = 앱 전체에서 공유하는 저장소
- 엔드포인트에서는 `request.app.state.변수명`으로 접근

#### Pydantic Settings (config.py)
- `BaseSettings`를 상속하면 `.env` 파일에서 자동으로 값을 읽어옴
- `model_config = {"env_file": ".env"}` 설정 필요
- 모듈 레벨에서 `settings = Settings()` 하면 싱글톤처럼 동작 (Python이 모듈을 1번만 로드하니까)

#### SQLAlchemy 비동기 설정 (database.py)
- `create_async_engine()` : DB 연결 통로. echo=True면 SQL이 콘솔에 찍힘
- `async_sessionmaker()` : 세션을 찍어내는 공장. 호출할 때마다 새 세션 생성
- `expire_on_commit=False` : 커밋 후에도 객체 속성에 바로 접근 가능 (비동기 환경에서 필수)
- `get_session()` : FastAPI Depends()에서 쓸 의존성 주입용 함수

#### shutdown 순서가 중요한 이유
- 파이프라인이 collect → validate → analyze → notify 순서로 흐름
- 위에서부터 순서대로 join()해야 중간에 작업이 유실되지 않음
- notify를 먼저 join하면 collect에 남은 작업이 흘러갈 곳이 없어짐
