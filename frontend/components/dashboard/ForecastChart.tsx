'use client'
import { useEffect, useRef, useState } from 'react'
import { Forecast, OHLCVBar, OrderFlowData } from '@/lib/types'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

interface Props {
  forecast:     Forecast | null
  ohlcvData:    OHLCVBar[]
  setOhlcvData?: (updater: (prev: OHLCVBar[]) => OHLCVBar[]) => void
  orderFlow?:   OrderFlowData | null
  chartTf:      '15m' | '1h' | '4h' | '1d'
  onTfChange:   (tf: '15m' | '1h' | '4h' | '1d') => void
  lastTickPrice?: number
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
function fmtPrice2(p: number): string {
  return `$${p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function ForecastChart({ forecast, ohlcvData, setOhlcvData, orderFlow, chartTf, onTfChange, lastTickPrice }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const [dims, setDims] = useState({ w: 0, h: 0 })
  const animFrameRef = useRef<number | undefined>(undefined)

  // ── Live price — polled every 30s from /market/orderflow (real OANDA tick) ──
  const [livePrice, setLivePrice] = useState<number>(forecast?.gold_price ?? 0)
  useEffect(() => {
    const fetchPrice = async () => {
      try {
        const r = await fetch(`${BACKEND}/market/orderflow`)
        const d = await r.json()
        if (d?.current_price) setLivePrice(d.current_price)
      } catch { /* keep previous value */ }
    }
    fetchPrice()
    const interval = setInterval(fetchPrice, 30000)
    return () => clearInterval(interval)
  }, [])

  // ── Tick-level last-candle update — fires on EVERY cTrader tick ─────────────
  useEffect(() => {
    if (!setOhlcvData || !lastTickPrice || !ohlcvData.length) return
    setOhlcvData(prev => {
      if (!prev.length) return prev
      const updated = [...prev]
      const last = { ...updated[updated.length - 1] }
      last.close = lastTickPrice
      if (lastTickPrice > last.high) last.high = lastTickPrice
      if (lastTickPrice < last.low)  last.low  = lastTickPrice
      updated[updated.length - 1] = last
      return updated
    })
  }, [lastTickPrice])

  // ── New-candle detection — checks every 10s if a new bar has started ────────
  const lastCandleTimeRef = useRef<string>('')
  useEffect(() => {
    if (!ohlcvData.length) return
    lastCandleTimeRef.current = ohlcvData[ohlcvData.length - 1].time
  }, [ohlcvData])

  useEffect(() => {
    if (!setOhlcvData) return
    const checkNewCandle = async () => {
      if (!lastCandleTimeRef.current) return
      try {
        const tf = { '15m': 'M15', '1h': 'H1', '4h': 'H4', '1d': 'D' }[chartTf] || 'H1'
        const r  = await fetch(`${BACKEND}/market/candles?granularity=${tf}&count=2`)
        const candles: OHLCVBar[] = await r.json()
        if (!candles.length) return

        const newest = candles[candles.length - 1]
        if (newest.time !== lastCandleTimeRef.current) {
          setOhlcvData(prev => {
            const updated = [...prev, newest]
            if (updated.length > 200) updated.shift()
            return updated
          })
          lastCandleTimeRef.current = newest.time
        }
      } catch {}
    }
    const interval = setInterval(checkNewCandle, 10000)
    return () => clearInterval(interval)
  }, [chartTf, setOhlcvData])

  // ── Hover tooltip — OHLCV for the candle under the cursor ───────────────────
  const [tooltip, setTooltip] = useState<{ visible: boolean; x: number; y: number; data: OHLCVBar | null }>({
    visible: false, x: 0, y: 0, data: null,
  })

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

    const bars = (ohlcvData || []).filter(b => b && typeof b.close === 'number')

    // Layout constants — shared between draw pass and the mousemove hit-test
    const pad = { top: 28, bottom: 28, left: 12, right: 14 }

    const drawChart = () => {
      const dpr  = window.devicePixelRatio || 1
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
      const fullW   = W - pad.left - pad.right
      const candleW = fullW * 0.80
      const bandW   = fullW * 0.20
      const cH      = H - pad.top - pad.bottom

      // Price scale — derived from candle highs/lows + forecast ranges + live price
      let lo = Math.min(...bars.map(b => b.low))
      let hi = Math.max(...bars.map(b => b.high))
      if (forecast) {
        const fLo = Math.min(forecast.range_24h_low ?? lo, forecast.range_4h_low ?? lo)
        const fHi = Math.max(forecast.range_24h_high ?? hi, forecast.range_4h_high ?? hi)
        lo = Math.min(lo, fLo)
        hi = Math.max(hi, fHi)
      }
      if (livePrice > 0) { lo = Math.min(lo, livePrice); hi = Math.max(hi, livePrice) }
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

      // ── Candlesticks (real OANDA OHLCV) ────────────────────────────────
      for (let i = 0; i < n; i++) {
        const b = bars[i]
        const x = xAt(i)
        const up = b.close >= b.open
        const color = up ? '#22c55e' : '#ef4444'
        ctx.strokeStyle = color
        ctx.fillStyle   = color
        ctx.lineWidth   = 1
        ctx.beginPath()
        ctx.moveTo(x, toY(b.high))
        ctx.lineTo(x, toY(b.low))
        ctx.stroke()
        const yO = toY(b.open)
        const yC = toY(b.close)
        const top = Math.min(yO, yC)
        const h   = Math.max(1, Math.abs(yC - yO))
        ctx.fillRect(x - bodyW / 2, top, bodyW, h)
      }

      // ── Connecting price line with glow + gradient fill ─────────────────
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
        const mid4 = ((r4lo ?? lastClose) + (r4hi ?? lastClose)) / 2
        const half4 = Math.abs((r4hi ?? lastClose) - (r4lo ?? lastClose)) / 2
        bands.push({ label: '15m',  lo: mid4 - half4 * 0.35, hi: mid4 + half4 * 0.35, widthFactor: 0.28, color: 'rgba(255,255,255,0.10)' })
        bands.push({ label: '1h',   lo: mid4 - half4 * 0.65, hi: mid4 + half4 * 0.65, widthFactor: 0.52, color: 'rgba(255,255,255,0.09)' })
        bands.push({ label: '4h',   lo: r4lo,  hi: r4hi,  widthFactor: 0.76, color: 'rgba(255,165,0,0.12)' })
        bands.push({ label: '24h',  lo: r24lo, hi: r24hi, widthFactor: 1.00, color: 'rgba(255,80,0,0.10)' })
      }

      bands.forEach(b => {
        if (b.lo == null || b.hi == null) return
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
      })

      // ── Forecast midline — dashed orange projection from current price ───
      if (forecast) {
        const momentum = forecast.forecast_momentum ?? 0
        const slope    = momentum >= 0 ? -1 : 1
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
      ctx.shadowBlur  = 0

      // ── LIVE PRICE — dashed horizontal line + pulsing dot + label ────────
      if (livePrice && livePrice > scaleMin && livePrice < scaleMax) {
        const yLive = toY(livePrice)

        ctx.save()
        ctx.strokeStyle = '#ff5500'
        ctx.lineWidth   = 1
        ctx.globalAlpha = 0.8
        ctx.setLineDash([3, 3])
        ctx.beginPath()
        ctx.moveTo(pad.left, yLive)
        ctx.lineTo(W - pad.right, yLive)
        ctx.stroke()
        ctx.setLineDash([])
        ctx.globalAlpha = 1

        const labelW = 72
        const labelH = 18
        ctx.fillStyle = '#ff5500'
        ctx.fillRect(W - pad.right, yLive - labelH / 2, labelW, labelH)
        ctx.fillStyle = '#000000'
        ctx.font = 'bold 10px JetBrains Mono, monospace'
        ctx.textAlign = 'center'
        ctx.fillText(fmtPrice2(livePrice), W - pad.right + labelW / 2, yLive + 4)
        ctx.textAlign = 'left'

        const pulse = 0.6 + 0.4 * Math.sin(Date.now() / 300)
        ctx.beginPath()
        ctx.arc(W - pad.right - 4, yLive, 5, 0, Math.PI * 2)
        ctx.fillStyle = '#ff5500'
        ctx.globalAlpha = pulse
        ctx.fill()
        ctx.globalAlpha = 1

        ctx.beginPath()
        ctx.arc(W - pad.right - 4, yLive, 8, 0, Math.PI * 2)
        ctx.strokeStyle = '#ff5500'
        ctx.lineWidth = 1
        ctx.globalAlpha = pulse * 0.4
        ctx.stroke()
        ctx.globalAlpha = 1
        ctx.restore()
      }
    }

    drawChart()

    // ── Hover tooltip — map mouse X to nearest candle ────────────────────────
    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const cssW = dims.w || rect.width
      const fullW   = cssW - pad.left - pad.right
      const candleW = fullW * 0.80
      const n = bars.length
      if (n < 2) return
      const slot = candleW / n
      const mx = e.clientX - rect.left
      const idx = Math.floor((mx - pad.left) / slot)
      if (idx >= 0 && idx < n) {
        setTooltip({ visible: true, x: mx, y: e.clientY - rect.top, data: bars[idx] })
      } else {
        setTooltip(prev => (prev.visible ? { ...prev, visible: false } : prev))
      }
    }
    const handleMouseLeave = () => setTooltip(prev => (prev.visible ? { ...prev, visible: false } : prev))

    canvas.addEventListener('mousemove', handleMouseMove)
    canvas.addEventListener('mouseleave', handleMouseLeave)

    // ── Animate the pulsing live-price dot during likely market hours (UTC) ──
    const nowHour = new Date().getUTCHours()
    if (nowHour >= 6 && nowHour <= 21) {
      const animate = () => {
        drawChart()
        animFrameRef.current = requestAnimationFrame(animate)
      }
      animFrameRef.current = requestAnimationFrame(animate)
    }

    return () => {
      canvas.removeEventListener('mousemove', handleMouseMove)
      canvas.removeEventListener('mouseleave', handleMouseLeave)
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [ohlcvData, orderFlow, forecast, dims, livePrice])

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
              fontSize:      '0.7rem',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              padding:       '3px 10px',
            }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Canvas — 100% width x 320px height, retina-sharp, with hover tooltip overlay */}
      <div ref={containerRef} style={{ width: '100%', height: '320px', position: 'relative', flexShrink: 0 }}>
        <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, cursor: 'crosshair' }} />

        {tooltip.visible && tooltip.data && (
          <div style={{
            position: 'absolute',
            left: tooltip.x + 12,
            top: Math.max(0, tooltip.y - 10),
            background: '#0d0f17',
            border: '1px solid rgba(255,80,0,0.4)',
            padding: '8px 12px',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            color: '#e0e0e0',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            lineHeight: 1.8,
            zIndex: 10,
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
          }}>
            <div style={{ color: '#4a5068', fontSize: '9px', letterSpacing: '0.14em', marginBottom: '4px' }}>
              {tooltip.data.time?.slice(0, 16).replace('T', ' ')} UTC
            </div>
            <div>O <span style={{ color: '#ff7744' }}>${tooltip.data.open?.toFixed(2)}</span></div>
            <div>H <span style={{ color: '#22c55e' }}>${tooltip.data.high?.toFixed(2)}</span></div>
            <div>L <span style={{ color: '#ef4444' }}>${tooltip.data.low?.toFixed(2)}</span></div>
            <div>C <span style={{ color: tooltip.data.close >= tooltip.data.open ? '#22c55e' : '#ef4444' }}>
              ${tooltip.data.close?.toFixed(2)}
            </span></div>
            <div>V <span style={{ color: '#6b7494' }}>{tooltip.data.volume?.toLocaleString()}</span></div>
          </div>
        )}
      </div>

      {/* Live order-flow + cTrader tick status strip */}
      {orderFlow && (
        <div style={{ display: 'flex', gap: '20px', fontSize: '11px', color: '#4a5068', letterSpacing: '0.12em', fontFamily: "'JetBrains Mono', monospace", borderTop: '1px solid rgba(255,80,0,0.06)', paddingTop: '6px', marginTop: '8px', overflow: 'hidden', whiteSpace: 'nowrap' }}>
          <span>VWAP <span style={{ color: '#ff7744' }}>{orderFlow.session_vwap != null ? fmtPrice2(orderFlow.session_vwap) : '—'}</span></span>
          <span>DELTA <span style={{ color: (orderFlow.cumulative_delta || 0) > 0 ? '#22c55e' : '#ef4444' }}>
            {(orderFlow.cumulative_delta || 0) > 0 ? '+' : ''}{orderFlow.cumulative_delta?.toFixed?.(0) ?? orderFlow.cumulative_delta ?? '—'}
          </span></span>
          <span>POC <span style={{ color: '#ff6633' }}>{orderFlow.poc_price != null ? fmtPrice2(orderFlow.poc_price) : '—'}</span></span>
          <span>VAH <span style={{ color: '#22c55e' }}>{orderFlow.vah != null ? fmtPrice2(orderFlow.vah) : '—'}</span></span>
          <span>VAL <span style={{ color: '#ef4444' }}>{orderFlow.val != null ? fmtPrice2(orderFlow.val) : '—'}</span></span>
          <span style={{ marginLeft: 'auto', color: '#22c55e' }}>● CTRADER LIVE TICKS</span>
        </div>
      )}

      {/* Probability bar */}
      <div className="flex h-2 overflow-hidden">
        <div style={{ width: `${bull}%`, background: '#22c55e', transition: 'width 0.8s ease' }} />
        <div style={{ width: `${100 - bull - bear}%`, background: '#94a3b8', transition: 'width 0.8s ease' }} />
        <div style={{ width: `${bear}%`, background: '#ef4444', transition: 'width 0.8s ease' }} />
      </div>
      <div className="flex justify-between" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
        <span style={{ color: '#22c55e' }}>BULL {bull.toFixed(0)}%</span>
        <span>NEUT {(100 - bull - bear).toFixed(0)}%</span>
        <span style={{ color: '#ef4444' }}>BEAR {bear.toFixed(0)}%</span>
      </div>
    </div>
  )
}
