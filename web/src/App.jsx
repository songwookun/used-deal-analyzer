import { useEffect, useState, useCallback } from 'react'
import {
  Search as SearchIcon,
  LayoutDashboard,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Minus,
  History,
  Globe,
  ArrowRight,
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

function formatNumber(n) { return (n ?? 0).toLocaleString('ko-KR') }
function formatPrice(n) { if (n == null) return '—'; return n.toLocaleString('ko-KR') + '원' }
function formatTime(iso) { if (!iso) return '—'; return new Date(iso).toLocaleTimeString('ko-KR', { hour12: false }) }

export default function App() {
  const [view, setView] = useState('search')
  // 대시보드에서 최근 검색 클릭 시 검색 페이지로 이동하면서 그 검색을 자동 로드
  const [pendingSearchId, setPendingSearchId] = useState(null)

  function openSearch(id) {
    setPendingSearchId(id)
    setView('search')
  }

  return (
    <div className="layout">
      <Sidebar view={view} onChange={setView} />
      <main className="main">
        {view === 'search'
          ? <SearchPage
              autoLoadId={pendingSearchId}
              onConsumeAutoLoad={() => setPendingSearchId(null)}
            />
          : <Dashboard onOpenSearch={openSearch} />
        }
      </main>
    </div>
  )
}

function Sidebar({ view, onChange }) {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const tick = async () => {
      try {
        const r = await fetch(`${API}/health/ready`)
        setHealth({ ok: r.ok, body: await r.json() })
      } catch { setHealth(null) }
    }
    tick()
    const t = setInterval(tick, 5000)
    return () => clearInterval(t)
  }, [])

  const ok = health?.ok && health?.body?.status === 'ok'
  const dot = !health ? 'red' : ok ? 'green' : 'amber'
  const label = !health ? 'unreachable' : ok ? 'All systems normal' : 'Degraded'

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">
          <Sparkles size={16} strokeWidth={2.25} />
        </div>
        <div className="brand-text">
          <div className="brand-name">쇼핑 분석</div>
          <div className="brand-sub">RAG · DataLab · LLM</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <NavItem
          icon={SearchIcon}
          active={view === 'search'}
          onClick={() => onChange('search')}
        >
          검색
        </NavItem>
        <NavItem
          icon={LayoutDashboard}
          active={view === 'dashboard'}
          onClick={() => onChange('dashboard')}
        >
          대시보드
        </NavItem>
      </nav>

      <div className="sidebar-foot">
        <div className="status-card">
          <div className="status-row">
            <span className={`dot dot--${dot}`} />
            <span className="status-label">{label}</span>
          </div>
          {health?.body?.components && (
            <div className="status-detail muted small">
              {Object.entries(health.body.components.workers || {}).filter(([, v]) => v === 'alive').length}/
              {Object.keys(health.body.components.workers || {}).length} workers alive
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
      <Icon size={16} strokeWidth={2} />
      <span>{children}</span>
    </button>
  )
}

function Dashboard({ onOpenSearch }) {
  const [stats, setStats] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const s = await fetch(`${API}/api/stats?recent=10`).then(r => r.json())
      setStats(s)
    } catch {}
  }, [])

  useEffect(() => {
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

  // 상위 1개 가격대 buckets 라벨 찾기
  const topBucket = Object.entries(buckets).sort((a, b) => b[1] - a[1])[0]
  const topBucketLabel = topBucket && topBucket[1] > 0 ? PRICE_BUCKET_LABEL[topBucket[0]] : '—'

  return (
    <>
      <PageHeader
        title="대시보드"
        subtitle="검색 누적 통계 · 카테고리 트렌드 · 외부 API 호출 현황"
      />

      <Section title="검색 통계">
        <div className="tiles">
          <StatTile icon={SearchIcon} tone="muted" label="누적 검색" value={totalSearches} />
          <StatTile icon={History} tone="amber" label="오늘 검색" value={todaySearches} />
          <StatTile icon={TrendingUp} tone="green" label="상승 예측 키워드" value={forecast.RISING ?? 0} />
          <StatTile icon={Sparkles} tone="muted" label="주요 가격대" value={topBucketLabel} mono={false} />
        </div>
      </Section>

      <div className="grid-2">
        <Section title="LLM 트렌드 예측 분포" subtitle="과거 검색의 LLM 평가 누적">
          <ForecastBars forecast={forecast} />
        </Section>

        <Section title="가격대 분포" subtitle="검색된 상품 중앙가 기준">
          <BucketBars buckets={buckets} />
        </Section>
      </div>

      <Section title="카테고리 트렌드" subtitle="네이버 데이터랩 (최근 7일 vs 이전 7일)">
        <TrendsRow trends={s.categoryTrends} />
      </Section>

      <Section title="인기 검색어" subtitle="동일 키워드 검색 빈도 top 10">
        <TopQueries items={s.topQueries} onOpenSearch={onOpenSearch} stats={s.recent} />
      </Section>

      <Section title="외부 API 호출" subtitle="apiType별 SENT / RESPONSE_OK / FAILED" icon={Globe}>
        <ApiCallsTable apiCalls={s.apiCalls} />
      </Section>

      <Section title="최근 검색" subtitle="클릭 시 저장된 분석 즉시 로드">
        <RecentSearchTable rows={s.recent} onOpen={onOpenSearch} />
      </Section>

      <footer className="footer">
        <span className="muted small">auto-refresh {POLL_MS / 1000}s</span>
        <span className="muted small">·</span>
        <span className="muted small">{s.asOf ? `as of ${formatTime(s.asOf)}` : 'loading...'}</span>
      </footer>
    </>
  )
}

function StatTile({ icon: Icon, tone, label, value, mono = true }) {
  return (
    <div className="tile">
      <div className={`tile-icon tone-${tone}`}><Icon size={16} strokeWidth={2} /></div>
      <div className="tile-body">
        <div className="tile-label">{label}</div>
        <div className={`tile-value ${mono ? 'mono' : ''}`}>
          {typeof value === 'number' ? formatNumber(value) : value}
        </div>
      </div>
    </div>
  )
}

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
              <Icon size={14} strokeWidth={2} />
              <span>{FORECAST_LABEL[k]}</span>
            </div>
            <div className="bar-track">
              <div className={`bar-fill bar-fill--${FORECAST_TONE[k]}`} style={{ width: `${pct}%` }} />
            </div>
            <div className="bar-value mono small">{v} ({pct}%)</div>
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
              <div className="bar-fill bar-fill--muted" style={{ width: `${pct}%` }} />
            </div>
            <div className="bar-value mono small">{v} ({pct}%)</div>
          </div>
        )
      })}
    </div>
  )
}

