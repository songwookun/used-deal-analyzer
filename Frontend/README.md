# Frontend — AI 파이프라인 관측 대시보드

`Vite + React` 기반의 옵저버빌리티 콘솔. 백엔드(FastAPI 비동기 4단계 큐 워커 · LLM 분석 · 네이버 데이터랩 트렌드 · RAG)의 상태와 결과를 실시간으로 시각화합니다.

> 단독 실행이 아닌 **모노레포 일부**입니다. 전체 실행은 루트의 `start.command`(macOS) / `start.bat`(Windows) 사용을 권장합니다.

---

## 빠른 시작

```bash
# 의존성 설치 (최초 1회)
npm install

# 개발 서버 (기본 :5173)
npm run dev

# 프로덕션 빌드
npm run build

# 빌드 결과 미리보기
npm run preview

# ESLint
npm run lint
```

백엔드는 기본적으로 `http://localhost:8000` 으로 가정합니다. 다른 호스트면 환경변수로 지정:

```bash
VITE_API=http://192.168.0.10:8000 npm run dev
```

---

## 화면 구성

### 1. 대시보드 — `파이프라인 개요`
다섯 단계 위계로 정보를 노출합니다.

| 단계 | 영역 | 데이터 소스 |
|---|---|---|
| 1 | 시스템 상태 히어로 (System Readiness · 워커 · DB · LLM 엔진) | `GET /health/ready` |
| 2 | 핵심 지표 KPI (누적/오늘/상승 예측/주요 가격대) | `GET /api/stats` |
| 3 | 파이프라인 처리 흐름 (수집 → 검증 → 분석 → 발신 + LLM 핑) | `GET /health/ready` (queues) |
| 4 | 운영 인사이트 2-col (LLM 트렌드 · 가격대 분포 / 실패 표면 · 외부 API 호출) | `GET /api/stats` |
| 5 | 최근 파이프라인 활동 로그 테이블 | `GET /api/stats?recent=10` |

추가로 카테고리 트렌드(데이터랩) · 인기 검색어 패널이 4단계와 5단계 사이에 위치합니다.

### 2. 분석 콘솔 — `키워드 분석`
키워드 입력 → 백엔드 파이프라인 실행 → AI 분석 리포트 형태로 결과 표시.

```
검색 입력 → 결과 헤더 → LLM 종합 평가(강조)
        → 키워드 트렌드 → 가격 분포
        → 대체품 추천 → RAG 근거 자료
        → 검색 결과 테이블
```

캐시된 결과 자동 로드 + 새로 검색 재실행 모두 지원.

---

## 폴링 주기

- `/health/ready` — 5초 (App 레벨에서 한 번만 폴링, Sidebar/TopBar/대시보드가 공유)
- `/api/stats?recent=10` — 5초 (대시보드만)

`POLL_MS` 상수 한 곳에서 관리됩니다 (`src/App.jsx`).

---

## 디자인 토큰

`src/index.css` 의 `:root` 에 모두 정의되어 있습니다.

- **베이스**: 다크 graphite 사이드바 (`#0e1218`) + 라이트 cool gray 메인 (`#f4f6fa`)
- **단일 액센트**: indigo (`#6366f1`)
- **시맨틱 컬러**: green / amber / red / violet / blue (각 base + soft 배경 + line 보더)
- **타이포그래피**: 영문 sans는 시스템 / Inter, 한글은 Pretendard / Apple SD Gothic Neo. 모노스페이스(JetBrains Mono / SF Mono)는 ID·시간·숫자 로그에만 사용
- **레이아웃**: 사이드바 232px, 톱바 56px, 카드 radius 8~16px

레퍼런스 톤: Linear · Datadog · Grafana Cloud · Vercel Observability.

---

## 폴더 구조

```
Frontend/
├── index.html              # 진입 HTML (페이지 타이틀)
├── vite.config.js
├── eslint.config.js
├── package.json
├── public/
│   ├── favicon.svg
│   └── icons.svg
└── src/
    ├── main.jsx            # React 엔트리
    ├── App.jsx             # 앱 셸 (사이드바 · 톱바 · 라우팅 · 헬스 폴링) + 대시보드
    ├── SearchPage.jsx      # 분석 콘솔
    ├── App.css             # 컴포넌트 / 레이아웃 스타일
    ├── index.css           # 디자인 토큰 + 글로벌 리셋
    └── assets/             # 정적 이미지
```

---

## 개발 메모

- **상태 끌어올리기**: `health` 폴링은 App 레벨 한 곳. Sidebar / TopBar / Dashboard 가 props로 공유 (fetch 중복 X)
- **자동 로드 흐름**: 대시보드의 활동 로그/인기 검색어를 클릭하면 `pendingSearchId` 가 분석 페이지로 전달되어 캐시된 결과를 즉시 로드
- **외부 의존성 최소화**: UI 라이브러리 없음 — 모든 컴포넌트는 자체 JSX + CSS. 아이콘은 `lucide-react` 만 사용

---

## ESLint

- React 19 + `eslint-plugin-react-hooks` 7.x 룰 적용
- `react-hooks/set-state-in-effect` 룰은 폴링 useEffect 두 곳에서 의도적으로 disable (마운트 시 즉시 fetch가 의도된 동작)
