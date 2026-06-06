'use client'
import { Forecast } from '@/lib/types'

interface Props { forecast: Forecast | null; isRefreshing?: boolean }

export default function ProbabilityGauge({ forecast, isRefreshing }: Props) {
  const bull = forecast?.bullish_prob ?? 33
  const bear = forecast?.bearish_prob ?? 33
  const neut = forecast?.neutral_prob ?? 34
  const conf = forecast?.confidence_score ?? 0
  const mom  = forecast?.forecast_momentum ?? 0

  const dominant = bull > bear && bull > neut ? 'BULLISH'
    : bear > bull && bear > neut ? 'BEARISH' : 'NEUTRAL'
  const domColor = dominant === 'BULLISH' ? '#22c55e'
    : dominant === 'BEARISH' ? '#ef4444' : '#94a3b8'

  return (
    <div className="aurum-card p-4 flex flex-col gap-3" style={{
      border: isRefreshing ? '1px solid rgba(255,80,0,0.6)' : '1px solid var(--border-subtle)',
      transition: 'border-color 0.3s ease',
      animation: isRefreshing ? 'glowPulse 1s ease-in-out infinite' : 'cardMount 0.4s ease-out forwards',
    }}>
      <div className="section-label">Probability Distribution</div>

      {/* Big dominant readout */}
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs text-[var(--text-label)] mb-1">Primary Signal</div>
          <div className="hero-number text-4xl" style={{ color: domColor }}>
            {dominant === 'BULLISH' ? bull.toFixed(1) : dominant === 'BEARISH' ? bear.toFixed(1) : neut.toFixed(1)}
            <span className="text-lg ml-1">%</span>
          </div>
          <div className="text-xs mt-1" style={{ color: domColor }}>{dominant}</div>
        </div>
        <div className="text-right">
          <div className="text-xs text-[var(--text-label)] mb-1">Confidence</div>
          <div className="text-2xl font-bold text-[var(--accent-amber)]">{conf.toFixed(0)}%</div>
          <div className="text-xs text-[var(--text-label)] mt-1">
            {mom > 0 ? '+' : ''}{mom.toFixed(1)} MOM
          </div>
        </div>
      </div>

      {/* Three bars */}
      <div className="flex flex-col gap-2">
        {[
          { label: 'BULL', val: bull, cls: 'bull', color: '#22c55e' },
          { label: 'BEAR', val: bear, cls: 'bear', color: '#ef4444' },
          { label: 'NEUT', val: neut, cls: 'neut', color: '#94a3b8' },
        ].map(({ label, val, color }) => (
          <div key={label}>
            <div className="flex justify-between text-xs mb-1">
              <span style={{ color }}>{label}</span>
              <span style={{ color }}>{val.toFixed(1)}%</span>
            </div>
            <div className="prob-bar">
              <div
                className="prob-bar-fill"
                style={{ width: `${val}%`, background: color }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Status pills */}
      <div className="flex gap-2 flex-wrap mt-1">
        <span className={`status-pill ${dominant === 'BULLISH' ? 'bull' : dominant === 'BEARISH' ? 'bear' : 'neut'}`}>
          ● {dominant}
        </span>
        <span className="status-pill conf">CONF {conf.toFixed(0)}%</span>
      </div>
    </div>
  )
}
