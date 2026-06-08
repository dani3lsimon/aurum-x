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
  raw_data?: {
    key_factors?: string[]
    directional_bias?: string
    signal_strength?: string
    data_quality?: string
    notable_risk?: string
    [key: string]: unknown
  }
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

export interface RegimeInfo {
  regime: string
  confidence: number
  blocked_by_hysteresis?: boolean
  method?: string
  sample_size?: number
  window_hours?: number
  challenger?: string | null
  top_labels?: Record<string, number>
}

export interface PositionSizing {
  risk_pct: number
  risk_usd?: number
  vix: number | null
  label?: string
  note: string
  account_size?: number
}

export interface ShortScoreThresholds {
  high_conviction: number
  scalp: number
  vix: number | null
  note: string
}

export interface DecayFactors {
  price?: number
  delta?: number
  vwap?: number
  data_timestamp?: string | null
  note?: string
}

export interface RegimeWeightAdjustment {
  base_weight: number
  regime_modifier: number
  decay_applied: number
  effective_weight: number
}

export interface CalibrationInfo {
  status: string
  bars_used?: number
  gold_std_1h?: number
  gold_std_4h?: number
  significant_dxy_move?: number
  calibrated_at?: string
  [key: string]: unknown
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
  cot_directional_filter?: {
    is_extreme_long: boolean
    is_extreme_short: boolean
    long_suppressed: boolean
    short_suppressed: boolean
    note: string
  }
  spread_info: SpreadInfo
  data_sources_live: string[]
  data_sources_missing: string[]
  timestamp: string

  // Signal-quality layers
  decay_factors?: DecayFactors
  current_regime?: string
  regime_info?: RegimeInfo
  regime_weight_adjustments?: Record<string, RegimeWeightAdjustment>
  interaction_bonus?: number
  interaction_note?: string
  thresholds?: ShortScoreThresholds
  calibration?: CalibrationInfo
  position_sizing?: PositionSizing

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
  type: 'forecast_update' | 'agent_update' | 'alert' | 'regime_change' | 'initial_state' | 'release_alert' | 'short_score_update' | 'multi_tf_update'
  data: unknown
}

// ── Multi-timeframe engine + price-action chart ────────────────────────────

export interface OHLCVBar {
  time:     string
  open:     number
  high:     number
  low:      number
  close:    number
  volume:   number
  complete: boolean
}

export interface OrderFlowData {
  status?: string
  source?: string
  instrument?: string
  current_price?: number
  bid?: number
  ask?: number
  spread?: number
  spread_ok?: boolean
  session_vwap?: number
  vwap_15min?: number
  price_vs_vwap?: number
  vwap_signal?: string
  cumulative_delta?: number
  delta_direction?: string
  delta_momentum?: string
  poc_price?: number
  vah?: number
  val?: number
  prior_session_low?: number
  prior_session_high?: number
  [key: string]: unknown
}

export interface TfCondition {
  short_met: boolean
  long_met:  boolean
  value:     string
}

export interface TfScore {
  short_pct:        number
  long_pct:         number
  short_raw:        number
  long_raw:         number
  atr:              number
  vwap:             number
  delta:            number
  current_price?:   number
  break_direction?: string
  granularity?:     string
  error?:           string
  conditions:       Record<string, TfCondition>
}

export interface MultiTfSignal {
  timestamp:        string
  best_signal:      string
  best_timeframe:   string | null
  best_direction:   string
  conviction:       string | null
  edge_strength:    number
  risk_pct:         number
  stop_loss:        number | null
  vix:              number
  hc_threshold?:    number
  scalp_threshold?: number
  timeframes:       Record<string, TfScore>
  shared_inputs?:   Record<string, unknown>
  entry_price?:    number
  atr?:            number
  risk_distance?:  number
  risk_usd?:       number
  position_size_oz?: number
  take_profits?: {
    tp1: { price: number; rr_ratio: string; action: string; reward_usd: number }
    tp2: { price: number; rr_ratio: string; action: string; reward_usd: number }
    tp3: { price: number; rr_ratio: string; action: string; reward_usd: number }
  }
  expected_move?: {
    direction:    string
    min_pts:      number
    max_pts:      number
    prob_tp1:     number
    prob_tp2:     number
    prob_tp3:     number
    note:         string
  }
}
