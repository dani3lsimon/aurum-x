'use client'
import { useState, useEffect } from 'react'
import UpdateBadge from './UpdateBadge'

const BACKEND    = process.env.NEXT_PUBLIC_BACKEND_URL || ''
const REFRESH_MS = 30_000

const STATUS_CONFIG: Record<string, { color: string; label: string; bg: string }> = {
  OPEN:    { color: '#ffb347', label: 'OPEN',    bg: 'rgba(255,179,71,0.1)' },
  TP1_HIT: { color: '#22c55e', label: 'TP1 ✓',  bg: 'rgba(34,197,94,0.08)' },
  TP2_HIT: { color: '#22c55e', label: 'TP2 ✓✓', bg: 'rgba(34,197,94,0.1)'  },
  CLOSED:  { color: '#6b7494', label: 'CLOSED',  bg: 'rgba(107,116,148,0.08)' },
  EXPIRED: { color: '#4a5068', label: 'EXPIRED', bg: 'rgba(74,80,104,0.08)' },
}

const RESULT_CONFIG: Record<string, { color: string; label: string }> = {
  TP3:            { color: '#22c55e', label: '✓ TP3 FULL' },
  TP2:            { color: '#22c55e', label: '✓ TP2' },
  TP1:            { color: '#60a5fa', label: '✓ TP1' },
  STOPPED:        { color: '#ef4444', label: '✗ STOPPED' },
  EXPIRED_PROFIT: { color: '#22c55e', label: '~ EXP +' },
  EXPIRED_LOSS:   { color: '#ef4444', label: '~ EXP −' },
}

// Row tint by outcome (subtle, behind direction border)
function rowTint(s: any): string {
  if (s.status === 'OPEN') return 'rgba(255,179,71,0.04)'
  const oc = (s.outcome_class || '').toUpperCase()
  const rl = (s.result_label  || '').toUpperCase()
  if (oc === 'WIN'  || ['TP1','TP2','TP3','EXPIRED_PROFIT'].includes(rl)) return 'rgba(34,197,94,0.04)'
  if (oc === 'LOSS' || ['STOPPED','EXPIRED_LOSS'].includes(rl))           return 'rgba(239,68,68,0.04)'
  return 'rgba(255,255,255,0.01)'
}

// Source badge color by outcome
function badgeColor(s: any): { border: string; color: string } {
  if (s.status === 'OPEN') return { border: '#ffb347', color: '#ffb347' }
  const oc = (s.outcome_class || '').toUpperCase()
  const rl = (s.result_label  || '').toUpperCase()
  if (oc === 'WIN'  || ['TP1','TP2','TP3','EXPIRED_PROFIT'].includes(rl)) return { border: '#22c55e', color: '#22c55e' }
  if (oc === 'LOSS' || ['STOPPED','EXPIRED_LOSS'].includes(rl))           return { border: '#ef4444', color: '#ef4444' }
  return { border: '#2a2d3a', color: '#4a5068' }
}

// Match condition filter to a signal row
function conditionMatches(s: any, condFilter: string): boolean {
  if (!condFilter) return true
  const [condName, condValue] = condFilter.split('::')
  const snap       = s.conditions_snapshot || {}
  const conditions = snap.conditions || {}
  const cond       = conditions[condName]
  if (!cond) return false
  if (String(cond.value) !== condValue) return false
  return s.direction === 'long' ? !!cond.long_met : !!cond.short_met
}

