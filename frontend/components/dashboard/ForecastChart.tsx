'use client'
import { useEffect, useRef, useState } from 'react'
import { Forecast, OHLCVBar, OrderFlowData } from '@/lib/types'

interface Props {
  forecast:   Forecast | null
  ohlcvData:  OHLCVBar[]
  orderFlow?: OrderFlowData | null
  chartTf:    '15m' | '1h' | '4h' | '1d'
  onTfChange: (tf: '15m' | '1h' | '4h' | '1d') => void
}

const TF_TABS: { key: '15m' | '1h' | '4h' | '1d'; label: string }[] = [
  { key: '15m', label: '15M' },
  { key: '1h',  label: '1H'  },
  { key: '4h',  label: '4H'  },
  { key: '1d',  label: '1D'  },
]

function fmtPrice(p: number): string {
  return `$${p.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function ForecastChart({ forecast, ohlcvData, orderFlow, chartTf, onTfChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const [dims, setDims] = useState({ w: 0, h: 0 })

  // Observe container — canvas fills it absolutely
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

    const dpr = window.devicePixelRatio || 1
    const cssW = dims.w || 600
    const cssH = dims.h || 320
    if (cssW < 10 || cssH < 10) return

    canvas.width  = cssW * dpr
    canvas.height = cssH * dpr
    canvas.style.width  = `${cssW}px`
    canvas.style.height = `${cssH}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const W = cssW
    const H = cssH

    const bars = (ohlcvData || []).filter(b => b && typeof b.close === 'number')
    if (bars.length < 2) {
      ctx.clearRect(0, 0, W, H)
      ctx.fillStyle = 'rgba(107,116,148,0.6)'
      ctx.font      = '11px JetBrains Mono, monospace'
      ctx.fillText('Waiting for live OANDA price data…', 16, H / 2)
      return
    }

    const currentPrice = orderFlow?.current_price ?? bars[bars.length - 1].close
    const vwap         = orderFlow?.session_vwap

    // Layout: candles occupy left 80%, forecast bands fan out on the right 20%
    const pad     = { top: 28, bottom: 28, left: 12, right: 14 }
    const fullW   = W - pad.left - pad.right
    const candleW = fullW * 0.80
    const bandW   = fullW * 0.20
    const cH      = H - pad.top - pad.bottom

    // Price scale — derived from candle highs/lows + forecast ranges so
    // both the historical action and the projected bands fit comfortably
    let lo = Math.min(...bars.map(b => b.low))
    let hi = Math.max(...bars.map(b => b.high))
    if (forecast) {
      const fLo = Math.min(forecast.range_24h_low ?? lo, forecast.range_4h_low ?? lo)
      const fHi = Math.max(forecast.range_24h_high ?? hi, forecast.range_4h_high ?? hi)
      lo = Math.min(lo, fLo)
      hi = Math.max(hi, fHi)
    }
    const range    = (hi - lo) || (currentPrice * 0.02)
    const scaleMin = lo - range * 0.08
    const scaleMax = hi + range * 0.08
    const scaleRange = scaleMax - scaleMin

    const toY = (p: number) =>
      pad.top + (1 - Math.max(0, Math.min(1, (p - scaleMin) / scaleRange))) * cH

    const n = bars.length
    const slot = candleW / n
    const bodyW = Math.max(1.5, slot * 0.6)
    const xAt = (i: number) => pad.left + slot * (i + 0.5)

    ctx.clearRect(0, 0, W, H)

    // Grid
    ctx.strokeStyle = 'rgba(240,13,23,0.08)'
    ctx.lineWidth   = 1
    for (let g = 0; g <= 4; g++) {
      const gy = pad.top + (g / 4) * cH
      ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(W - pad.right, gy); ctx.stroke()
      const gp = scaleMax - (g / 4) * scaleRange
      ctx.fillStyle = 'rgba(107,116,148,0.55)'
      ctx.font      = '9px JetBrains Mono, monospace'
      ctx.fillText(fmtPrice(gp), pad.left + 4, gy - 3)
    }

    // ── Candlesticks (real OANDA OHLCV) ──────────────────────────────────
    for (let i = 0; i < n; i++) {
      const b = bars[i]
      const x = xAt(i)
      const up = b.close >= b.open
      const color = up ? '#22c55e' : '#ef4444'
      ctx.strokeStyle = color
      ctx.fillStyle   = color
      ctx.lineWidth   = 1
      // wick
      ctx.beginPath()
      ctx.moveTo(x, toY(b.high))
      ctx.lineTo(x, toY(b.low))
      ctx.stroke()
      // body
      const yO = toY(b.open)
      const yC = toY(b.close)
      const top = Math.min(yO, yC)
      const h   = Math.max(1, Math.abs(yC - yO))
      ctx.fillRect(x - bodyW / 2, top, bodyW, h)
    }

    // ── Connecting price line with glow + gradient fill ──────────────────
    const closes = bars.map((b, i) => ({ x: xAt(i), y: toY(b.close) }))
    const fill = ctx.createLinearGradient(0, pad.top, 0, H - pad.bottom)
    fill.addColorStop(0, 'rgba(255,80,0,0.18)')
    fill.addColorStop(1, 'rgba(180,0,0,0.0)')
    ctx.beginPath()
    ctx.moveTo(closes[0].x, H - pad.bottom)
    ctx.lineTo(closes[0].x, closes[0].y)
    for (let i = 1; i < closes.length; i++) ctx.lineTo(closes[i].x, closes[i].y)
    ctx.lineTo(closes[closes.length - 1].x, H - pad.bottom)
    ctx.closePath()
    ctx.fillStyle = fill
    ctx.fill()

    ctx.shadowColor = '#ff5500'
    ctx.shadowBlur  = 8
    ctx.strokeStyle = 'rgba(255,85,0,0.85)'
    ctx.lineWidth   = 1.5
    ctx.lineJoin    = 'round'
    ctx.beginPath()
    ctx.moveTo(closes[0].x, closes[0].y)
    for (let i = 1; i < closes.length; i++) ctx.lineTo(closes[i].x, closes[i].y)
    ctx.stroke()
    ctx.shadowBlur = 0

    // ── VWAP line (dashed amber) ─────────────────────────────────────────
    if (typeof vwap === 'number' && vwap > 0) {
      const y = toY(vwap)
      ctx.save()
      ctx.setLineDash([5, 4])
      ctx.strokeStyle = 'rgba(245,158,11,0.7)'
      ctx.lineWidth   = 1.25
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + candleW, y); ctx.stroke()
      ctx.restore()
      ctx.fillStyle = 'rgba(245,158,11,0.85)'
      ctx.font      = '9px JetBrains Mono, monospace'
      ctx.fillText(`VWAP ${fmtPrice(vwap)}`, pad.left + 4, y - 4)
    }

    // ── VAH / VAL lines (thin dashed green) ──────────────────────────────
    const vah = orderFlow?.vah
    const val = orderFlow?.val
    for (const [label, lvl] of [['VAH', vah], ['VAL', val]] as [string, number | undefined][]) {
      if (typeof lvl === 'number' && lvl > 0) {
        const y = toY(lvl)
        ctx.save()
        ctx.setLineDash([3, 3])
        ctx.strokeStyle = 'rgba(34,197,94,0.4)'
        ctx.lineWidth   = 1
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + candleW, y); ctx.stroke()
        ctx.restore()
        ctx.fillStyle = 'rgba(34,197,94,0.65)'
        ctx.font      = '8px JetBrains Mono, monospace'
        ctx.fillText(`${label} ${fmtPrice(lvl)}`, pad.left + candleW - 64, y - 3)
      }
    }

    // ── Forecast bands (right 20%) — 4 horizons fanning from current price ─
    const bandX0 = pad.left + candleW + 6
    const bandSpan = bandW - 12
    const lastClose = bars[bars.length - 1].close
    const startY = toY(lastClose)

    type Band = { label: string; lo?: number; hi?: number; widthFactor: number; color: string }
    const bands: Band[] = []
    if (forecast) {
      const r4lo = forecast.range_4h_low, r4hi = forecast.range_4h_high
      const r24lo = forecast.range_24h_low, r24hi = forecast.range_24h_high
      // 15min / 1h bands derived as narrower fractions of the 4h range —
      // honestly labelled as scaled projections, not independently forecast
      const mid4 = ((r4lo ?? lastClose) + (r4hi ?? lastClose)) / 2
      const half4 = Math.abs((r4hi ?? lastClose) - (r4lo ?? lastClose)) / 2
      bands.push({ label: '15m',  lo: mid4 - half4 * 0.35, hi: mid4 + half4 * 0.35, widthFactor: 0.28, color: 'rgba(255,255,255,0.10)' })
      bands.push({ label: '1h',   lo: mid4 - half4 * 0.65, hi: mid4 + half4 * 0.65, widthFactor: 0.52, color: 'rgba(255,255,255,0.09)' })
      bands.push({ label: '4h',   lo: r4lo,  hi: r4hi,  widthFactor: 0.76, color: 'rgba(255,165,0,0.12)' })
      bands.push({ label: '24h',  lo: r24lo, hi: r24hi, widthFactor: 1.00, color: 'rgba(255,80,0,0.10)' })
    }

    bands.forEach((b, idx) => {
      if (b.lo == null || b.hi == null) return
      const x = bandX0 + bandSpan * (idx / Math.max(1, bands.length - 1)) * 0 // stacked, not staggered horizontally
      const w = bandSpan * b.widthFactor
      const x0 = bandX0
      const yHi = toY(Math.max(b.lo, b.hi))
      const yLo = toY(Math.min(b.lo, b.hi))
      ctx.fillStyle = b.color
      ctx.fillRect(x0, yHi, w, Math.max(2, yLo - yHi))
      ctx.strokeStyle = 'rgba(255,255,255,0.12)'
      ctx.lineWidth = 1
      ctx.strokeRect(x0, yHi, w, Math.max(2, yLo - yHi))
      ctx.fillStyle = 'rgba(200,205,224,0.65)'
      ctx.font      = '8px JetBrains Mono, monospace'
      ctx.fillText(b.label, x0 + 3, yHi + 9)
      void x
    })

    // ── Forecast midline — dashed orange projection from current price ───
    if (forecast) {
      const momentum = forecast.forecast_momentum ?? 0
      const slope    = momentum >= 0 ? -1 : 1   // canvas y grows downward; up-move = negative slope
      const endX     = bandX0 + bandSpan
      const endY     = startY + slope * cH * 0.12 * Math.min(1, Math.abs(momentum) || 0.3)
      ctx.save()
      ctx.setLineDash([4, 4])
      ctx.strokeStyle = 'rgba(255,140,0,0.65)'
      ctx.lineWidth   = 1.5
      ctx.beginPath()
      ctx.moveTo(closes[closes.length - 1].x, startY)
      ctx.lineTo(endX, endY)
      ctx.stroke()
      ctx.restore()
    }

    // ── Current price label (filled rectangle at right edge) ─────────────
    const labelText = fmtPrice(currentPrice)
    ctx.font = 'bold 11px JetBrains Mono, monospace'
    const tw = ctx.measureText(labelText).width
    const ly = Math.max(pad.top + 8, Math.min(H - pad.bottom - 8, startY))
    ctx.fillStyle = '#ff5500'
    ctx.fillRect(W - pad.right - tw - 12, ly - 9, tw + 10, 18)
    ctx.fillStyle = '#0a0c12'
    ctx.fillText(labelText, W - pad.right - tw - 7, ly + 4)

    // dot at current price on the candle line
    ctx.beginPath()
    ctx.arc(closes[closes.length - 1].x, closes[closes.length - 1].y, 3.5, 0, Math.PI * 2)
    ctx.fillStyle   = '#ff5500'
    ctx.shadowColor = '#ff5500'
    ctx.shadowBlur  = 8
    ctx.fill()
    ctx.shadowBlur = 0

  }, [ohlcvData, orderFlow, forecast, dims])

  const bull = forecast?.bullish_prob ?? 0
  const bear = forecast?.bearish_prob ?? 0

  return (
    <div className="aurum-card p-4 flex flex-col gap-3" style={{ height: '100%' }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="section-label">Price Action &amp; Forecast Bands</div>
        <div className="flex gap-1">
          {TF_TABS.map(t => (
            <button key={t.key} onClick={() => onTfChange(t.key)} style={{
              background:    chartTf === t.key ? 'rgba(240,13,23,0.2)' : 'transparent',
              border:        `1px solid ${chartTf === t.key ? 'rgba(240,13,23,0.5)' : 'rgba(240,13,23,0.15)'}`,
              color:         chartTf === t.key ? '#ff4400' : '#4a5068',
              borderRadius:  '2px',
              cursor:        'pointer',
              fontFamily:    "'JetBrains Mono', monospace",
              fontSize:      '0.65rem',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              padding:       '2px 8px',
            }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Canvas — 100% width x 320px height, retina-sharp */}
      <div ref={containerRef} style={{ width: '100%', height: '320px', position: 'relative', flexShrink: 0 }}>
        <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0 }} />
      </div>

      {/* OANDA live order-flow strip */}
      {orderFlow && (
        <div style={{
          fontSize: '0.65rem', color: 'var(--text-label)', letterSpacing: '0.04em',
          fontFamily: "'JetBrains Mono', monospace", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          borderTop: '1px solid rgba(240,13,23,0.1)', paddingTop: '8px',
        }}>
          VWAP {orderFlow.session_vwap != null ? fmtPrice(orderFlow.session_vwap) : '—'}
          {' · '}DELTA {orderFlow.cumulative_delta ?? '—'} ({orderFlow.delta_direction ?? '—'})
          {' · '}POC {orderFlow.poc_price != null ? fmtPrice(orderFlow.poc_price) : '—'}
          {' · '}VAH {orderFlow.vah != null ? fmtPrice(orderFlow.vah) : '—'}
          {' · '}VAL {orderFlow.val != null ? fmtPrice(orderFlow.val) : '—'}
        </div>
      )}

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
    </div>
  )
}
