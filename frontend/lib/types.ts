export interface Forecast {
  id: string
  timestamp: string
  gold_price: number
  bullish_prob: number
  bearish_prob: number
  neutral_prob: number
  confidence_score: number
  forecast_momentum: number
  macro_regime: string
  agent_scores: Record<string, number>
  range_4h_low: number;  range_4h_high: number
  range_24h_low: number; range_24h_high: number
  range_1w_low: number;  range_1w_high: number
  range_1m_low: number;  range_1m_high: number
  range_1q_low: number;  range_1q_high: number
  volatility_score: number
  tail_risk_upside: number
  tail_risk_downside: number
  tail_risk_probability: number
}

export interface AgentScore {
  agent_name: string
  score: number
  confidence: number
  rationale: string
  timestamp: string
  regime: string
}

export interface Scenario {
  id: string
  scenario_label: string
  scenario_name: string
  probability: number
  expected_gold_target: number
  confidence: number
  key_drivers: string[]
  horizon?: string
}

export interface Alert {
  id: string
  timestamp: string
  alert_type: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  title: string
  description: string
  acknowledged: boolean
}

export interface EconomicRelease {
  id: string
  event: string
  country: string
  release_date: string
  actual: number | null
  forecast: number | null
  previous: number | null
  surprise: number | null
  impact: 'low' | 'medium' | 'high'
  gold_sensitivity: 'low' | 'medium' | 'high' | 'critical'
  gold_impact_score: number | null
}

export interface ShortScoreCondition {
  short_met: boolean
  long_met: boolean
  direction: 'short' | 'long' | 'neutral'
  points: number
  value: string | number | null
  threshold: string
  source: string
}

export interface ShortScorePreCondition {
  pass: boolean
  value: string
}

export interface SpreadInfo {
  current_spread: number | null
  threshold: number
  acceptable: boolean
  account_type: string
  note: string
}

export type NetSignal =
  | 'HIGH CONVICTION LONG'
  | 'HIGH CONVICTION SHORT'
  | 'POTENTIAL SCALP LONG'
  | 'POTENTIAL SCALP SHORT'
  | 'CONFLICTING SIGNALS'
  | 'NO TRADE'
  | 'BLOCKED'

export interface ShortScore {
  // Long side
  long_score: number
  long_raw: number
  long_conditions_met: number

  // Short side
  short_score: number
  short_raw: number
  short_conditions_met: number

  // Net signal
  net_signal: NetSignal
  net_color: 'red' | 'amber' | 'green' | 'gray'
  go_long: boolean
  go_short: boolean
  scalp_long: boolean
  scalp_short: boolean

  // Shared
  max_score: number
  total_conditions: number
  conditions: Record<string, ShortScoreCondition>
  pre_conditions: Record<string, ShortScorePreCondition>
  pre_conditions_pass: boolean
  spread_info: SpreadInfo
  data_sources_live: string[]
  data_sources_missing: string[]
  timestamp: string

  // Backwards-compat aliases (old single-direction shape)
  short_setup_score: number
  raw_score: number
  conditions_met: number
  signal: NetSignal
  signal_color: 'red' | 'amber' | 'green' | 'gray'
  go: boolean
  scalp: boolean
}

export interface WSMessage {
  type: 'forecast_update' | 'agent_update' | 'alert' | 'regime_change' | 'initial_state' | 'release_alert' | 'short_score_update'
  data: unknown
}
