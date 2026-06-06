'use client'
import { useEffect, useRef, useState } from 'react'
import { Forecast } from '@/lib/types'

interface Props { forecast: Forecast | null; history?: Forecast[] }

const TABS = ['4H', '24H', '1W', '1M', '1Q'] as const
type Tab = typeof TABS[number]

const RANGE_KEYS: Record<Tab, { low: keyof Forecast; high: keyof Forecast }> = {
  '4H':  { low: 'range_4h_low',  high: 'range_4h_high'  },
  '24H': { low: 'range_24h_low', high: 'range_24h_high' },
  '1W':  { low: 'range_1w_low',  high: 'range_1w_high'  },
  '1M':  { low: 'range_1m_low',  high: 'range_1m_high'  },
  '1Q':  { low: 'range_1q_low',  high: 'range_1q_high'  },
}

export default function ForecastChart({ forecast }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [tab, setTab] = useState<Tab>('24H')
  const animRef = useRef<number>(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const W = canvas.width  = canvas.offsetWidth
    const H = canvas.height = canvas.offsetHeight

    const price   = forecast?.gold_price ?? 3300
    const bull    = forecast?.bullish_prob ?? 34
    const bear    = forecast?.bearish_prob ?? 33
    const rangeK  = RANGE_KEYS[tab]
    const lo      = (forecast?.[rangeK.low]  as number) || price * 0.97
    const hi      = (forecast?.[rangeK.high] as number) || price * 1.03
    const bias    = (bull - bear) / 100

    // Generate simulated price path
    const points = 80
    const padding = { top: 20, bottom: 30, left: 8, right: 8 }
    const chartH = H - padding.top - padding.bottom
    const chartW = W - padding.left - padding.right

    const priceRange = hi - lo
    const midPrice   = (lo + hi) / 2

    const path: { x: number; y: number }[] = []
    let cur = price
    for (let i = 0; i <= points; i++) {
      const t    = i / points
      const x    = padding.left + t * chartW
      const trend = bias * priceRange * t * 0.6
      const noise = (Math.random() - 0.5) * priceRange * 0.08
      cur = cur + trend / points + noise
      cur = Math.max(lo * 0.98, Math.min(hi * 1.02, cur))
      const norm = (cur - (midPrice - priceRange * 0.7)) / (priceRange * 1.4)
      const y    = padding.top + (1 - Math.max(0, Math.min(1, norm))) * chartH
      path.push({ x, y })
    }

    // Animate draw left-to-right
    let progress = 0
    const DURATION = 120

    const draw = () => {
      ctx.clearRect(0, 0, W, H)

      // Background range band
      const grad = ctx.createLinearGradient(0, padding.top, 0, H - padding.bottom)
      grad.addColorStop(0, 'rgba(255,80,0,0.08)')
      grad.addColorStop(1, 'rgba(180,0,0,0.01)')
      const yHi = padding.top + (1 - (hi - (midPrice - priceRange * 0.7)) / (priceRange * 1.4)) * chartH
      const yLo = padding.top + (1 - (lo - (midPrice - priceRange * 0.7)) / (priceRange * 1.4)) * chartH
      ctx.fillStyle = grad
      ctx.fillRect(padding.left, yHi, chartW, yLo - yHi)

      // Grid lines
      ctx.strokeStyle = 'rgba(240,13,23,0.08)'
      ctx.lineWidth   = 1
      for (let g = 0; g <= 4; g++) {
        const gy = padding.top + (g / 4) * chartH
        ctx.beginPath(); ctx.moveTo(padding.left, gy); ctx.lineTo(W - padding.right, gy); ctx.stroke()
      }

      // Price path — animated clip
      const visibleCount = Math.floor(progress * path.length)
      if (visibleCount < 2) { progress++; animRef.current = requestAnimationFrame(draw); return }

      // Fill under curve
      const fillGrad = ctx.createLinearGradient(0, padding.top, 0, H)
      fillGrad.addColorStop(0, 'rgba(255,80,0,0.7)')
      fillGrad.addColorStop(1, 'rgba(180,0,0,0.0)')

      ctx.beginPath()
      ctx.moveTo(path[0].x, H - padding.bottom)
      ctx.lineTo(path[0].x, path[0].y)
      for (let i = 1; i < visibleCount; i++) {
        ctx.lineTo(path[i].x, path[i].y)
      }
      ctx.lineTo(path[visibleCount - 1].x, H - padding.bottom)
      ctx.closePath()
      ctx.fillStyle = fillGrad
      ctx.fill()

      // Glow line
      ctx.shadowColor  = '#ff5500'
      ctx.shadowBlur   = 12
      ctx.strokeStyle  = '#ff5500'
      ctx.lineWidth    = 2
      ctx.lineJoin     = 'round'
      ctx.beginPath()
      ctx.moveTo(path[0].x, path[0].y)
      for (let i = 1; i < visibleCount; i++) {
        ctx.lineTo(path[i].x, path[i].y)
      }
      ctx.stroke()
      ctx.shadowBlur = 0

      // Price labels
      ctx.fillStyle = 'rgba(107,116,148,0.9)'
      ctx.font      = '9px JetBrains Mono, monospace'
      ctx.fillText(`$${hi.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, padding.left + 2, yHi + 10)
      ctx.fillText(`$${lo.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, padding.left + 2, yLo - 4)

      // Current price dot
      if (visibleCount >= 1) {
        const lastPt = path[visibleCount - 1]
        ctx.beginPath()
        ctx.arc(lastPt.x, lastPt.y, 3, 0, Math.PI * 2)
        ctx.fillStyle = '#ff5500'
        ctx.shadowColor = '#ff5500'
        ctx.shadowBlur  = 8
        ctx.fill()
        ctx.shadowBlur = 0
      }

      if (progress < DURATION) {
        progress++
        animRef.current = requestAnimationFrame(draw)
      }
    }

    cancelAnimationFrame(animRef.current)
    progress = 0
    animRef.current = requestAnimationFrame(draw)

    return () => cancelAnimationFrame(animRef.current)
  }, [forecast, tab])

  const bull = forecast?.bullish_prob ?? 34
  const bear = forecast?.bearish_prob ?? 33

  return (
    <div className="aurum-card p-4 flex flex-col gap-3 h-full">
      <div className="flex items-center justify-between">
        <div className="section-label">Price Forecast Chart</div>
        <div className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="px-2 py-0.5 text-xs transition-all"
              style={{
                background:   tab === t ? 'rgba(240,13,23,0.2)' : 'transparent',
                border:       `1px solid ${tab === t ? 'rgba(240,13,23,0.5)' : 'rgba(240,13,23,0.15)'}`,
                color:        tab === t ? '#ff4400' : '#4a5068',
                borderRadius: '2px',
                cursor:       'pointer',
                fontFamily:   "'JetBrains Mono', monospace",
                fontSize:     '0.55rem',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <canvas
        ref={canvasRef}
        className="w-full flex-1"
        style={{ minHeight: '140px', display: 'block' }}
      />

      {/* Probability flow bar */}
      <div className="flex h-2 overflow-hidden" style={{ borderRadius: 0 }}>
        <div style={{ width: `${bull}%`, background: '#22c55e', transition: 'width 0.8s ease' }} />
        <div style={{ width: `${100 - bull - bear}%`, background: '#94a3b8', transition: 'width 0.8s ease' }} />
        <div style={{ width: `${bear}%`, background: '#ef4444', transition: 'width 0.8s ease' }} />
      </div>
      <div className="flex justify-between text-xs text-[var(--text-muted)]" style={{ fontSize: '0.5rem' }}>
        <span className="text-[#22c55e]">BULL {bull.toFixed(0)}%</span>
        <span>NEUT {(100 - bull - bear).toFixed(0)}%</span>
        <span className="text-[#ef4444]">BEAR {bear.toFixed(0)}%</span>
      </div>
    </div>
  )
}
