'use client'
import { useEffect, useRef, useState } from 'react'
import { Forecast } from '@/lib/types'

interface Props { forecast: Forecast | null }

const TABS = ['4H', '24H', '1W', '1M', '1Q'] as const
type Tab = typeof TABS[number]

const RANGE_KEYS: Record<Tab, { low: keyof Forecast; high: keyof Forecast }> = {
  '4H':  { low: 'range_4h_low',  high: 'range_4h_high'  },
  '24H': { low: 'range_24h_low', high: 'range_24h_high' },
  '1W':  { low: 'range_1w_low',  high: 'range_1w_high'  },
  '1M':  { low: 'range_1m_low',  high: 'range_1m_high'  },
  '1Q':  { low: 'range_1q_low',  high: 'range_1q_high'  },
}

function buildSummary(f: Forecast): string {
  const trend   = f.bullish_prob > 50 ? 'BULLISH' : f.bearish_prob > 40 ? 'BEARISH' : 'NEUTRAL'
  const regime  = (f.macro_regime ?? 'UNKNOWN').replace(/_/g, ' ').toUpperCase()
  const lo      = f.range_24h_low  ?? f.gold_price * 0.97
  const hi      = f.range_24h_high ?? f.gold_price * 1.03
  const mid     = (lo + hi) / 2
  const pct     = (((mid - f.gold_price) / f.gold_price) * 100).toFixed(1)
  const conf    = f.confidence_score?.toFixed(0) ?? '—'
  const momDir  = (f.forecast_momentum ?? 0) >= 0 ? 'POSITIVE' : 'NEGATIVE'

  return (
    `Gold is ${trend} in a ${regime} environment. ` +
    `24H range: $${lo.toFixed(0)}–$${hi.toFixed(0)} (${pct > '0' ? '+' : ''}${pct}% implied move). ` +
    `Momentum is ${momDir}. Model confidence: ${conf}%.`
  )
}

