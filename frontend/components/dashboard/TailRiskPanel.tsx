'use client'
import { Forecast } from '@/lib/types'

interface Props { forecast: Forecast | null }

export default function TailRiskPanel({ forecast }: Props) {
  const upside   = forecast?.tail_risk_upside   ?? 0
  const downside = forecast?.tail_risk_downside ?? 0
  const prob     = forecast?.tail_risk_probability ?? 0
  const price    = forecast?.gold_price ?? 0
  const vol      = forecast?.volatility_score ?? 50

  const upsidePct  = price > 0 ? ((upside - price) / price * 100)   : 0
  const downsidePct = price > 0 ? ((downside - price) / price * 100) : 0

  return (
    <div className="aurum-card p-4 flex flex-col gap-3">
      <div className="section-label">Tail Risk Analysis</div>

      <div className="grid grid-cols-2 gap-2">
        {/* Upside tail */}
        <div className="flex flex-col gap-1 p-2" style={{ background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.2)' }}>
          <div style={{ color: '#22c55e', fontSize: '0.75rem', fontWeight: 600 }}>UPSIDE TAIL</div>
          <div className="text-xl font-bold text-[#22c55e]">
            ${upside > 0 ? upside.toLocaleString('en-US', { maximumFractionDigits: 0 }) : '---'}
          </div>
          <div className=" text-[#22c55e80]">
            {upsidePct > 0 ? '+' : ''}{upsidePct.toFixed(1)}% from spot
          </div>
        </div>

        {/* Downside tail */}
        <div className="flex flex-col gap-1 p-2" style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <div style={{ color: '#ef4444', fontSize: '0.75rem', fontWeight: 600 }}>DOWNSIDE TAIL</div>
          <div className="text-xl font-bold text-[#ef4444]">
            ${downside > 0 ? downside.toLocaleString('en-US', { maximumFractionDigits: 0 }) : '---'}
          </div>
          <div className=" text-[#ef444480]">
            {downsidePct.toFixed(1)}% from spot
          </div>
        </div>
      </div>

      {/* Tail probability */}
      <div className="flex flex-col gap-1">
        <div className="flex justify-between" style={{ fontSize: '0.75rem' }}>
          <span className="text-[var(--text-label)]">TAIL EVENT PROBABILITY</span>
          <span className="text-[var(--accent-amber)] font-bold">{prob.toFixed(1)}%</span>
        </div>
        <div className="prob-bar">
          <div className="prob-bar-fill" style={{ width: `${Math.min(prob * 3, 100)}%`, background: '#ffb347' }} />
        </div>
      </div>

      {/* Volatility score */}
      <div className="flex flex-col gap-1">
        <div className="flex justify-between" style={{ fontSize: '0.75rem' }}>
          <span className="text-[var(--text-label)]">VOLATILITY SCORE</span>
          <span className="font-bold" style={{ color: vol > 80 ? '#ef4444' : vol > 50 ? '#ffb347' : '#22c55e' }}>
            {vol.toFixed(0)} / 100
          </span>
        </div>
        <div className="prob-bar">
          <div
            className="prob-bar-fill"
            style={{
              width: `${vol}%`,
              background: vol > 80 ? '#ef4444' : vol > 50 ? '#ffb347' : '#22c55e'
            }}
          />
        </div>
      </div>
    </div>
  )
}
