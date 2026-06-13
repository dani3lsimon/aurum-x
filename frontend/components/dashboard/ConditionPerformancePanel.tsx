'use client'
import { useState, useEffect } from 'react'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ''

type CondRow = {
  condition:   string
  value:       string
  signals:     number
  win_pct:     number
  avg_r:       number
  avg_pnl_pts: number
}

type SortKey = keyof CondRow
const COLS: { key: SortKey; label: string }[] = [
  { key: 'condition',   label: 'CONDITION' },
  { key: 'value',       label: 'VALUE'     },
  { key: 'signals',     label: 'SIGNALS'   },
  { key: 'win_pct',     label: 'WIN %'     },
  { key: 'avg_r',       label: 'AVG R'     },
  { key: 'avg_pnl_pts', label: 'AVG PTS'  },
]

export default function ConditionPerformancePanel() {
  const [rows,    setRows]    = useState<CondRow[]>([])
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('avg_r')
  const [sortAsc, setSortAsc] = useState(false)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    fetch(`${BACKEND}/forecast/signal-history/condition-stats`)
      .then(r => r.json())
      .then(d => { if (Array.isArray(d)) setRows(d) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(a => !a)
    else { setSortKey(key); setSortAsc(false) }
  }

  const visible = rows
    .filter(r => showAll || r.signals >= 3)
    .sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv))
      return sortAsc ? cmp : -cmp
    })

  if (loading) return (
    <div style={{ padding: '12px 16px', fontSize: '11px', color: '#4a5068', letterSpacing: '0.14em' }}>
      LOADING CONDITION STATS...
    </div>
  )

  return (
    <div style={{ padding: '12px 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.16em', color: '#ff7744' }}>◆ CONDITION PERFORMANCE</span>
        <button onClick={() => setShowAll(a => !a)} style={{
          fontSize: '10px', padding: '3px 10px', background: 'transparent',
          border: '1px solid rgba(255,80,0,0.2)', color: '#4a5068',
          fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer', letterSpacing: '0.1em',
        }}>
          {showAll ? 'HIDE LOW SAMPLE' : 'SHOW ALL'}
        </button>
      </div>

      {visible.length === 0 ? (
        <div style={{ fontSize: '11px', color: '#2a2d3a', textAlign: 'center', padding: '12px', letterSpacing: '0.12em' }}>
          {rows.length === 0
            ? 'NO CONDITION DATA YET — CONDITIONS_SNAPSHOT POPULATES ONCE SIGNALS CLOSE'
            : 'NO CONDITIONS WITH ≥3 SIGNALS — CLICK "SHOW ALL" TO SEE ALL'}
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 2px', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase' }}>
          <thead>
            <tr style={{ fontSize: '9px', color: '#2a2d3a', letterSpacing: '0.12em' }}>
              {COLS.map(c => (
                <th key={c.key} onClick={() => handleSort(c.key)}
                  style={{ padding: '4px 8px', textAlign: 'left', fontWeight: 400, cursor: 'pointer', userSelect: 'none',
                    color: sortKey === c.key ? '#ff7744' : '#2a2d3a',
                    borderBottom: '1px solid rgba(255,80,0,0.08)', whiteSpace: 'nowrap' }}>
                  {c.label} {sortKey === c.key ? (sortAsc ? '▲' : '▼') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((r, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent' }}>
                <td style={{ padding: '4px 8px', color: '#ff7744', fontWeight: 700 }}>{r.condition}</td>
                <td style={{ padding: '4px 8px', color: '#8a92ab' }}>{r.value}</td>
                <td style={{ padding: '4px 8px', color: '#6b7494' }}>{r.signals}</td>
                <td style={{ padding: '4px 8px', color: r.win_pct >= 50 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>
                  {r.win_pct}%
                </td>
                <td style={{ padding: '4px 8px', color: r.avg_r >= 0 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>
                  {r.avg_r >= 0 ? '+' : ''}{r.avg_r.toFixed(3)}R
                </td>
                <td style={{ padding: '4px 8px', color: r.avg_pnl_pts >= 0 ? '#22c55e' : '#ef4444' }}>
                  {r.avg_pnl_pts >= 0 ? '+' : ''}{r.avg_pnl_pts.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