export default function ForecastChart({ forecast }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const animRef      = useRef<number>(0)
  const [tab, setTab]   = useState<Tab>('24H')
  const [dims, setDims] = useState({ w: 0, h: 0 })

  // Observe container div — canvas fills it absolutely
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const e = entries[0]
      if (e) setDims({ w: e.contentRect.width, h: e.contentRect.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const W = canvas.width  = dims.w || 600
    const H = canvas.height = dims.h || 220
    if (W < 10 || H < 10) return

    const price  = forecast?.gold_price ?? 3300
    const bull   = forecast?.bullish_prob ?? 34
    const bear   = forecast?.bearish_prob ?? 33
    const rangeK = RANGE_KEYS[tab]
    const lo     = (forecast?.[rangeK.low]  as number) || price * 0.97
    const hi     = (forecast?.[rangeK.high] as number) || price * 1.03
    const bias   = (bull - bear) / 100

    const pad = { top: 24, bottom: 32, left: 12, right: 12 }
    const cW  = W - pad.left - pad.right
    const cH  = H - pad.top  - pad.bottom

    const priceRange = hi - lo
    const midPrice   = (lo + hi) / 2
    const scaleMin   = midPrice - priceRange * 0.7
    const scaleRange = priceRange * 1.4

    const toY = (p: number) =>
      pad.top + (1 - Math.max(0, Math.min(1, (p - scaleMin) / scaleRange))) * cH

    // Build path
    const POINTS = 80
    const path: { x: number; y: number }[] = []
    let cur = price
    for (let i = 0; i <= POINTS; i++) {
      const t     = i / POINTS
      const trend = bias * priceRange * t * 0.6
      const noise = (Math.random() - 0.5) * priceRange * 0.08
      cur = cur + trend / POINTS + noise
      cur = Math.max(lo * 0.97, Math.min(hi * 1.03, cur))
      path.push({ x: pad.left + t * cW, y: toY(cur) })
    }

    let progress = 0
    const FRAMES = 100

    const draw = () => {
      ctx.clearRect(0, 0, W, H)

      // Range band
      const yHi   = toY(hi)
      const yLo   = toY(lo)
      const band  = ctx.createLinearGradient(0, yHi, 0, yLo)
      band.addColorStop(0, 'rgba(255,80,0,0.07)')
      band.addColorStop(1, 'rgba(180,0,0,0.01)')
      ctx.fillStyle = band
      ctx.fillRect(pad.left, yHi, cW, yLo - yHi)

      // Grid
      ctx.strokeStyle = 'rgba(240,13,23,0.1)'
      ctx.lineWidth   = 1
      for (let g = 0; g <= 4; g++) {
        const gy = pad.top + (g / 4) * cH
        ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(W - pad.right, gy); ctx.stroke()
      }

      const vis = Math.max(2, Math.floor((progress / FRAMES) * path.length))

      // Fill
      const fill = ctx.createLinearGradient(0, pad.top, 0, H)
      fill.addColorStop(0, 'rgba(255,80,0,0.55)')
      fill.addColorStop(1, 'rgba(180,0,0,0.0)')
      ctx.beginPath()
      ctx.moveTo(path[0].x, H - pad.bottom)
      ctx.lineTo(path[0].x, path[0].y)
      for (let i = 1; i < vis; i++) ctx.lineTo(path[i].x, path[i].y)
      ctx.lineTo(path[vis - 1].x, H - pad.bottom)
      ctx.closePath()
      ctx.fillStyle = fill
      ctx.fill()

      // Line
      ctx.shadowColor = '#ff5500'
      ctx.shadowBlur  = 10
      ctx.strokeStyle = '#ff5500'
      ctx.lineWidth   = 2
      ctx.lineJoin    = 'round'
      ctx.beginPath()
      ctx.moveTo(path[0].x, path[0].y)
      for (let i = 1; i < vis; i++) ctx.lineTo(path[i].x, path[i].y)
      ctx.stroke()
      ctx.shadowBlur = 0

      // Labels
      ctx.fillStyle = 'rgba(107,116,148,0.9)'
      ctx.font      = '10px JetBrains Mono, monospace'
      ctx.fillText(`$${hi.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, pad.left + 4, yHi + 12)
      ctx.fillText(`$${lo.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, pad.left + 4, yLo - 4)

      // Dot
      const last = path[vis - 1]
      ctx.beginPath()
      ctx.arc(last.x, last.y, 4, 0, Math.PI * 2)
      ctx.fillStyle  = '#ff5500'
      ctx.shadowColor = '#ff5500'
      ctx.shadowBlur  = 10
      ctx.fill()
      ctx.shadowBlur = 0

      // Price tag
      ctx.fillStyle = '#ff6633'
      ctx.font      = 'bold 11px JetBrains Mono, monospace'
      ctx.fillText(`$${cur.toFixed(0)}`, Math.min(last.x + 6, W - 60), last.y + 4)

      if (progress < FRAMES) {
        progress++
        animRef.current = requestAnimationFrame(draw)
      }
    }

    cancelAnimationFrame(animRef.current)
    animRef.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(animRef.current)
  }, [forecast, tab, dims])

  const bull = forecast?.bullish_prob ?? 0
  const bear = forecast?.bearish_prob ?? 0
  const summary = forecast ? buildSummary(forecast) : null

  return (
    <div className="aurum-card p-4 flex flex-col gap-3" style={{ height: '100%' }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="section-label">Price Forecast Chart</div>
        <div className="flex gap-1">
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              background:    tab === t ? 'rgba(240,13,23,0.2)' : 'transparent',
              border:        `1px solid ${tab === t ? 'rgba(240,13,23,0.5)' : 'rgba(240,13,23,0.15)'}`,
              color:         tab === t ? '#ff4400' : '#4a5068',
              borderRadius:  '2px',
              cursor:        'pointer',
              fontFamily:    "'JetBrains Mono', monospace",
              fontSize:      '0.65rem',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              padding:       '2px 8px',
            }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Canvas container — fixed height, canvas fills it */}
      <div ref={containerRef} style={{ width: '100%', height: '200px', position: 'relative', flexShrink: 0 }}>
        <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
      </div>

      {/* Probability bar */}
      <div className="flex h-2 overflow-hidden">
        <div style={{ width: `${bull}%`, background: '#22c55e', transition: 'width 0.8s ease' }} />
        <div style={{ width: `${100 - bull - bear}%`, background: '#94a3b8', transition: 'width 0.8s ease' }} />
        <div style={{ width: `${bear}%`, background: '#ef4444', transition: 'width 0.8s ease' }} />
      </div>
      <div className="flex justify-between" style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
        <span style={{ color: '#22c55e' }}>BULL {bull.toFixed(0)}%</span>
        <span>NEUT {(100 - bull - bear).toFixed(0)}%</span>
        <span style={{ color: '#ef4444' }}>BEAR {bear.toFixed(0)}%</span>
      </div>

      {/* Plain-language summary */}
      {summary && (
        <div style={{ borderTop: '1px solid rgba(240,13,23,0.15)', paddingTop: '12px' }}>
          <div className="section-label" style={{ marginBottom: '8px' }}>Market Intel Summary</div>
          <div style={{
            fontSize:      '0.78rem',
            color:         '#c8cde0',
            letterSpacing: '0.02em',
            lineHeight:    1.8,
            textTransform: 'none',
            fontFamily:    "'JetBrains Mono', monospace",
          }}>
            {summary}
          </div>
        </div>
      )}
    </div>
  )
}
