'use client'
import { Forecast } from '@/lib/types'

interface Props { forecast: Forecast | null }

const HORIZONS = [
  { label: '4H',  low: 'range_4h_low',  high: 'range_4h_high'  },
  { label: '24H', low: 'range_24h_low', high: 'range_24h_high' },
  { label: '1W',  low: 'range_1w_low',  high: 'range_1w_high'  },
  { label: '1M',  low: 'range_1m_low',  high: 'range_1m_high'  },
  { label: '1Q',  low: 'range_1q_low',  high: 'range_1q_high'  },
] as const

export default function ForecastRanges({ forecast }: Props) {
  const price = forecast?.gold_price ?? 0
  const vol   = forecast?.volatility_score ?? 50

  return (
    <div className="aurum-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="section-label">Price Range Forecast</div>
        <div className="text-xs text-[var(--text-muted)]">VOL {vol.toFixed(0)}</div>
      </div>

      <div className="flex flex-col gap-2">
        {HORIZONS.map(({ label, low, high }) => {
          const lo = forecast?.[low] ?? 0
          const hi = forecast?.[high] ?? 0
          const mid = (lo + hi) / 2
          const bias = price > 0 ? ((mid - price) / price) * 100 : 0

          return (
            <div key={label} className="flex items-center gap-3">
              <div className="text-xs font-bold text-[var(--accent-primary)] w-6 shrink-0">{label}</div>

              <div className="flex-1 flex flex-col gap-0.5">
                <div className="flex justify-between" style={{ fontSize: '0.72rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>${lo.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
                  <span style={{ color: bias > 0 ? '#22c55e' : bias < 0 ? '#ef4444' : 'var(--text-muted)' }}>
                    {bias > 0 ? '+' : ''}{bias.toFixed(1)}%
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>${hi.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
                </div>
                <div className="h-1 bg-[rgba(255,255,255,0.04)] relative overflow-hidden">
                  {lo > 0 && hi > 0 && price > 0 && (
                    <div
                      className="absolute h-full"
                      style={{
                        left: '0%',
                        right: '0%',
                        background: `linear-gradient(90deg, #ef444440, #ff440060, #22c55e40)`,
                      }}
                    />
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="border-t border-[var(--border-subtle)] pt-2 flex justify-between text-[var(--text-muted)]" style={{ fontSize: '0.72rem' }}>
        <span>CURRENT <span className="text-white">${price.toLocaleString()}</span></span>
        <span>VOL SCORE <span className="text-[var(--accent-amber)]">{vol.toFixed(0)}/100</span></span>
      </div>
    </div>
  )
}
