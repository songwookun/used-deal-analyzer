import { useEffect, useState, useCallback } from 'react'
import {
  Search as SearchIcon,
  LayoutDashboard,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Minus,
  Globe,
  ArrowRight,
  Activity,
  Cpu,
  Database,
  Layers,
  ChevronRight,
  AlertTriangle,
  Zap,
} from 'lucide-react'
import SearchPage from './SearchPage'
import './App.css'

const API = import.meta.env.VITE_API ?? 'http://localhost:8000'
const POLL_MS = 5000

const TREND_ICON = { 급상승: TrendingUp, 안정: Minus, 하락: TrendingDown }
const TREND_TONE = { 급상승: 'green', 안정: 'muted', 하락: 'red' }
const FORECAST_TONE = { RISING: 'green', STEADY: 'muted', FALLING: 'red' }
const FORECAST_LABEL = { RISING: '상승', STEADY: '안정', FALLING: '하락' }
const FORECAST_ICON = { RISING: TrendingUp, STEADY: Minus, FALLING: TrendingDown }
const PRICE_BUCKET_LABEL = {
  under_10k: '~1만원',
  '10k_100k': '1~10만원',
  '100k_1m': '10~100만원',
  over_1m: '100만원+',
}

const PIPELINE_STAGES = [
  { key: 'collect',  label: '수집',  note: '스크래핑' },
  { key: 'validate', label: '검증',  note: '정규화' },
  { key: 'analyze',  label: '분석',  note: 'LLM + RAG' },
  { key: 'notify',   label: '발신',  note: '알림 전달' },
]
const AUX_STAGE = { key: 'llm_ping', label: 'LLM 핑', note: '헬스 프로브' }

function formatNumber(n) { return (n ?? 0).toLocaleString('ko-KR') }
function formatTime(iso) { if (!iso) return '—'; return new Date(iso).toLocaleTimeString('ko-KR', { hour12: false }) }

/* ---------- App shell ---------- */

export default function App() {
  const [view, setView] = useState('dashboard')
  const [pendingSearchId, setPendingSearchId] = useState(null)
  const [health, setHealth] = useState(null)

  // Health polling — lifted to App so Sidebar / TopBar / Dashboard 모두 공유
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const r = await fetch(`${API}/health/ready`)
        const body = await r.json()
        if (alive) setHealth({ ok: r.ok, body, fetchedAt: Date.now() })
      } catch {
        if (alive) setHealth({ ok: false, body: null, fetchedAt: Date.now() })
      }
    }
    tick()
    const t = setInterval(tick, POLL_MS)
    return () => { alive = false; clearInterval(t) }
  }, [])

  function openSearch(id) {
    setPendingSearchId(id)
    setView('search')
  }

  const pageMeta = view === 'search'
    ? { title: '분석 콘솔', sub: 'RAG + 데이터랩 + LLM 파이프라인' }
    : { title: '파이프라인 개요', sub: '워커 · 큐 · 검색 분석' }

  return (
    <div className="layout">
      <Sidebar view={view} onChange={setView} health={health} />
      <TopBar title={pageMeta.title} sub={pageMeta.sub} health={health} />
      <main className="main">
        {view === 'search'
          ? <SearchPage
              autoLoadId={pendingSearchId}
              onConsumeAutoLoad={() => setPendingSearchId(null)}
            />
          : <Dashboard onOpenSearch={openSearch} health={health} />
        }
      </main>
    </div>
  )
}

/* ---------- Sidebar ---------- */

