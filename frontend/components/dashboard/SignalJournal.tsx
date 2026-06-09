'use client'
import { useState, useEffect } from 'react'
import UpdateBadge from './UpdateBadge'

const BACKEND    = process.env.NEXT_PUBLIC_BACKEND_URL || ''
const REFRESH_MS = 30_000

const STATUS_CONFIG: Record<string, { color: string; label: string; bg: string }> = {
  OPEN:           { color: '#ffb347', label: 'OPEN',    bg: 'rgba(255,179,71,0.1)' },
  TP1_HIT:        { color: '#22c55e', label: 'TP1 ✓',  bg: 'rgba(34,197,94,0.08)' },
  TP2_HIT:        { color: '#22c55e', label: 'TP2 ✓✓', bg: 'rgba(34,197,94,0.1)'  },
  CLOSED:         { color: '#6b7494', label: 'CLOSED',  bg: 'rgba(107,116,148,0.08)'},
  EXPIRED:        { color: '#4a5068', label: 'EXPIRED', bg: 'rgba(74,80,104,0.08)' },
}

const RESULT_CONFIG: Record<string, { color: string; label: string }> = {
  TP3:            { color: '#22c55e',  label: '✓ TP3 FULL' },
  TP2:            { color: '#22c55e',  label: '✓ TP2' },
  TP1:            { color: '#60a5fa',  label: '✓ TP1' },
  STOPPED:        { color: '#ef4444',  label: '✗ STOPPED' },
  EXPIRED_PROFIT: { color: '#22c55e',  label: '~ EXP +' },
  EXPIRED_LOSS:   { color: '#ef4444',  label: '~ EXP −' },
}