function TopQueries({ items, onOpenSearch, stats }) {
  if (!items || items.length === 0) return <Empty>검색 기록 없음</Empty>
  // recent에서 normalizedQuery로 가장 최근 id 매핑 — 클릭 시 그 id로 로드
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
          <span className="muted small mono">×{t.count}</span>
          <ArrowRight size={14} strokeWidth={2} className="muted" />
        </button>
      ))}
    </div>
  )
}

function ApiCallsTable({ apiCalls }) {
  const entries = Object.entries(apiCalls || {})
  if (entries.length === 0) return <Empty>외부 API 호출 기록 없음</Empty>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>API</th>
            <th className="num">SENT</th>
            <th className="num">SUCCESS</th>
            <th className="num">FAILED</th>
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
            return (
              <tr key={type}>
                <td><span className="status-pill tone-muted">{type}</span></td>
                <td className="num mono">{sent}</td>
                <td className="num mono tone-green">{ok}</td>
                <td className={`num mono ${failed > 0 ? 'tone-red' : ''}`}>{failed}</td>
                <td className="num mono">{successRate != null ? `${successRate}%` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function RecentSearchTable({ rows, onOpen }) {
  if (!rows || rows.length === 0) return <Empty>검색 기록 없음. 검색 페이지에서 시작해보세요.</Empty>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>검색어</th>
            <th className="num">상품 수</th>
            <th className="num">중앙가</th>
            <th>키워드 트렌드</th>
            <th>LLM 예측</th>
            <th>시각</th>
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
                <td className="title-cell" title={r.query}>{r.query}</td>
                <td className="num mono">{r.resultsCount}</td>
                <td className="num mono">{r.medianPrice ? `${r.medianPrice.toLocaleString('ko-KR')}원` : '—'}</td>
                <td>
                  {r.keywordTrendLabel ? (
                    <span className={`status-pill tone-${trendTone}`}>
                      <TrendI size={12} strokeWidth={2.25} />
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
                      <FI size={12} strokeWidth={2.25} />
                      {FORECAST_LABEL[r.trendForecast] ?? r.trendForecast}
                    </span>
                  ) : <span className="muted small">—</span>}
                </td>
                <td className="muted small">{formatTime(r.createdAt)}</td>
                <td><ArrowRight size={14} strokeWidth={2} className="muted" /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function PageHeader({ title, subtitle }) {
  return (
    <div className="page-header">
      <h1>{title}</h1>
      {subtitle && <p className="muted">{subtitle}</p>}
    </div>
  )
}

function Section({ title, subtitle, icon: Icon, children }) {
  return (
    <section className="section">
      <div className="section-head">
        <div className="section-title">
          {Icon && <Icon size={14} strokeWidth={2} className="section-icon" />}
          <h2>{title}</h2>
        </div>
        {subtitle && <span className="muted small">{subtitle}</span>}
      </div>
      {children}
    </section>
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
            <div className="muted small">{cat}</div>
            <div className={`trend-line tone-${tone}`}>
              <Icon size={16} strokeWidth={2} />
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
