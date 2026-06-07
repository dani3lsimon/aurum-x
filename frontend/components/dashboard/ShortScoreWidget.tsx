'use client'
import { ShortScore } from '@/lib/types'

interface Props {
  shortScore: ShortScore | null
}

const SIGNAL_COLORS: Record<string, string> = {
  red:   '#ef4444',
  amber: '#f59e0b',
  green: '#22c55e',
  gray:  '#6b7280',
}

const CONDITION_LABELS: Record<string, string> = {
  dxy_rising:            'Dollar (DXY) Rising',
  real_yield_rising:     'Real Yields Rising',
  price_below_vwap:      'Price Below VWAP',
  negative_delta:        'Negative Order-Flow Delta',
  cot_bearish_trend:     'COT 8-Week Trend Bearish',
  no_imminent_news:      'No Imminent High-Impact News',
  options_gamma_bearish: 'Options Gamma Bearish',
  etf_outflows:          'Gold ETF Outflows',
  risk_on_equities:      'Risk-On Equities',
  price_breaks_support:  'Price Breaks Support (VAL)',
}

export default function ShortScoreWidget({ shortScore }: Props) {
  const score      = shortScore?.short_setup_score ?? 0
  const signal     = shortScore?.signal ?? 'NO TRADE'
  const colorKey   = shortScore?.signal_color ?? 'gray'
  const glowColor  = SIGNAL_COLORS[colorKey] ?? SIGNAL_COLORS.gray
  const go         = shortScore?.go ?? false
  const conditions = shortScore?.conditions ?? {}
  const preConds   = shortScore?.pre_conditions ?? {}
  const blocked    = shortScore?.signal === 'BLOCKED'
  const live       = shortScore?.data_sources_live ?? []
  const missing    = shortScore?.data_sources_missing ?? []

  const conditionEntries = Object.entries(conditions)

  return (
    <div className="aurum-card p-4 flex flex-col gap-3" style={{
      border: `1px solid ${blocked ? 'var(--border-subtle)' : `${glowColor}33`}`,
      transition: 'border-color 0.3s ease',
      animation: 'cardMount 0.4s ease-out forwards',
    }}>
      <div className="flex items-center justify-between">
        <div className="section-label">Short-Setup Score Engine</div>
        {go && (
          <span
            className="status-pill"
            style={{
              color: '#fff',
              background: glowColor,
              animation: 'glowPulse 1.2s ease-in-out infinite',
            }}
          >
            ● GO
          </span>
        )}
      </div>

      {/* Big gauge readout */}
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs text-[var(--text-label)] mb-1">Confluence Score</div>
          <div
            className="hero-number text-4xl"
            style={{ color: glowColor, textShadow: `0 0 18px ${glowColor}66` }}
          >
            {score.toFixed(1)}
            <span className="text-lg ml-1">%</span>
          </div>
          <div className="text-xs mt-1 font-bold" style={{ color: glowColor }}>{signal}</div>
        </div>
        <div className="text-right">
          <div className="text-xs text-[var(--text-label)] mb-1">Conditions Met</div>
          <div className="text-2xl font-bold text-[var(--accent-amber)]">
            {shortScore?.conditions_met ?? 0}/{shortScore?.total_conditions ?? 10}
          </div>
          <div className="text-xs text-[var(--text-label)] mt-1">
            raw {shortScore?.raw_score ?? 0} / {shortScore?.max_score ?? 14}
          </div>
        </div>
      </div>

      {/* Horizontal gauge bar with 40%/70% zone markers */}
      <div className="flex flex-col gap-1">
        <div style={{ position: 'relative', height: '10px', background: 'rgba(255,255,255,0.06)', borderRadius: '5px', overflow: 'hidden' }}>
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0,
            width: `${Math.min(100, Math.max(0, score))}%`,
            background: glowColor,
            transition: 'width 0.5s ease',
          }} />
          {/* 40% zone marker */}
          <div style={{ position: 'absolute', left: '40%', top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.35)' }} />
          {/* 70% zone marker */}
          <div style={{ position: 'absolute', left: '70%', top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.35)' }} />
        </div>
        <div className="flex justify-between text-[10px] text-[var(--text-label)]">
          <span>0%</span>
          <span style={{ position: 'relative', left: '-12px' }}>40% — scalp</span>
          <span style={{ position: 'relative', left: '6px' }}>70% — high conviction</span>
          <span>100%</span>
        </div>
      </div>

      {/* BLOCKED warning banner */}
      {blocked && (
        <div className="text-xs px-3 py-2 rounded" style={{
          background: 'rgba(107,114,128,0.15)',
          border: '1px solid rgba(107,114,128,0.4)',
          color: '#9ca3af',
        }}>
          ⛔ <span className="font-bold">SIGNAL BLOCKED</span> — one or more pre-conditions failed.
          No short signal fires regardless of confluence score until the safety net clears.
        </div>
      )}

      {/* Pre-conditions row */}
      <div className="flex flex-col gap-1">
        <div className="text-xs text-[var(--text-label)]">Pre-Conditions (hard filters)</div>
        <div className="flex flex-col gap-1">
          {Object.entries(preConds).map(([key, pc]) => (
            <div key={key} className="flex items-center justify-between text-xs px-2 py-1 rounded" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <span className="flex items-center gap-2">
                <span style={{
                  display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%',
                  background: pc.pass ? '#22c55e' : '#ef4444',
                }} />
                <span className="text-[var(--text-secondary)]">{key.replace(/_/g, ' ')}</span>
              </span>
              <span className="text-[var(--text-label)]" style={{ maxWidth: '60%', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {pc.value}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 10-condition grid: 2 cols x 5 rows */}
      <div className="grid grid-cols-2 gap-2">
        {conditionEntries.map(([key, c]) => {
          const dotColor = c.met ? '#22c55e' : '#6b7280'
          return (
            <div key={key} className="flex flex-col gap-0.5 px-2 py-1.5 rounded" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div className="flex items-center gap-2">
                <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
                <span className="text-xs text-[var(--text-secondary)]" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {CONDITION_LABELS[key] ?? key}
                </span>
                <span className="text-[10px] ml-auto text-[var(--accent-amber)]">+{c.points}</span>
              </div>
              <div className="text-[10px] text-[var(--text-label)]" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {String(c.value ?? 'unavailable')}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                threshold: {c.threshold} · src: {c.source}
              </div>
            </div>
          )
        })}
      </div>

      {/* Data sources live / missing — honest audit trail */}
      <div className="flex flex-col gap-1 text-[10px]">
        <div className="flex flex-wrap gap-1 items-center">
          <span className="text-[var(--text-label)]">LIVE:</span>
          {live.length > 0 ? live.map(s => (
            <span key={s} className="status-pill" style={{ color: '#22c55e', borderColor: 'rgba(34,197,94,0.3)', background: 'rgba(34,197,94,0.08)' }}>{s}</span>
          )) : <span className="text-[var(--text-muted)]">none</span>}
        </div>
        <div className="flex flex-wrap gap-1 items-center">
          <span className="text-[var(--text-label)]">MISSING:</span>
          {missing.length > 0 ? missing.map(s => (
            <span key={s} className="status-pill" style={{ color: '#9ca3af', borderColor: 'rgba(156,163,175,0.3)', background: 'rgba(156,163,175,0.08)' }}>{s}</span>
          )) : <span className="text-[var(--text-muted)]">none — full data coverage</span>}
        </div>
      </div>

      {shortScore?.timestamp && (
        <div className="text-[10px] text-[var(--text-muted)] text-right">
          updated {new Date(shortScore.timestamp).toLocaleTimeString()}
        </div>
      )}
    </div>
  )
}
