import { useState, useEffect, useCallback } from 'react'
import {
  Search as SearchIcon,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Minus,
  ExternalLink,
  Clock,
  RefreshCw,
  AlertCircle,
  Brain,
  Layers,
} from 'lucide-react'

const API = import.meta.env.VITE_API ?? 'http://localhost:8000'

const FORECAST_TONE = { RISING: 'green', STEADY: 'muted', FALLING: 'red' }
const FORECAST_LABEL = { RISING: '상승 예상', STEADY: '안정', FALLING: '하락 예상' }
const FORECAST_ICON = { RISING: TrendingUp, STEADY: Minus, FALLING: TrendingDown }
const TREND_TONE = { 급상승: 'green', 안정: 'muted', 하락: 'red' }
const TREND_ICON = { 급상승: TrendingUp, 안정: Minus, 하락: TrendingDown }

function formatPrice(n) {
  if (n == null) return '—'
  return n.toLocaleString('ko-KR') + '원'
}

export default function SearchPage({ autoLoadId, onConsumeAutoLoad }) {
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [recent, setRecent] = useState([])

  const refreshRecent = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/search/recent?limit=8`).then(r => r.json())
      setRecent(Array.isArray(r) ? r : [])
    } catch {
      setRecent([])
    }
  }, [])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { refreshRecent() }, [refreshRecent])

  // 대시보드에서 진입 시 해당 검색 자동 로드
  useEffect(() => {
    if (autoLoadId) {
      const found = recent.find(r => r.id === autoLoadId)
      const query = found?.query ?? ''
      loadCached(autoLoadId, query)
      onConsumeAutoLoad?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoadId, recent.length])

  async function runSearch(e) {
    e?.preventDefault?.()
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const url = `${API}/api/search?q=${encodeURIComponent(q.trim())}`
      const res = await fetch(url, { method: 'POST' })
      const body = await res.json()
      if (!res.ok) {
        setError(body?.detail ?? `에러 ${res.status}`)
      } else {
        setResult(body)
        refreshRecent()
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadCached(id, query) {
    setQ(query)
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(`${API}/api/search/${id}`)
      const body = await res.json()
      if (!res.ok) setError(body?.detail ?? `에러 ${res.status}`)
      else setResult(body)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <span className="crumb">분석 콘솔</span>
          <h1>키워드 분석</h1>
          <p>키워드 → 네이버 쇼핑 + 데이터랩 트렌드 + RAG 유사 검색 → LLM 종합 평가 파이프라인.</p>
        </div>
      </div>

      <form className="search-form" onSubmit={runSearch}>
        <div className="search-input-wrap">
          <SearchIcon size={16} className="search-input-icon" strokeWidth={2} />
          <input
            className="search-input"
            placeholder="분석할 키워드를 입력하세요 (예: 갤럭시 버즈 프로 2)"
            value={q}
            onChange={e => setQ(e.target.value)}
            disabled={loading}
            autoFocus
          />
        </div>
        <button className="btn primary" type="submit" disabled={loading || !q.trim()}>
          <Sparkles size={14} strokeWidth={2.25} />
          {loading ? '분석 중…' : '분석 실행'}
        </button>
      </form>

      {recent.length > 0 && (
        <div className="recent-card">
          <div className="recent-label muted">
            <Clock size={11} strokeWidth={2.25} /> 최근 검색 · 클릭 시 저장된 결과 로드
          </div>
          <div className="recent-chips">
            {recent.map(r => (
              <button
                key={r.id}
                className="chip"
                onClick={() => loadCached(r.id, r.query)}
                type="button"
              >
                {r.query}
              </button>
            ))}
          </div>
        </div>
      )}

      {result?.cached && (
        <div className="cached-banner">
          <Clock size={14} strokeWidth={2} />
          <span>저장된 결과 · {result.cachedAt ? new Date(result.cachedAt).toLocaleString('ko-KR') : ''}</span>
          <button className="link-btn" onClick={runSearch} type="button">
            <RefreshCw size={12} strokeWidth={2.25} /> 파이프라인 재실행
          </button>
        </div>
      )}

      {error && (
        <div className="error-card">
          <AlertCircle size={16} strokeWidth={2} />
          <div>
            <div className="error-title">분석 실패</div>
            <div className="muted small mono">{typeof error === 'string' ? error : JSON.stringify(error)}</div>
          </div>
        </div>
      )}

      {loading && (
        <div className="loading-card">
          <div className="spinner" />
          <div>
            <div className="loading-card-text">파이프라인 실행 중…</div>
            <div className="muted small mono">네이버 쇼핑 · 데이터랩 · RAG · LLM (5–15초)</div>
          </div>
        </div>
      )}

      {result && <ResultStack data={result} />}
    </>
  )
}

function ResultStack({ data }) {
  const trend = data.trend || {}
  const stats = data.priceStats || {}
  const a = data.analysis || {}

  return (
    <div className="result-stack">
      <div className="result-hero">
        <div className="result-hero-crumb">분석 대상</div>
        <h2 className="hero-query">"{data.query}"</h2>
        <div className="result-hero-meta">
          <span>상품 <strong>{data.shopResultsTotal ?? 0}</strong>건</span>
          <span>·</span>
          <span>중앙가 <strong>{formatPrice(stats.median)}</strong></span>
          {stats.count != null && (
            <>
              <span>·</span>
              <span>표본 <strong>{stats.count}</strong>건</span>
            </>
          )}
        </div>
      </div>

      <Section title="LLM 종합 평가" icon={Brain}>
        <div className="verdict-card">
          <div className="verdict-label"><Sparkles size={11} strokeWidth={2.5} /> 추론 근거</div>
          <div className="verdict-text">{a.reason || '평가 본문 없음'}</div>
        </div>
        <div className="pill-grid">
          <Pill label="카테고리 위치">{a.categoryRank}</Pill>
          <Pill label="가성비 평가">{a.valueAssessment}</Pill>
          <Pill label="트렌드 예측">
            <ForecastBadge forecast={a.trendForecast} />
            {a.trendForecastReason && <div className="muted small reason-line">{a.trendForecastReason}</div>}
          </Pill>
        </div>
      </Section>

      <div className="grid-2">
        <Section title="키워드 트렌드" subtitle="네이버 데이터랩 · 14일">
          <TrendCard trend={trend} />
        </Section>

        <Section title="가격 분포" subtitle="검색된 상품 기준">
          <PriceStatGrid stats={stats} />
        </Section>
      </div>

      {a.alternatives && a.alternatives.length > 0 && (
        <Section title="대체품 추천" subtitle="LLM이 검색 결과에서 추출">
          <div className="alt-grid">
            {a.alternatives.map((alt, i) => (
              <div key={i} className="alt-card">
                <div className="alt-title" title={alt.title}>{alt.title}</div>
                <div className="alt-price mono">{formatPrice(alt.price)}</div>
                <div className="muted small">{alt.mallName || '판매처 미상'}</div>
                <div className="alt-why">{alt.why}</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {data.similarSearches && data.similarSearches.length > 0 && (
        <Section title="RAG 근거 자료" subtitle="과거 유사 검색 임베딩 매치" icon={Layers}>
          <div className="rag-evidence">
            <div className="rag-evidence-label">
              <Layers size={11} strokeWidth={2.5} /> 유사 검색 {data.similarSearches.length}건 매칭
            </div>
            <div className="similar-strip">
              {data.similarSearches.map((s, i) => (
                <div key={i} className="similar-chip">
                  <span>{s.query}</span>
                  <span className="score">유사도 {s.score.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      <Section
        title="검색 결과"
        subtitle={`${data.shopResultsTotal ?? 0}건 중 상위 ${(data.shopResults || []).length}`}
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>제품명</th>
                <th>판매처</th>
                <th>카테고리</th>
                <th className="num">가격</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(data.shopResults || []).map((it, i) => (
                <tr key={i}>
                  <td className="title-cell" title={it.title}>{it.title}</td>
                  <td className="muted small">{it.mallName}</td>
                  <td className="muted small">{it.category2 || it.category1}</td>
                  <td className="num mono">{formatPrice(it.price)}</td>
                  <td>
                    {it.link && (
                      <a href={it.link} target="_blank" rel="noopener noreferrer" className="ext-link">
                        <ExternalLink size={13} strokeWidth={2} />
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}

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

function Pill({ label, children }) {
  return (
    <div className="pill">
      <div className="pill-label">{label}</div>
      <div className="pill-value">{children}</div>
    </div>
  )
}

function ForecastBadge({ forecast }) {
  const Icon = FORECAST_ICON[forecast] ?? Minus
  const tone = FORECAST_TONE[forecast] ?? 'muted'
  return (
    <span className={`forecast-badge tone-${tone}`}>
      <Icon size={14} strokeWidth={2.25} />
      {FORECAST_LABEL[forecast] ?? forecast}
    </span>
  )
}

function TrendCard({ trend }) {
  if (!trend.label) return <Empty>데이터랩 트렌드 데이터 없음</Empty>
  const Icon = TREND_ICON[trend.label] ?? Minus
  const tone = TREND_TONE[trend.label] ?? 'muted'
  return (
    <div className="trend-block">
      <div className="trend-line-big">
        <span className={`tone-${tone} trend-icon-big`}><Icon size={20} strokeWidth={2.25} /></span>
        <span className={`trend-label-big tone-${tone}`}>{trend.label}</span>
        <span className={`trend-pct-big mono tone-${tone}`}>
          {trend.changePercent >= 0 ? '+' : ''}{trend.changePercent?.toFixed(1)}%
        </span>
      </div>
      <div className="muted small mono">최근 7일 평균 대비 이전 7일 평균</div>
      {trend.series && trend.series.length > 1 && <Sparkline series={trend.series} />}
    </div>
  )
}

function PriceStatGrid({ stats }) {
  return (
    <div className="price-grid">
      <Stat label="표본">{stats.count ?? 0}건</Stat>
      <Stat label="최저">{formatPrice(stats.min)}</Stat>
      <Stat label="중앙">{formatPrice(stats.median)}</Stat>
      <Stat label="최고">{formatPrice(stats.max)}</Stat>
    </div>
  )
}

function Stat({ label, children }) {
  return (
    <div className="stat-card">
      <div className="stat-card-label">{label}</div>
      <div className="stat-value mono">{children}</div>
    </div>
  )
}

function Sparkline({ series }) {
  if (!series || series.length < 2) return null
  const W = 600, H = 60, P = 4
  const ratios = series.map(s => s.ratio)
  const min = Math.min(...ratios)
  const max = Math.max(...ratios)
  const range = (max - min) || 1
  const stepX = (W - P * 2) / (series.length - 1)
  const points = series.map((s, i) => {
    const x = P + i * stepX
    const y = H - P - ((s.ratio - min) / range) * (H - P * 2)
    return { x, y }
  })
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
  const area = `${path} L ${points[points.length - 1].x} ${H - P} L ${P} ${H - P} Z`
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <path d={area} fill="currentColor" opacity="0.10" />
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

function Empty({ children }) {
  return <div className="empty">{children}</div>
}
