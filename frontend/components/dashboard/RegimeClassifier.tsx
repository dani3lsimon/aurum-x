'use client'
import { Forecast } from '@/lib/types'

interface Props { forecast: Forecast | null }

const REGIME_CONFIG: Record<string, { color: string; bg: string; label: string; desc: string }> = {
  inflation_shock:       { color: '#ff4400', bg: 'rgba(255,68,0,0.12)',    label: 'INFLATION SHOCK',      desc: 'High CPI — Gold bullish' },
  disinflation:          { color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)',  label: 'DISINFLATION',         desc: 'Falling inflation — Mixed' },
  recession_risk:        { color: '#ff4d7a', bg: 'rgba(255,77,122,0.12)', label: 'RECESSION RISK',        desc: 'Growth slowdown — Gold bullish' },
  growth_expansion:      { color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', label: 'GROWTH EXPANSION',      desc: 'Risk-on — Gold bearish' },
  liquidity_expansion:   { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  label: 'LIQUIDITY EXPANSION',   desc: 'QE/stimulus — Gold bullish' },
  liquidity_contraction: { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  label: 'LIQUIDITY CONTRACTION', desc: 'QT active — Gold bearish' },
  rate_hike_cycle:       { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  label: 'RATE HIKE CYCLE',       desc: 'Tightening — Gold bearish' },
  rate_cut_cycle:        { color: '#22c55e', bg: 'rgba(34,197,94,0.12)',  label: 'RATE CUT CYCLE',        desc: 'Easing — Gold bullish' },
  geopolitical_crisis:   { color: '#ffb347', bg: 'rgba(255,179,71,0.12)', label: 'GEOPOLITICAL CRISIS',   desc: 'Safe haven demand — Gold bullish' },
  risk_off:              { color: '#ffb347', bg: 'rgba(255,179,71,0.12)', label: 'RISK OFF',              desc: 'Flight to safety — Gold bullish' },
  unknown:               { color: '#4a5068', bg: 'rgba(74,80,104,0.1)',   label: 'REGIME UNKNOWN',        desc: 'Insufficient data' },
}

export default function RegimeClassifier({ forecast }: Props) {
  const regime = forecast?.macro_regime ?? 'unknown'
  const cfg = REGIME_CONFIG[regime] ?? REGIME_CONFIG['unknown']

  return (
    <div className="aurum-card p-4 flex flex-col gap-3">
      <div className="section-label">Macro Regime</div>

      {/* Active regime highlight */}
      <div className="p-3 flex flex-col gap-2" style={{ background: cfg.bg, border: `1px solid ${cfg.color}50` }}>
        <div style={{ color: cfg.color, fontSize: '0.8rem', fontWeight: 700, letterSpacing: '0.12em' }}>
          {cfg.label}
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem', textTransform: 'none', lineHeight: 1.4 }}>
          {cfg.desc}
        </div>
      </div>

      {/* All regimes — single column, readable */}
      <div className="flex flex-col gap-1">
        {Object.entries(REGIME_CONFIG)
          .filter(([k]) => k !== 'unknown')
          .map(([key, c]) => {
            const isActive = key === regime
            return (
              <div
                key={key}
                className="flex items-center gap-2 px-2 py-1"
                style={{
                  background: isActive ? c.bg : 'transparent',
                  border: `1px solid ${isActive ? c.color + '50' : 'transparent'}`,
                }}
              >
                <div
                  className="shrink-0"
                  style={{
                    width: '6px', height: '6px', borderRadius: '50%',
                    background: isActive ? c.color : '#2a2d3a',
                    boxShadow: isActive ? `0 0 6px ${c.color}` : 'none',
                  }}
                />
                <div style={{
                  color: isActive ? c.color : '#4a5068',
                  fontSize: '0.68rem',
                  letterSpacing: '0.08em',
                  fontWeight: isActive ? 600 : 400,
                }}>
                  {c.label}
                </div>
              </div>
            )
          })}
      </div>
    </div>
  )
}