function Sidebar({ view, onChange, health }) {
  const overall = computeOverall(health)
  const workers = health?.body?.components?.workers || {}
  const aliveCount = Object.values(workers).filter(v => v === 'alive').length
  const totalCount = Object.keys(workers).length

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">
          <Sparkles size={16} strokeWidth={2.25} />
        </div>
        <div className="brand-text">
          <div className="brand-name">쇼핑 분석기</div>
          <div className="brand-sub">RAG · 데이터랩 · LLM</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <NavItem icon={LayoutDashboard} active={view === 'dashboard'} onClick={() => onChange('dashboard')}>
          개요
        </NavItem>
        <NavItem icon={SearchIcon} active={view === 'search'} onClick={() => onChange('search')}>
          분석
        </NavItem>
      </nav>

      <div className="sidebar-foot">
        <div className="side-status">
          <div className="side-status-row">
            <span className={`status-led status-led--${overall.tone}`} />
            <span>{overall.label}</span>
          </div>
          {totalCount > 0 && (
            <div className="side-status-detail">
              <span className={aliveCount === totalCount ? 'ok' : 'warn'}>
                {aliveCount}/{totalCount}
              </span>
              <span> 워커 정상</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}

function NavItem({ icon: Icon, active, onClick, children }) {
  return (
    <button className={`nav-item ${active ? 'nav-item--active' : ''}`} onClick={onClick}>
      <Icon size={15} strokeWidth={2} />
      <span>{children}</span>
    </button>
  )
}

/* ---------- TopBar ---------- */

function TopBar({ title, sub, health }) {
  const overall = computeOverall(health)
  const lastFetched = health?.fetchedAt
    ? new Date(health.fetchedAt).toLocaleTimeString('ko-KR', { hour12: false })
    : '—'

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-title">{title}</div>
        <div className="topbar-sub">{sub}</div>
      </div>
      <div className="topbar-right">
        <span className="refresh-meta">
          <span className="pulse" />
          <span>마지막 동기화 {lastFetched}</span>
        </span>
        <span className={`health-pill health-pill--${overall.tone === 'green' ? 'ok' : overall.tone === 'red' ? 'bad' : 'warn'}`}>
          <span className="dot" />
          {overall.label}
        </span>
      </div>
    </header>
  )
}

/* ---------- Health computation ---------- */

function computeOverall(health) {
  if (!health) return { tone: 'red', label: '연결 불가' }
  if (!health.body) return { tone: 'red', label: '연결 불가' }
  const status = health.body.status
  if (status === 'ok' && health.ok) return { tone: 'green', label: '시스템 정상' }
  return { tone: 'amber', label: '일부 이상' }
}

/* ---------- Dashboard ---------- */

function Dashboard({ onOpenSearch, health }) {
  const [stats, setStats] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const s = await fetch(`${API}/api/stats?recent=10`).then(r => r.json())
      setStats(s)
    } catch {
      // network errors handled by leaving prior stats intact
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh])

  const s = stats || {}
  const searches = s.searches || {}
  const totalSearches = searches.total ?? 0
  const todaySearches = searches.today ?? 0
  const forecast = searches.byForecast || {}
  const buckets = searches.byPriceBucket || {}

  const topBucket = Object.entries(buckets).sort((a, b) => b[1] - a[1])[0]
  const topBucketLabel = topBucket && topBucket[1] > 0 ? PRICE_BUCKET_LABEL[topBucket[0]] : '—'

  const queues = health?.body?.components?.queues || {}

  return (
    <>
      <div className="page-header">
        <div>
          <span className="crumb">관제 플레인</span>
          <h1>AI 파이프라인 관측 대시보드</h1>
          <p>비동기 4단계 큐 워커 · LLM 분석 · 네이버 데이터랩 트렌드 · RAG 유사 검색을 한 화면에서 관측합니다.</p>
        </div>
      </div>

      {/* 1. SYSTEM STATUS HERO — 가장 시각적으로 우세한 영역 */}
      <SystemStatusHero health={health} />

      {/* 2. KPI ROW — 큰 숫자 4개 */}
      <div className="section-head section-head--prominent">
        <div className="section-title">
          <Zap size={13} strokeWidth={2.5} className="section-icon" />
          <h2>핵심 지표</h2>
        </div>
        <span className="muted small mono">전체 누적 · 실시간</span>
      </div>
      <div className="kpi-row">
        <KpiTile label="누적 검색"     value={totalSearches}             tone="indigo" />
        <KpiTile label="오늘 검색"     value={todaySearches}             tone="amber"  />
        <KpiTile label="상승 예측"     value={forecast.RISING ?? 0}      tone="green"  />
        <KpiTile label="주요 가격대"   value={topBucketLabel} mono={false} tone="violet" />
      </div>

      {/* 3. PIPELINE FLOW — 화살표로 연결된 4단계 흐름 + 보조 LLM 핑 */}
      <div className="section-head">
        <div className="section-title">
          <Layers size={13} strokeWidth={2.5} className="section-icon" />
          <h2>파이프라인 처리 흐름</h2>
        </div>
        <span className="muted small mono">큐 적재량 · 5초 폴링</span>
      </div>
      <PipelineFlow queues={queues} />

      {/* 4. INSIGHT — 2-column 분석 영역 */}
      <div className="section-head">
        <div className="section-title">
          <Activity size={13} strokeWidth={2.5} className="section-icon" />
          <h2>운영 인사이트</h2>
        </div>
        <span className="muted small mono">집계 · 분포 · 실패 표면</span>
      </div>
      <div className="insight-grid">
        <div className="insight-col">
          <Subsection title="LLM 트렌드 예측 분포" subtitle="누적 검색의 LLM 평가 분포">
            <ForecastBars forecast={forecast} />
          </Subsection>
          <Subsection title="가격대 분포" subtitle="검색된 상품 중앙가 기준">
            <BucketBars buckets={buckets} />
          </Subsection>
        </div>
        <div className="insight-col">
          <Subsection title="실패 표면" subtitle="외부 API 실패 횟수 상위" icon={AlertTriangle}>
            <FailureSurface apiCalls={s.apiCalls} />
          </Subsection>
          <Subsection title="외부 API 호출" subtitle="apiType별 발송 / 성공 / 실패" icon={Globe}>
            <ApiCallsTable apiCalls={s.apiCalls} />
          </Subsection>
        </div>
      </div>

      {/* 보조 분석: 카테고리 트렌드 + 인기 검색어 */}
      <Section title="카테고리 트렌드" subtitle="네이버 데이터랩 (최근 7일 vs 이전 7일)">
        <TrendsRow trends={s.categoryTrends} />
      </Section>

      <Section title="인기 검색어" subtitle="동일 키워드 검색 빈도 상위 10">
        <TopQueries items={s.topQueries} onOpenSearch={onOpenSearch} stats={s.recent} />
      </Section>

      {/* 5. LOG TABLE — 운영 로그 뷰어 */}
      <Section title="최근 파이프라인 활동" subtitle="저장된 분석 결과 · 행 클릭 시 즉시 로드">
        <RecentSearchTable rows={s.recent} onOpen={onOpenSearch} />
      </Section>

      <footer className="footer">
        <span className="muted small">자동 갱신 {POLL_MS / 1000}초</span>
        <span className="muted small">·</span>
        <span className="muted small">{s.asOf ? `기준 ${formatTime(s.asOf)}` : '불러오는 중…'}</span>
      </footer>
    </>
  )
}