export function SignalJournal({ livePrice }: { livePrice: number }) {
  const [signals,     setSignals]     = useState<any[]>([])
  const [stats,       setStats]       = useState<any>(null)
  const [filter,      setFilter]      = useState<'all'|'15min'|'1h'|'4h'>('all')
  const [loading,     setLoading]     = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchData = async () => {
    try {
      const [sigs, st] = await Promise.all([
        fetch(`${BACKEND}/forecast/signal-history?limit=200${filter !== 'all' ? `&timeframe=${filter}` : ''}`).then(r => r.json()),
        fetch(`${BACKEND}/forecast/signal-history/stats`).then(r => r.json()),
      ])
      setSignals(Array.isArray(sigs) ? sigs : [])
      setStats(st)
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

  return (
    <div style={{ padding: '16px', height: 'calc(100vh - 110px)', display: 'flex', flexDirection: 'column', gap: '10px', overflow: 'hidden' }}>

      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.16em', color: '#ff7744' }}>
          ◆ SIGNAL JOURNAL
        </span>
        <UpdateBadge lastUpdated={lastUpdated} intervalMs={REFRESH_MS} label="SUPABASE" />
      </div>

      {/* Performance summary */}
      {stats && stats.total > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '6px' }}>
          {[
            { label: 'TOTAL SIGNALS',  value: stats.total,           color: '#ff7744' },
            { label: 'WIN RATE',       value: `${stats.win_pct}%`,   color: stats.win_pct > 50 ? '#22c55e' : '#ef4444' },
            { label: 'TP1 HIT RATE',  value: `${stats.tp1_hit_pct}%`, color: '#22c55e' },
            { label: 'TP2 HIT RATE',  value: `${stats.tp2_hit_pct}%`, color: '#22c55e' },
            { label: 'TP3 HIT RATE',  value: `${stats.tp3_hit_pct}%`, color: '#22c55e' },
            { label: 'TOTAL PNL PTS', value: `${stats.total_pnl_pts > 0 ? '+' : ''}${stats.total_pnl_pts}`, color: stats.total_pnl_pts > 0 ? '#22c55e' : '#ef4444' },
            { label: 'AVG WIN',       value: `+${stats.avg_win_pts}`, color: '#22c55e' },
            { label: 'PROFIT FACTOR', value: stats.profit_factor,   color: stats.profit_factor > 1.5 ? '#22c55e' : '#ffb347' },
          ].map(s => (
            <div key={s.label} className="aurum-card" style={{ padding: '12px', textAlign: 'center' }}>
              <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.14em', marginBottom: '4px' }}>{s.label}</div>
              <div style={{ fontSize: '20px', fontWeight: 800, color: s.color }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Per-timeframe stats */}
      {stats?.by_timeframe && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px' }}>
          {(['15min','1h','4h'] as const).map(tf => {
            const t = stats.by_timeframe[tf]
            return (
              <div key={tf} className="aurum-card" style={{ padding: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '14px', fontWeight: 700, color: '#ff7744' }}>{tf.toUpperCase()}</span>
                <span style={{ fontSize: '12px', color: '#6b7494' }}>{t?.total ?? 0} signals</span>
                <span style={{ fontSize: '14px', fontWeight: 700, color: (t?.win_pct ?? 0) > 50 ? '#22c55e' : '#ef4444' }}>
                  {t?.win_pct ?? 0}% WIN
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: '4px' }}>
        {(['all','15min','1h','4h'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '5px 14px',
              fontSize: '11px',
              letterSpacing: '0.12em',
              background: filter === f ? '#ff5500' : 'transparent',
              color:      filter === f ? '#000' : '#4a5068',
              border:     '1px solid rgba(255,80,0,0.2)',
              cursor: 'pointer',
              fontFamily: 'JetBrains Mono, monospace',
              textTransform: 'uppercase',
            }}
          >
            {f === 'all' ? 'ALL TF' : f.toUpperCase()}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={fetchData} style={{ padding: '5px 14px', fontSize: '11px', background: 'transparent', border: '1px solid rgba(255,80,0,0.2)', color: '#4a5068', cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace' }}>
          ⟳ REFRESH
        </button>
      </div>

      {/* Signal table */}
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 2px', fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase' }}>
          <thead>
            <tr style={{ fontSize: '10px', color: '#2a2d3a', letterSpacing: '0.14em' }}>
              {['TIME', 'TF', 'DIR', 'CONV', 'ENTRY', 'STOP', 'TP1', 'TP2', 'TP3', 'STATUS', 'RESULT', 'PNL PTS', 'EDGE', 'DURATION'].map(h => (
                <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 400, borderBottom: '1px solid rgba(255,80,0,0.08)', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {signals.map(s => {
              const statusCfg = STATUS_CONFIG[s.status] || STATUS_CONFIG.CLOSED
              const resultCfg = s.result_label ? (RESULT_CONFIG[s.result_label] || { color: '#6b7494', label: s.result_label }) : null
              const isOpen    = s.status === 'OPEN'
              const isLong    = s.direction === 'long'

              // Live P&L for open signals
              const livePnl = isOpen && livePrice && s.entry_price
                ? (isLong ? livePrice - s.entry_price : s.entry_price - livePrice).toFixed(2)
                : null

              // Duration
              const entryMs   = new Date(s.entry_time).getTime()
              const closeMs   = s.closed_time ? new Date(s.closed_time).getTime() : Date.now()
              const durationH = ((closeMs - entryMs) / 3600000).toFixed(1)

              return (
                <tr key={s.id} style={{
                  background: isOpen ? 'rgba(255,179,71,0.04)' : 'rgba(255,255,255,0.01)',
                  borderLeft: `3px solid ${isLong ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                }}>
                  <td style={{ padding: '8px 10px', color: '#6b7494', whiteSpace: 'nowrap' }}>{fmtTime(s.entry_time)}</td>
                  <td style={{ padding: '8px 10px', fontWeight: 700, color: '#ff7744' }}>{s.timeframe}</td>
                  <td style={{ padding: '8px 10px', fontWeight: 700, color: isLong ? '#22c55e' : '#ef4444' }}>
                    {isLong ? '▲ LONG' : '▼ SHORT'}
                  </td>
                  <td style={{ padding: '8px 10px', color: '#6b7494', fontSize: '11px' }}>{s.conviction?.replace(' CONVICTION','') ?? '—'}</td>
                  <td style={{ padding: '8px 10px', fontWeight: 700, color: '#ff7744' }}>{fmtPrice(s.entry_price)}</td>
                  <td style={{ padding: '8px 10px', color: '#ef4444' }}>{fmtPrice(s.stop_loss)}</td>
                  <td style={{ padding: '8px 10px', color: s.tp1_hit ? '#22c55e' : '#4a5068' }}>
                    {fmtPrice(s.tp1_price)}{s.tp1_hit ? ' ✓' : ''}
                  </td>
                  <td style={{ padding: '8px 10px', color: s.tp2_hit ? '#22c55e' : '#4a5068' }}>
                    {fmtPrice(s.tp2_price)}{s.tp2_hit ? ' ✓' : ''}
                  </td>
                  <td style={{ padding: '8px 10px', color: s.tp3_hit ? '#22c55e' : '#4a5068' }}>
                    {fmtPrice(s.tp3_price)}{s.tp3_hit ? ' ✓' : ''}
                  </td>
                  <td style={{ padding: '8px 10px' }}>
                    <span style={{ padding: '2px 8px', background: statusCfg.bg, color: statusCfg.color, border: `1px solid ${statusCfg.color}40`, fontSize: '10px', letterSpacing: '0.1em' }}>
                      {statusCfg.label}
                    </span>
                  </td>
                  <td style={{ padding: '8px 10px' }}>
                    {resultCfg ? (
                      <span style={{ color: resultCfg.color, fontWeight: 700, fontSize: '11px' }}>{resultCfg.label}</span>
                    ) : isOpen ? (
                      <span style={{ color: '#ffb347', fontSize: '11px' }}>LIVE</span>
                    ) : '—'}
                  </td>
                  <td style={{ padding: '8px 10px', fontWeight: 700, color: livePnl !== null ? (parseFloat(livePnl) >= 0 ? '#22c55e' : '#ef4444') : (parseFloat(s.realized_pnl_pts || 0) >= 0 ? '#22c55e' : '#ef4444') }}>
                    {livePnl !== null
                      ? `${parseFloat(livePnl) >= 0 ? '+' : ''}${livePnl} ~`
                      : s.realized_pnl_pts
                      ? `${parseFloat(s.realized_pnl_pts) >= 0 ? '+' : ''}${parseFloat(s.realized_pnl_pts).toFixed(2)}`
                      : '—'
                    }
                  </td>
                  <td style={{ padding: '8px 10px', color: '#4a5068' }}>{s.edge_strength?.toFixed?.(1) ?? s.edge_strength ?? '—'}</td>
                  <td style={{ padding: '8px 10px', color: '#4a5068' }}>{durationH}h</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!loading && signals.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px', fontSize: '12px', color: '#2a2d3a', letterSpacing: '0.14em' }}>
            NO SIGNALS RECORDED YET — SIGNALS ARE LOGGED WHEN THE ENGINE GENERATES HIGH CONVICTION OR SCALP SIGNALS
          </div>
        )}
      </div>
    </div>
  )
}
