'use client'
import { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'

const BACKEND    = process.env.NEXT_PUBLIC_BACKEND_URL || ''
const REFRESH_MS = 30_000

type Point = {
  signal_id:    string
  closed_time:  string
  timeframe:    string
  pnl_usd:      number
  pnl_pts:      number
  equity:       number
  cum_pts:      number
  drawdown_pct: number
}
type Monthly = { month: string; trades: number; win_pct: number; pnl_usd: number }
type CurveData = {
  starting_capital: number
  final_equity:     number
  final_cum_pts:    number
  max_drawdown_pct: number
  points:           Point[]
  monthly:          Monthly[]
}

const fmtMoney = (v: number) =>
  v >= 0 ? `+$${v.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : `-$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

export default function EquityCurvePanel() {
  const [data,     setData]    = useState<CurveData | null>(null)
  const [stats,    setStats]   = useState<any>(null)
  const [mode,     setMode]    = useState<'pts' | 'usd'>('pts')
  const [loading,  setLoading] = useState(true)

  const fetchData = async () => {
    try {
      const [curveRes, statsRes] = await Promise.all([
        fetch(`${BACKEND}/forecast/signal-history/equity-curve`).then(r => r.json()),
        fetch(`${BACKEND}/forecast/signal-history/stats`).then(r => r.json()),
      ])
      setData(curveRes)
      setStats(statsRes)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])
  useEffect(() => {
    const t = setInterval(fetchData, REFRESH_MS)
    return () => clearInterval(t)
  }, [])

  if (loading) return (
    <div style={{ padding: '16px', fontSize: '11px', color: '#4a5068', letterSpacing: '0.14em' }}>
      LOADING EQUITY CURVE...
    </div>
  )

  if (!data || data.points.length === 0) return (
    <div style={{ padding: '20px', textAlign: 'center', color: '#2a2d3a', fontSize: '12px', letterSpacing: '0.14em' }}>
      NO CLOSED SIGNALS YET — EQUITY CURVE WILL APPEAR ONCE SIGNALS CLOSE
    </div>
  )

  const chartData = data.points.map((p, i) => ({
    idx:      i + 1,
    label:    p.closed_time.slice(0, 10),
    equity:   p.equity,
    cum_pts:  p.cum_pts,
    drawdown: -p.drawdown_pct,
  }))

  const yKey     = mode === 'usd' ? 'equity' : 'cum_pts'
  const baseline = mode === 'usd' ? data.starting_capital : 0
  const isUp     = mode === 'usd' ? data.final_equity >= data.starting_capital : data.final_cum_pts >= 0
  const lineColor = isUp ? '#22c55e' : '#ef4444'

  const summaryItems = [
    { label: 'TOTAL PNL',      value: mode === 'usd' ? fmtMoney(data.final_equity - data.starting_capital) : `${data.final_cum_pts >= 0 ? '+' : ''}${data.final_cum_pts.toFixed(1)} pts`, color: isUp ? '#22c55e' : '#ef4444' },
    { label: 'WIN RATE',       value: `${stats?.win_pct ?? 0}%`,                       color: (stats?.win_pct ?? 0) > 50 ? '#22c55e' : '#ef4444' },
    { label: 'PROFIT FACTOR',  value: stats?.profit_factor_r ?? '—',                   color: (stats?.profit_factor_r ?? 0) > 1 ? '#22c55e' : '#ef4444' },
    { label: 'MAX DRAWDOWN',   value: `${data.max_drawdown_pct.toFixed(1)}%`,          color: data.max_drawdown_pct > 10 ? '#ef4444' : '#ffb347' },
    { label: 'AVG R',          value: `${stats?.avg_r >= 0 ? '+' : ''}${(stats?.avg_r ?? 0).toFixed(3)}R`, color: (stats?.avg_r ?? 0) > 0 ? '#22c55e' : '#ef4444' },
  ]

  return (
    <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {/* Header + toggle */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.16em', color: '#ff7744' }}>◆ EQUITY CURVE</span>
        <div style={{ display: 'flex', gap: '4px' }}>
          {(['pts', 'usd'] as const).map(m => (
            <button key={m} onClick={() => setMode(m)} style={{
              padding: '3px 10px', fontSize: '10px', letterSpacing: '0.1em',
              background: mode === m ? '#ff5500' : 'transparent',
              color:      mode === m ? '#000' : '#4a5068',
              border: '1px solid rgba(255,80,0,0.2)', cursor: 'pointer',
              fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase',
            }}>
              {m === 'pts' ? 'POINTS' : '$10K SIM'}
            </button>
          ))}
        </div>
      </div>

      {/* Summary stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '6px' }}>
        {summaryItems.map(s => (
          <div key={s.label} style={{ textAlign: 'center', padding: '8px 4px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,80,0,0.06)' }}>
            <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.12em', marginBottom: '3px' }}>{s.label}</div>
            <div style={{ fontSize: '14px', fontWeight: 800, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Equity chart */}
      <div style={{ height: '140px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="ecGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={lineColor} stopOpacity={0.25} />
                <stop offset="95%" stopColor={lineColor} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,80,0,0.06)" />
            <XAxis dataKey="idx" tick={{ fill: '#4a5068', fontSize: 9 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fill: '#4a5068', fontSize: 9 }} tickLine={false} axisLine={false} width={50}
              tickFormatter={v => mode === 'usd' ? `$${(v/1000).toFixed(1)}k` : `${v.toFixed(0)}pt`} />
            <Tooltip
              contentStyle={{ background: '#0d0f17', border: '1px solid rgba(255,80,0,0.3)', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace' }}
              labelFormatter={(i) => chartData[+i - 1]?.label ?? ''}
              formatter={(v: any) => [mode === 'usd' ? `$${(+v).toFixed(2)}` : `${(+v).toFixed(2)} pts`, mode === 'usd' ? 'Equity' : 'Cum Pts']}
            />
            <ReferenceLine y={baseline} stroke="rgba(255,80,0,0.2)" strokeDasharray="4 4" />
            <Area type="monotone" dataKey={yKey} stroke={lineColor} strokeWidth={2}
              fill="url(#ecGrad)" dot={false} activeDot={{ r: 3, fill: lineColor }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Monthly breakdown */}
      {data.monthly.length > 0 && (
        <div style={{ overflow: 'auto', maxHeight: '100px' }}>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 2px', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace' }}>
            <thead>
              <tr style={{ fontSize: '9px', color: '#2a2d3a', letterSpacing: '0.12em' }}>
                {['MONTH', 'TRADES', 'WIN %', 'PNL ($)'].map(h => (
                  <th key={h} style={{ padding: '3px 8px', textAlign: 'left', fontWeight: 400 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.monthly.map(m => (
                <tr key={m.month} style={{ background: 'rgba(255,255,255,0.01)' }}>
                  <td style={{ padding: '3px 8px', color: '#ff7744', fontWeight: 700 }}>{m.month}</td>
                  <td style={{ padding: '3px 8px', color: '#6b7494' }}>{m.trades}</td>
                  <td style={{ padding: '3px 8px', color: m.win_pct > 50 ? '#22c55e' : '#ef4444' }}>{m.win_pct}%</td>
                  <td style={{ padding: '3px 8px', color: m.pnl_usd >= 0 ? '#22c55e' : '#ef4444', fontWeight: 700 }}>
                    {m.pnl_usd >= 0 ? '+' : ''}{m.pnl_usd.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