/* ---------- System Status Hero ---------- */

function SystemStatusHero({ health }) {
  const body = health?.body
  const components = body?.components || {}
  const workers = components.workers || {}
  const dbState = components.db || (health ? '—' : 'unknown')
  const llm = components.llm || {}

  const overall = computeOverall(health)

  const totalWorkers = Object.keys(workers).length
  const aliveWorkers = Object.values(workers).filter(v => v === 'alive').length
  const workerTone = totalWorkers === 0 ? 'muted' : aliveWorkers === totalWorkers ? 'green' : aliveWorkers === 0 ? 'red' : 'amber'
  const workerLabel = totalWorkers === 0
    ? '데이터 없음'
    : `${aliveWorkers}/${totalWorkers} 정상`

  const dbTone = dbState === 'ok' ? 'green' : dbState === 'unknown' || dbState === '—' ? 'muted' : 'red'
  const dbLabel = dbState === 'ok' ? '정상' : dbState

  const primaryState = llm.primary || '—'
  const fallbackState = llm.fallback || '—'
  const llmTone = primaryState === 'available' && (fallbackState === 'available' || fallbackState === 'none')
    ? 'green'
    : primaryState === 'exhausted' && fallbackState === 'available'
      ? 'amber'
      : primaryState === '—' ? 'muted' : 'red'
  const LLM_LABEL = { available: '사용 가능', exhausted: '쿼터 소진', none: '없음', unavailable: '사용 불가' }
  const llmLabel = primaryState === '—' ? '확인 중' : (LLM_LABEL[primaryState] ?? primaryState)
  const primaryKo = LLM_LABEL[primaryState] ?? primaryState
  const fallbackKo = LLM_LABEL[fallbackState] ?? fallbackState

  return (
    <div className="status-hero">
      <div className="status-hero-inner">
        <div className="status-cell">
          <span className="status-cell-label"><Activity size={12} strokeWidth={2.5} /> 시스템 준비 상태</span>
          <span className="status-cell-value">
            <span className={`status-led status-led--${overall.tone}`} />
            <span>{overall.label}</span>
          </span>
          <span className="status-cell-meta">
            {body?.status ? `상태=${body.status}` : '첫 헬스체크 대기 중…'}
          </span>
        </div>

        <div className="status-cell">
          <span className="status-cell-label"><Cpu size={12} strokeWidth={2.5} /> 비동기 워커</span>
          <span className="status-cell-value">
            <span className={`status-led status-led--${workerTone}`} />
            <span>{workerLabel}</span>
          </span>
          <span className="status-cell-meta">
            {totalWorkers > 0
              ? Object.entries(workers).map(([n, v]) => `${n}=${v}`).slice(0, 3).join(' · ')
              : '워커 등록 없음'}
          </span>
        </div>

        <div className="status-cell">
          <span className="status-cell-label"><Database size={12} strokeWidth={2.5} /> 데이터베이스</span>
          <span className="status-cell-value">
            <span className={`status-led status-led--${dbTone}`} />
            <span>{dbLabel}</span>
          </span>
          <span className="status-cell-meta">
            SQLite · 비동기 세션
          </span>
        </div>

        <div className="status-cell">
          <span className="status-cell-label"><Sparkles size={12} strokeWidth={2.5} /> LLM 엔진</span>
          <span className="status-cell-value">
            <span className={`status-led status-led--${llmTone}`} />
            <span>{llmLabel}</span>
          </span>
          <span className="status-cell-meta">
            기본={primaryKo} · 폴백={fallbackKo}
          </span>
        </div>
      </div>
    </div>
  )
}

