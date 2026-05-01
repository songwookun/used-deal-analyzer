import { useEffect, useState, useCallback } from 'react'
import './App.css'

const API = import.meta.env.VITE_API ?? 'http://localhost:8000'
const POLL_MS = 3000

const STATUS_ORDER = ['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'SKIPPED', 'TIMEOUT']
const STATUS_TONE = {
  PENDING: 'muted',
  PROCESSING: 'amber',
  COMPLETED: 'green',
  FAILED: 'red',
  SKIPPED: 'muted',
  TIMEOUT: 'red',
}

const TREND_ARROW = { '급상승': '↑', '안정': '→', '하락': '↓' }
const TREND_TONE = { '급상승': 'green', '안정': 'muted', '하락': 'red' }

function formatPrice(n) {
  if (n == null) return '—'
  return n.toLocaleString('ko-KR')
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleTimeString('ko-KR', { hour12: false })
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([
        fetch(`${API}/api/stats?recent=10`).then(r => r.json()),
        fetch(`${API}/health/ready`).then(async r => ({ ok: r.ok, body: await r.json() })),
      ])
      setStats(s)
      setHealth(h)
      setErr(null)
    } catch (e) {
      setErr(e.message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh])

  async function runPipeline(qs = '') {
    setRunning(true)
    try {
      await fetch(`${API}/api/test-pipeline${qs}`, { method: 'POST' })
      // 약간의 지연 후 갱신 (분석 끝나기 전 stats가 비어보일 수 있음)
      setTimeout(refresh, 500)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="page">
      <Header health={health} err={err} />

      <Toolbar running={running} onRun={runPipeline} />

      <Section title="Status">
        <StatusTiles counts={stats?.statusCounts} />
      </Section>

      <Section title="Trends" right={<TrendNote stats={stats} />}>
        <TrendsRow trends={stats?.trends} />
      </Section>

      <Section title="Failures" right={<MutedText>by reason</MutedText>}>
        <FailuresInline failures={stats?.failures} />
      </Section>

      <Section title="Recent items">
        <RecentTable rows={stats?.recent} />
      </Section>

      <footer className="footer">
        <span>auto-refresh {POLL_MS / 1000}s</span>
        <span>·</span>
        <span>{stats?.asOf ? `as of ${formatTime(stats.asOf)}` : '...'}</span>
      </footer>
    </div>
  )
}

function Header({ health, err }) {
  const ok = health?.ok && health?.body?.status === 'ok'
  const dot = err ? 'red' : ok ? 'green' : 'amber'
  const label = err ? 'unreachable' : ok ? 'ready' : 'degraded'
  return (
    <header className="header">
      <div className="brand">
        <span className={`dot dot--${dot}`} />
        <h1>Pipeline</h1>
        <span className="muted small">{label}</span>
      </div>
    </header>
  )
}

function Toolbar({ running, onRun }) {
  return (
    <div className="toolbar">
      <button className="btn primary" disabled={running} onClick={() => onRun()}>
        {running ? 'Queueing…' : 'Run normal item'}
      </button>
      <button className="btn" disabled={running} onClick={() => onRun('?seller=F')}>F seller (SKIP)</button>
      <button className="btn" disabled={running} onClick={() => onRun('?sold=true')}>Sold (SKIP)</button>
      <button className="btn" disabled={running} onClick={() => onRun('?over_price=true')}>Over price (SKIP)</button>
    </div>
  )
}

function Section({ title, right, children }) {
  return (
    <section className="section">
      <div className="section-head">
        <h2>{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

function StatusTiles({ counts }) {
  const c = counts ?? {}
  return (
    <div className="tiles">
      {STATUS_ORDER.map(s => (
        <div key={s} className="tile">
          <div className={`tile-label tone-${STATUS_TONE[s]}`}>{s}</div>
          <div className="tile-value mono">{c[s] ?? 0}</div>
        </div>
      ))}
    </div>
  )
}

function TrendNote({ stats }) {
  const n = stats?.trends ? Object.keys(stats.trends).length : 0
  if (n === 0) return <MutedText>비활성 (DataLab 키 없음 또는 갱신 전)</MutedText>
  return <MutedText>{n} categories · 최근 7일 vs 이전 7일</MutedText>
}

function TrendsRow({ trends }) {
  const entries = Object.entries(trends ?? {})
  if (entries.length === 0) {
    return <EmptyHint>트렌드 데이터 없음</EmptyHint>
  }
  return (
    <div className="trend-row">
      {entries.map(([cat, t]) => (
        <div key={cat} className="trend-card">
          <div className="trend-cat">{cat}</div>
          <div className={`trend-value tone-${TREND_TONE[t.label] ?? 'muted'}`}>
            <span className="trend-arrow">{TREND_ARROW[t.label] ?? '·'}</span>
            <span className="mono">{(t.changePercent >= 0 ? '+' : '') + t.changePercent.toFixed(1)}%</span>
          </div>
          <div className="trend-label muted small">{t.label}</div>
        </div>
      ))}
    </div>
  )
}

function FailuresInline({ failures }) {
  const byReason = failures?.byReason ?? {}
  const entries = Object.entries(byReason)
  if (entries.length === 0) return <EmptyHint>실패 매물 없음</EmptyHint>
  return (
    <div className="kv-row">
      {entries.map(([k, v]) => (
        <div key={k} className="kv">
          <span className="muted small">{k}</span>
          <span className="mono">{v}</span>
        </div>
      ))}
    </div>
  )
}

function RecentTable({ rows }) {
  if (!rows || rows.length === 0) return <EmptyHint>매물 없음</EmptyHint>
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>itemId</th>
            <th>title</th>
            <th>status</th>
            <th>category</th>
            <th className="num">asking</th>
            <th className="num">estimated</th>
            <th className="num">diff%</th>
            <th className="num">retry</th>
            <th>analyzedAt</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(it => (
            <tr key={it.itemId}>
              <td className="mono small">{it.itemId}</td>
              <td className="title-cell" title={it.title}>{it.title}</td>
              <td>
                <span className={`badge tone-${STATUS_TONE[it.status] ?? 'muted'}`}>
                  {it.status}
                </span>
                {it.failReason && <span className="muted small fail-reason">{it.failReason}</span>}
              </td>
              <td className="muted">{it.category}</td>
              <td className="num mono">{formatPrice(it.askingPrice)}</td>
              <td className="num mono">{formatPrice(it.estimatedPrice)}</td>
              <td className={`num mono ${diffTone(it.priceDiffPercent)}`}>
                {it.priceDiffPercent != null ? `${it.priceDiffPercent > 0 ? '+' : ''}${it.priceDiffPercent}%` : '—'}
              </td>
              <td className="num mono">{it.retryCount}</td>
              <td className="muted small">{formatTime(it.analyzedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function diffTone(pct) {
  if (pct == null) return ''
  if (pct <= -20) return 'tone-green'
  if (pct >= 20) return 'tone-red'
  return ''
}

function MutedText({ children }) {
  return <span className="muted small">{children}</span>
}

function EmptyHint({ children }) {
  return <div className="empty">{children}</div>
}
