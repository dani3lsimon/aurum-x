'use client'
import { Forecast, RegimeInfo } from '@/lib/types'

interface Props { forecast: Forecast | null; regimeData?: RegimeInfo }

const REGIME_COLORS: Record<string, string> = {
  inflation_shock:        '#ff7744',
  disinflation:           '#60a5fa',
  recession_risk:         '#fbbf24',
  growth_expansion:       '#22c55e',
  liquidity_expansion:    '#2dd4bf',
  liquidity_contraction:  '#ef4444',
  rate_hike_cycle:        '#ef4444',
  rate_cut_cycle:         '#ffb347',
  geopolitical_crisis:    '#c084fc',
  risk_off:               '#ffb347',
  unknown:                '#4a5068',
}

const REGIME_DESC: Record<string, string> = {
  inflation_shock:        'Accelerating inflation — safe haven demand',
  disinflation:           'Falling inflation — gold premium reducing',
  recession_risk:         'Growth concerns — safe haven flows active',
  growth_expansion:       'Risk-on — capital rotating away from gold',
  liquidity_expansion:    'Central bank easing — supportive for gold',
  liquidity_contraction:  'Tightening conditions — gold headwind',
  rate_hike_cycle:        'Rising rates — opportunity cost rising',
  rate_cut_cycle:         'Easing cycle — historically bullish gold',
  geopolitical_crisis:    'Geopolitical risk premium active',
  risk_off:               'Risk aversion — safe haven flows',
  unknown:                'Regime classification in progress',
}

export default function RegimeClassifier({ forecast, regimeData }: Props) {
  const regime     = regimeData?.regime || forecast?.macro_regime || 'unknown'
  const confidence = regimeData?.confidence || 0
  const stable     = regimeData?.blocked_by_hysteresis === false

  const color = REGIME_COLORS[regime] || '#4a5068'
  const desc  = REGIME_DESC[regime]   || ''
  const label = regime.replace(/_/g, ' ').toUpperCase()

  return (
    <div className="aurum-card" style={{ padding: '16px', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderColor: `${color}22` }}>
      <div style={{ fontSize: '11px', color: '#4a5068', letterSpacing: '0.18em', marginBottom: '10px' }}>
        MACRO REGIME
      </div>

      <div style={{
        fontSize: 'clamp(1.2rem, 2vw, 1.8rem)',
        fontWeight: 800,
        color,
        letterSpacing: '0.06em',
        lineHeight: 1.2,
        marginBottom: '8px',
      }}>
        {label}
      </div>

      <div style={{ fontSize: '12px', color: '#6b7494', lineHeight: 1.5, letterSpacing: '0.04em', flex: 1 }}>
        {desc}
      </div>

      <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '11px', color: '#4a5068', letterSpacing: '0.1em' }}>
          {confidence > 0 ? `${confidence.toFixed(0)}% CONF` : ''}
          {stable ? ' · ✓ STABLE' : ''}
        </div>
        <div style={{ fontSize: '11px', color: '#4a5068', letterSpacing: '0.1em' }}>
          24H ROLLING
        </div>
      </div>
    </div>
  )
}