/* ---------- Pipeline Flow (process diagram) ---------- */

function PipelineFlow({ queues }) {
  const auxDepth = queues?.[AUX_STAGE.key]
  const auxBusy = (auxDepth ?? 0) > 0
  return (
    <div className="pipeline-wrap">
      <div className="pipeline-flow">
        {PIPELINE_STAGES.map((stage, idx) => {
          const depth = queues?.[stage.key]
          const known = depth != null
          const busy = (depth ?? 0) > 0
          return (
            <FragmentLike key={stage.key}>
              <div className={`pf-stage ${busy ? 'pf-stage--busy' : ''}`}>
                <div className="pf-stage-head">
                  <span className="pf-stage-idx mono">단계 {idx + 1}</span>
                  <span className="pf-stage-name">{stage.label}</span>
                </div>
                <div className="pf-stage-num mono">{known ? depth : '—'}</div>
                <div className="pf-stage-foot">
                  <span className={`pf-led ${busy ? 'pf-led--busy' : known ? 'pf-led--idle' : 'pf-led--unknown'}`} />
                  <span className="pf-stage-note mono">{stage.note}</span>
                </div>
              </div>
              {idx < PIPELINE_STAGES.length - 1 && (
                <div className={`pf-arrow ${busy ? 'pf-arrow--active' : ''}`}>
                  <ChevronRight size={20} strokeWidth={2} />
                </div>
              )}
            </FragmentLike>
          )
        })}
      </div>
      <div className={`pf-aux ${auxBusy ? 'pf-aux--busy' : ''}`}>
        <span className="pf-aux-tag mono">aux</span>
        <span className="pf-aux-name">{AUX_STAGE.label}</span>
        <span className="pf-aux-num mono">{auxDepth != null ? auxDepth : '—'}</span>
        <span className="pf-aux-note mono">{AUX_STAGE.note}</span>
      </div>
    </div>
  )
}

function FragmentLike({ children }) { return <>{children}</> }

/* ---------- KPI tile (dominant numbers) ---------- */

function KpiTile({ label, value, tone = 'indigo', mono = true }) {
  return (
    <div className={`kpi-tile kpi-tile--${tone}`}>
      <div className="kpi-tile-label">{label}</div>
      <div className={`kpi-tile-value ${mono ? 'mono' : ''}`}>
        {typeof value === 'number' ? formatNumber(value) : value}
      </div>
      <div className="kpi-tile-bar" />
    </div>
  )
}

/* ---------- Failure Surface ---------- */

