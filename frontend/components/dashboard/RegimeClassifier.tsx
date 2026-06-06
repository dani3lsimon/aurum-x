'use client'
import { Forecast } from '@/lib/types'

interface Props { forecast: Forecast | null }

const REGIME_CONFIG: Record<string, { color: string; bg: string; label: string; desc: string }> = {
  inflation_shock:       { color: '#ff4400', bg: 'rgba(255,68,0,0.12)',    label: 'INFLATION SHOCK',       desc: 'High CPI — Gold bullish' },
  disinflation:          { color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)',  label: 'DISINFLATION',          desc: 'Falling inflation — Mixed' },
  recession_risk:        { color: '#ff4d7a', bg: 'rgba(255,77,122,0.12)', label: 'RECESSION RISK',         desc: 'Growth slowdown — Gold bullish' },
  growth_expansion:      { color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', label: 'GROWTH EXPANSION',       desc: 'Risk-on — Gold bearish' },
  liquidity_expansion:   { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  label: 'LIQUIDITY EXPANSION',    desc: 'QE/stimulus — Gold bullish' },
  liquidity_contraction: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  label: 'LIQUIDITY CONTRACTION',  desc: 'QT active — Gold bearish' },
  rate_hike_cycle:       { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  label: 'RATE HIKE CYCLE',        desc: 'Tightening — Gold bearish' },
  rate_cut_cycle:        { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  label: 'RATE CUT CYCLE',         desc: 'Easing — Gold bullish' },
  geopolitical_crisis:   { color: '#ffb347', bg: 'rgba(255,179,71,0.12)', label: 'GEOPOLITICAL CRISIS',    desc: 'Safe haven demand — Gold bullish' },
  risk_off:              { color: '#ffb347', bg: 'rgba(255,179,71,0.12)', label: 'RISK OFF',               desc: 'Flight to safety — Gold bullish' },
  unknown:               { color: '#4a5068', bg: 'rgba(74,80,104,0.1)',   label: 'REGIME UNKNOWN',         desc: 'Insufficient data' },
}

export default function RegimeClassifier({ forecast }: Props) {
  const regime = forecast?.macro_regime ?? 'unknown'
  const cfg = REGIME_CONFIG[regime] ?? REGIME_CONFIG['unknown']

  return (
    <div className="aurum-card p-4 flex flex-col gap-3">
      <div className="section-label">Macro Regime</div>

      <div
        className="p-3 flex flex-col gap-2"
        style={{ background: cfg.bg, border: `1px solid ${cfg.color}40` }}
      >
        <div className="text-xs font-800 tracking-widest" style={{ color: cfg.color }}>
          {cfg.label}
        </div>
        <div className="text-xs text-[var(--text-muted)] normal-case" style={{ textTransform: 'none' }}>
          {cfg.desc}
        </div>
      </div>

      {/* All regimes grid */}
      <div className="grid grid-cols-2 gap-1">
        {Object.entries(REGIME_CONFIG)
          .filter(([k]) => k !== 'unknown')
          .map(([key, c]) => (
            <div
              key={key}
              className="flex items-center gap-1.5 px-2 py-1"
              style={{
                background: key === regime ? c.bg : 'transparent',
                border: `1px solid ${key === regime ? c.color + '60' : 'transparent'}`,
              }}
            >
              <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: key === regime ? c.color : '#4a5068' }} />
              <div className="text-xs truncate" style={{ color: key === regime ? c.color : '#4a5068', fontSize: '0.5rem' }}>
                {c.label}
              </div>
            </div>
          ))}
      </div>
    </div>
  )
}
