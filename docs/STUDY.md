# 학습 기록

---

## 2026-04-12 (1일차)

### 완료한 TASK
- [x] TASK-001: 프로젝트 초기 세팅 (디렉토리 구조 + FastAPI 뼈대)
- [x] TASK-002: QueueManager 클래스 구현
- [x] TASK-003: FastAPI lifespan에 QueueManager 연결
- [x] TASK-004: SQLAlchemy 비동기 DB 설정 (config.py + database.py)

### 남은 TASK (Phase 1)
- [ ] TASK-005: DB 모델 정의 (models.py - 7개 테이블)
- [ ] TASK-006: Alembic 마이그레이션 초기화
- [ ] TASK-007: pipeline_log 헬퍼 함수 (log_helpers.py)
- [ ] TASK-008: collect_worker 구현 (첫 번째 워커)
- [ ] TASK-009: validate_worker 구현
- [ ] TASK-010: analyze_worker 구현
- [ ] TASK-011: notify_worker 구현
- [ ] TASK-012: lifespan에 워커 4개 연결 + mock 데이터로 전체 파이프라인 1회 통과

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