function FailureSurface({ apiCalls }) {
  const failures = Object.entries(apiCalls || {})
    .map(([type, events]) => {
      const sent = events.SENT ?? 0
      const ok = events.SUCCESS ?? events.RESPONSE_OK ?? 0
      const failed = events.FAILED ?? 0
      const total = ok + failed
      const failRate = total > 0 ? (failed / total) * 100 : 0
      return { type, failed, sent, ok, failRate }
    })
    .filter(r => r.failed > 0)
    .sort((a, b) => b.failed - a.failed)

  if (failures.length === 0) {
    return (
      <div className="failure-empty">
        <AlertTriangle size={16} strokeWidth={2} />
        <span>현재 기록된 외부 API 실패 없음</span>
      </div>
    )
  }
  const max = Math.max(...failures.map(r => r.failed))
  return (
    <div className="failure-list">
      {failures.map(r => {
        const pct = max > 0 ? Math.round((r.failed / max) * 100) : 0
        const tone = r.failRate >= 20 ? 'red' : r.failRate >= 5 ? 'amber' : 'muted'
        return (
          <div key={r.type} className="failure-row">
            <div className="failure-row-head">
              <span className="failure-type mono">{r.type}</span>
              <span className={`failure-count mono tone-${tone}`}>×{r.failed}</span>
            </div>
            <div className="failure-track">
              <div className={`failure-fill failure-fill--${tone}`} style={{ width: `${pct}%` }} />
            </div>
            <div className="failure-meta mono small muted">
              실패율 {r.failRate.toFixed(1)}% · 총 {r.sent} 건
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ---------- Bars ---------- */

function ForecastBars({ forecast }) {
  const total = (forecast.RISING ?? 0) + (forecast.STEADY ?? 0) + (forecast.FALLING ?? 0)
  if (total === 0) return <Empty>아직 검색 기록 없음</Empty>
  const order = ['RISING', 'STEADY', 'FALLING']
  return (
    <div className="bars">
      {order.map(k => {
        const v = forecast[k] ?? 0
        const pct = total ? Math.round((v / total) * 100) : 0
        const Icon = FORECAST_ICON[k]
        return (
          <div key={k} className="bar-row">
            <div className={`bar-label tone-${FORECAST_TONE[k]}`}>
              <Icon size={14} strokeWidth={2.25} />
              <span>{FORECAST_LABEL[k]}</span>
            </div>
            <div className="bar-track">
              <div className={`bar-fill bar-fill--${FORECAST_TONE[k] === 'muted' ? 'muted' : FORECAST_TONE[k]}`} style={{ width: `${pct}%` }} />
            </div>
            <div className="bar-value mono">{v} ({pct}%)</div>
          </div>
        )
      })}
    </div>
  )
}

function BucketBars({ buckets }) {
  const order = ['under_10k', '10k_100k', '100k_1m', 'over_1m']
  const total = order.reduce((a, k) => a + (buckets[k] ?? 0), 0)
  if (total === 0) return <Empty>아직 검색 기록 없음</Empty>
  return (
    <div className="bars">
      {order.map(k => {
        const v = buckets[k] ?? 0
        const pct = total ? Math.round((v / total) * 100) : 0
        return (
          <div key={k} className="bar-row">
            <div className="bar-label">{PRICE_BUCKET_LABEL[k]}</div>
            <div className="bar-track">
              <div className="bar-fill bar-fill--accent" style={{ width: `${pct}%` }} />
            </div>
            <div className="bar-value mono">{v} ({pct}%)</div>
          </div>
        )
      })}
    </div>
  )
}

/* ---------- Top queries ---------- */

function TopQueries({ items, onOpenSearch, stats }) {
  if (!items || items.length === 0) return <Empty>검색 기록 없음</Empty>
  const idByNormalized = {}
  for (const r of (stats || [])) {
    if (!idByNormalized[r.query]) idByNormalized[r.query] = r.id
  }
  return (
    <div className="top-queries">
      {items.map(t => (
        <button
          key={t.normalizedQuery}
          className="top-query-row"
          onClick={() => {
            const id = idByNormalized[t.lastQuery]
            if (id) onOpenSearch?.(id)
          }}
          type="button"
        >
          <span className="top-query-text">{t.lastQuery}</span>
          <span className="top-query-count mono">×{t.count}</span>
          <ArrowRight size={14} strokeWidth={2} className="muted" />
        </button>
      ))}
    </div>
  )
}

/* ---------- API calls table ---------- */

function ApiCallsTable({ apiCalls }) {
  const entries = Object.entries(apiCalls || {})
  if (entries.length === 0) return <Empty>외부 API 호출 기록 없음</Empty>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>API</th>
            <th className="num">발송</th>
            <th className="num">성공</th>
            <th className="num">실패</th>
            <th className="num">성공률</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([type, events]) => {
            const sent = events.SENT ?? 0
            const ok = events.SUCCESS ?? events.RESPONSE_OK ?? 0
            const failed = events.FAILED ?? 0
            const total = ok + failed
            const successRate = total > 0 ? Math.round((ok / total) * 100) : null
            const successTone = successRate == null ? 'muted'
              : successRate >= 95 ? 'green'
              : successRate >= 80 ? 'amber'
              : 'red'
            return (
              <tr key={type}>
                <td><span className="status-pill tone-violet mono">{type}</span></td>
                <td className="num mono">{sent}</td>
                <td className="num mono tone-green">{ok}</td>
                <td className={`num mono ${failed > 0 ? 'tone-red' : 'tone-muted'}`}>{failed}</td>
                <td className={`num mono tone-${successTone}`}>{successRate != null ? `${successRate}%` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ---------- Recent search table (operation log) ---------- */

function RecentSearchTable({ rows, onOpen }) {
  if (!rows || rows.length === 0) return <Empty>검색 기록 없음. 분석 페이지에서 시작해보세요.</Empty>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>검색어</th>
            <th className="num">건수</th>
            <th className="num">중앙가</th>
            <th>키워드 트렌드</th>
            <th>LLM 예측</th>
            <th className="num">시각</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const TrendI = TREND_ICON[r.keywordTrendLabel] ?? Minus
            const trendTone = TREND_TONE[r.keywordTrendLabel] ?? 'muted'
            const FI = FORECAST_ICON[r.trendForecast] ?? Minus
            const ftone = FORECAST_TONE[r.trendForecast] ?? 'muted'
            return (
              <tr key={r.id} className="row-clickable" onClick={() => onOpen?.(r.id)}>
                <td className="id-cell">#{String(r.id).padStart(4, '0')}</td>
                <td className="title-cell" title={r.query}>{r.query}</td>
                <td className="num mono">{r.resultsCount}</td>
                <td className="num mono">{r.medianPrice ? `${r.medianPrice.toLocaleString('ko-KR')}원` : '—'}</td>
                <td>
                  {r.keywordTrendLabel ? (
                    <span className={`status-pill tone-${trendTone}`}>
                      <TrendI size={12} strokeWidth={2.5} />
                      {r.keywordTrendLabel}
                      {r.keywordChangePercent != null && (
                        <span className="mono small">
                          {' '}{r.keywordChangePercent >= 0 ? '+' : ''}{r.keywordChangePercent.toFixed(1)}%
                        </span>
                      )}
                    </span>
                  ) : <span className="muted small">—</span>}
                </td>
                <td>
                  {r.trendForecast ? (
                    <span className={`status-pill tone-${ftone}`}>
                      <FI size={12} strokeWidth={2.5} />
                      {FORECAST_LABEL[r.trendForecast] ?? r.trendForecast}
                    </span>
                  ) : <span className="muted small">—</span>}
                </td>
                <td className="num mono small muted">{formatTime(r.createdAt)}</td>
                <td><ArrowRight size={14} strokeWidth={2} className="muted" /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ---------- Section / Trend / Empty (shared utilities) ---------- */

function Section({ title, subtitle, icon: Icon, children }) {
  return (
    <section className="section">
      <div className="section-head">
        <div className="section-title">
          {Icon && <Icon size={13} strokeWidth={2.25} className="section-icon" />}
          <h2>{title}</h2>
        </div>
        {subtitle && <span className="muted small">{subtitle}</span>}
      </div>
      {children}
    </section>
  )
}

function Subsection({ title, subtitle, icon: Icon, children }) {
  return (
    <div className="subsection">
      <div className="subsection-head">
        <div className="subsection-title">
          {Icon && <Icon size={12} strokeWidth={2.5} className="section-icon" />}
          <h3>{title}</h3>
        </div>
        {subtitle && <span className="muted small mono">{subtitle}</span>}
      </div>
      {children}
    </div>
  )
}

function TrendsRow({ trends }) {
  const entries = Object.entries(trends ?? {})
  if (entries.length === 0) return <Empty>트렌드 데이터 없음 (DataLab 키 또는 최초 수집 대기)</Empty>
  return (
    <div className="trend-grid">
      {entries.map(([cat, t]) => {
        const Icon = TREND_ICON[t.label] ?? Minus
        const tone = TREND_TONE[t.label] ?? 'muted'
        return (
          <div key={cat} className="trend-card">
            <div className="muted small mono">{cat}</div>
            <div className={`trend-line tone-${tone}`}>
              <Icon size={16} strokeWidth={2.25} />
              <span className="trend-pct mono">
                {t.changePercent >= 0 ? '+' : ''}{t.changePercent?.toFixed(1)}%
              </span>
            </div>
            <div className="muted small">{t.label}</div>
          </div>
        )
      })}
    </div>
  )
}

function Empty({ children }) {
  return <div className="empty">{children}</div>
}