export function SignalJournal({
  livePrice,
  equityPoints,
}: {
  livePrice:     number
  equityPoints?: { signal_id: string; equity: number }[]
}) {
  const [signals,     setSignals]     = useState<any[]>([])
  const [stats,       setStats]       = useState<any>(null)
  const [condStats,   setCondStats]   = useState<{ condition: string; value: string }[]>([])
  const [filter,      setFilter]      = useState<'all'|'15min'|'1h'|'4h'>('all')
  const [condFilter,  setCondFilter]  = useState<string>('')
  const [loading,     setLoading]     = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  // Build equity map for the EQUITY column
  const equityMap = new Map<string, number>()
  for (const p of equityPoints || []) {
    equityMap.set(p.signal_id, p.equity)
  }

  const fetchData = async () => {
    try {
      const [sigs, st, cs] = await Promise.all([
        fetch(`${BACKEND}/forecast/signal-history?limit=200${filter !== 'all' ? `&timeframe=${filter}` : ''}`).then(r => r.json()),
        fetch(`${BACKEND}/forecast/signal-history/stats`).then(r => r.json()),
        fetch(`${BACKEND}/forecast/signal-history/condition-stats`).then(r => r.json()),
      ])
      setSignals(Array.isArray(sigs) ? sigs : [])
      setStats(st)
      if (Array.isArray(cs)) setCondStats(cs.map((r: any) => ({ condition: r.condition, value: r.value })))
      setLastUpdated(new Date())
    } catch {}
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [filter])
  useEffect(() => {
    const interval = setInterval(fetchData, REFRESH_MS)
    return () => clearInterval(interval)
  }, [filter])

  const fmtPrice = (p: number | null) =>
    p ? `$${p.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'

  const fmtTime = (iso: string | null) => {
    if (!iso) return '—'
    const d = new Date(iso)
    return `${d.toLocaleDateString('en-GB', { day:'2-digit', month:'short' })} ${d.toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' })}`
  }

  const displayedSignals = signals.filter(s => conditionMatches(s, condFilter))

  // Distinct (condition, value) pairs for dropdown
  const condOptions = condStats.map(c => ({ key: `${c.condition}::${c.value}`, label: `${c.condition.toUpperCase()}: ${c.value}` }))

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: '10px', overflow: 'hidden', padding: '12px 16px' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.16em', color: '#ff7744' }}>
          ◆ SIGNAL JOURNAL
        </span>
        <UpdateBadge lastUpdated={lastUpdated} intervalMs={REFRESH_MS} label="SUPABASE" />
      </div>

      {/* Summary stats */}
      {stats && stats.total > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '6px', flexShrink: 0 }}>
          {[
            { label: 'TOTAL',         value: stats.total,              color: '#ff7744' },
            { label: 'WIN RATE',      value: `${stats.win_pct}%`,      color: stats.win_pct > 50 ? '#22c55e' : '#ef4444' },
            { label: 'TP1 RATE',      value: `${stats.tp1_hit_pct}%`,  color: '#22c55e' },
            { label: 'TP2 RATE',      value: `${stats.tp2_hit_pct}%`,  color: '#22c55e' },
            { label: 'TP3 RATE',      value: `${stats.tp3_hit_pct}%`,  color: '#22c55e' },
            { label: 'PNL PTS',       value: `${stats.total_pnl_pts > 0 ? '+' : ''}${stats.total_pnl_pts}`, color: stats.total_pnl_pts > 0 ? '#22c55e' : '#ef4444' },
            { label: 'AVG R',         value: `${stats.avg_r >= 0 ? '+' : ''}${(stats.avg_r ?? 0).toFixed(3)}R`, color: stats.avg_r > 0 ? '#22c55e' : '#ef4444' },
            { label: 'PROFIT FACTOR', value: stats.profit_factor_r,   color: stats.profit_factor_r > 1.5 ? '#22c55e' : '#ffb347' },
          ].map(s => (
            <div key={s.label} className="aurum-card" style={{ padding: '10px', textAlign: 'center' }}>
              <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.12em', marginBottom: '3px' }}>{s.label}</div>
              <div style={{ fontSize: '17px', fontWeight: 800, color: s.color }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Per-timeframe */}
      {stats?.by_timeframe && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', flexShrink: 0 }}>
          {(['15min','1h','4h'] as const).map(tf => {
            const t = stats.by_timeframe[tf]
            return (
              <div key={tf} className="aurum-card" style={{ padding: '8px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '13px', fontWeight: 700, color: '#ff7744' }}>{tf.toUpperCase()}</span>
                <span style={{ fontSize: '11px', color: '#6b7494' }}>{t?.total ?? 0} signals</span>
                <span style={{ fontSize: '13px', fontWeight: 700, color: (t?.win_pct ?? 0) > 50 ? '#22c55e' : '#ef4444' }}>
                  {t?.win_pct ?? 0}% WIN
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Filter row */}
      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', flexShrink: 0 }}>
        {/* Strategy filter — placeholder, single option */}
        <span style={{ padding: '5px 12px', fontSize: '10px', letterSpacing: '0.1em', background: 'rgba(255,80,0,0.08)', color: '#ff7744', border: '1px solid rgba(255,80,0,0.2)', fontFamily: 'JetBrains Mono, monospace', opacity: 0.7 }}>
          AURUM-X
        </span>

        {/* Timeframe filters */}
        {(['all','15min','1h','4h'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: '5px 12px', fontSize: '11px', letterSpacing: '0.12em',
            background: filter === f ? '#ff5500' : 'transparent',
            color:      filter === f ? '#000' : '#4a5068',
            border:     '1px solid rgba(255,80,0,0.2)', cursor: 'pointer',
            fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase',
          }}>
            {f === 'all' ? 'ALL TF' : f.toUpperCase()}
          </button>
        ))}

        {/* Condition filter dropdown */}
        <select value={condFilter} onChange={e => setCondFilter(e.target.value)} style={{
          padding: '5px 10px', fontSize: '10px', letterSpacing: '0.1em',
          background: '#0d0f17', color: condFilter ? '#ff7744' : '#4a5068',
          border: '1px solid rgba(255,80,0,0.2)', cursor: 'pointer',
          fontFamily: 'JetBrains Mono, monospace', outline: 'none',
        }}>
          <option value="">ALL CONDITIONS</option>
          {condOptions.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>

        <div style={{ flex: 1 }} />
        <a
          href={`${BACKEND}/forecast/signal-history/export.csv${filter !== 'all' ? `?timeframe=${filter}` : ''}`}
          download
          style={{ fontSize: '11px', padding: '5px 10px', border: '1px solid rgba(255,80,0,0.2)', color: '#8a92ab', textDecoration: 'none', fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer' }}
        >
          ⬇ CSV
        </a>
        <button onClick={fetchData} style={{ padding: '5px 12px', fontSize: '11px', background: 'transparent', border: '1px solid rgba(255,80,0,0.2)', color: '#4a5068', cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace' }}>
          ⟳ REFRESH
        </button>
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 2px', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase' }}>
          <thead>
            <tr style={{ fontSize: '9px', color: '#2a2d3a', letterSpacing: '0.12em' }}>
              {['TIME','TF','SRC','DIR','CONV','ENTRY','STOP','TP1','TP2','TP3','STATUS','RESULT','PNL PTS','EQUITY','EDGE','DUR'].map(h => (
                <th key={h} style={{ padding: '5px 8px', textAlign: 'left', fontWeight: 400, borderBottom: '1px solid rgba(255,80,0,0.08)', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayedSignals.map(s => {
              const statusCfg  = STATUS_CONFIG[s.status] || STATUS_CONFIG.CLOSED
              const resultCfg  = s.result_label ? (RESULT_CONFIG[s.result_label] || { color: '#6b7494', label: s.result_label }) : null
              const isOpen     = s.status === 'OPEN'
              const isLong     = s.direction === 'long'
              const badge      = badgeColor(s)

              const livePnl = isOpen && livePrice && s.entry_price
                ? (isLong ? livePrice - s.entry_price : s.entry_price - livePrice).toFixed(2)
                : null

              const entryMs  = new Date(s.entry_time).getTime()
              const closeMs  = s.closed_time ? new Date(s.closed_time).getTime() : Date.now()
              const durH     = ((closeMs - entryMs) / 3_600_000).toFixed(1)

              const equityVal = equityMap.get(s.signal_id)

              return (
                <tr key={s.id} style={{
                  background:  rowTint(s),
                  borderLeft:  `3px solid ${isLong ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                }}>
                  <td style={{ padding: '7px 8px', color: '#6b7494', whiteSpace: 'nowrap' }}>{fmtTime(s.entry_time)}</td>
                  <td style={{ padding: '7px 8px', fontWeight: 700, color: '#ff7744' }}>{s.timeframe}</td>
                  {/* Source badge */}
                  <td style={{ padding: '7px 8px' }}>
                    <span style={{ padding: '1px 6px', fontSize: '9px', border: `1px solid ${badge.border}40`, color: badge.color, letterSpacing: '0.08em' }}>
                      AURUM-X
                    </span>
                  </td>
                  <td style={{ padding: '7px 8px', fontWeight: 700, color: isLong ? '#22c55e' : '#ef4444' }}>
                    {isLong ? '▲ LONG' : '▼ SHORT'}
                  </td>
                  <td style={{ padding: '7px 8px', color: '#6b7494', fontSize: '10px' }}>{s.conviction?.replace(' CONVICTION','') ?? '—'}</td>
                  <td style={{ padding: '7px 8px', fontWeight: 700, color: '#ff7744' }}>{fmtPrice(s.entry_price)}</td>
                  <td style={{ padding: '7px 8px', color: '#ef4444' }}>{fmtPrice(s.stop_loss)}</td>
                  <td style={{ padding: '7px 8px', color: s.tp1_hit ? '#22c55e' : '#4a5068' }}>
                    {fmtPrice(s.tp1_price)}{s.tp1_hit ? ' ✓' : ''}
                  </td>
                  <td style={{ padding: '7px 8px', color: s.tp2_hit ? '#22c55e' : '#4a5068' }}>
                    {fmtPrice(s.tp2_price)}{s.tp2_hit ? ' ✓' : ''}
                  </td>
                  <td style={{ padding: '7px 8px', color: s.tp3_hit ? '#22c55e' : '#4a5068' }}>
                    {fmtPrice(s.tp3_price)}{s.tp3_hit ? ' ✓' : ''}
                  </td>
                  <td style={{ padding: '7px 8px' }}>
                    <span style={{ padding: '2px 6px', background: statusCfg.bg, color: statusCfg.color, border: `1px solid ${statusCfg.color}40`, fontSize: '9px', letterSpacing: '0.08em' }}>
                      {statusCfg.label}
                    </span>
                  </td>
                  <td style={{ padding: '7px 8px' }}>
                    {resultCfg
                      ? <span style={{ color: resultCfg.color, fontWeight: 700, fontSize: '10px' }}>{resultCfg.label}</span>
                      : isOpen
                      ? <span style={{ color: '#ffb347', fontSize: '10px' }}>LIVE</span>
                      : '—'}
                  </td>
                  <td style={{ padding: '7px 8px', fontWeight: 700, color: livePnl !== null ? (parseFloat(livePnl) >= 0 ? '#22c55e' : '#ef4444') : (parseFloat(s.realized_pnl_pts || 0) >= 0 ? '#22c55e' : '#ef4444') }}>
                    {livePnl !== null
                      ? `${parseFloat(livePnl) >= 0 ? '+' : ''}${livePnl} ~`
                      : s.realized_pnl_pts
                      ? `${parseFloat(s.realized_pnl_pts) >= 0 ? '+' : ''}${parseFloat(s.realized_pnl_pts).toFixed(2)}`
                      : '—'}
                  </td>
                  {/* Equity column */}
                  <td style={{ padding: '7px 8px', color: equityVal != null ? (equityVal >= 10000 ? '#22c55e' : '#ef4444') : '#2a2d3a', fontWeight: equityVal != null ? 700 : 400 }}>
                    {equityVal != null ? `$${equityVal.toLocaleString('en-US', { minimumFractionDigits: 0 })}` : '—'}
                  </td>
                  <td style={{ padding: '7px 8px', color: '#4a5068' }}>{s.edge_strength?.toFixed?.(1) ?? s.edge_strength ?? '—'}</td>
                  <td style={{ padding: '7px 8px', color: '#4a5068' }}>{durH}h</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!loading && displayedSignals.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px', fontSize: '11px', color: '#2a2d3a', letterSpacing: '0.14em' }}>
            {condFilter ? 'NO SIGNALS MATCH THIS CONDITION FILTER' : 'NO SIGNALS RECORDED YET'}
          </div>
        )}
      </div>
    </div>
  )
}
