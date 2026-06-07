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

const LONG_COLOR  = '#22c55e'
const SHORT_COLOR = '#ef4444'

const CONDITION_LABELS: Record<string, string> = {
  dxy_direction:        'Dollar (DXY) Direction',
  real_yield_direction: 'Real Yield Direction',
  price_vs_vwap:        'Price vs Session VWAP',
  cumulative_delta:     'Cumulative Order-Flow Delta',
  cot_mm_trend:         'COT Managed-Money 8W Trend',
  no_imminent_news:     'No Imminent High-Impact News',
  options_gamma:        'Options Gamma Positioning',
  etf_flows:            'Gold ETF Flows',
  risk_sentiment:       'Risk Sentiment',
  session_level_break:  'Session Level Break (Hi/Lo)',
}

function GaugeBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ position: 'relative', height: '10px', background: 'rgba(255,255,255,0.06)', borderRadius: '5px', overflow: 'hidden' }}>
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0,
        width: `${Math.min(100, Math.max(0, value))}%`,
        background: color,
        transition: 'width 0.5s ease',
      }} />
      <div style={{ position: 'absolute', left: '40%', top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.35)' }} />
      <div style={{ position: 'absolute', left: '70%', top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.35)' }} />
    </div>
  )
}

export default function ShortScoreWidget({ shortScore }: Props) {
  const longScore   = shortScore?.long_score ?? 0
  const shortScoreV = shortScore?.short_score ?? 0
  const netSignal   = shortScore?.net_signal ?? 'NO TRADE'
  const netColorKey = shortScore?.net_color ?? 'gray'
  const netColor    = SIGNAL_COLORS[netColorKey] ?? SIGNAL_COLORS.gray
  const blocked     = netSignal === 'BLOCKED'
  const goLong      = shortScore?.go_long ?? false
  const goShort     = shortScore?.go_short ?? false
  const conditions  = shortScore?.conditions ?? {}
  const preConds    = shortScore?.pre_conditions ?? {}
  const live        = shortScore?.data_sources_live ?? []
  const missing     = shortScore?.data_sources_missing ?? []
  const spreadInfo  = shortScore?.spread_info

  const longLeading  = !blocked && longScore  > shortScoreV
  const shortLeading = !blocked && shortScoreV > longScore

  const conditionEntries = Object.entries(conditions)

  return (
    <div className="aurum-card p-4 flex flex-col gap-3" style={{
      border: `1px solid ${blocked ? 'var(--border-subtle)' : `${netColor}33`}`,
      transition: 'border-color 0.3s ease',
      animation: 'cardMount 0.4s ease-out forwards',
    }}>
      <div className="flex items-center justify-between">
        <div className="section-label">Trade Confluence Score Engine</div>
        <div className="flex items-center gap-2">
          {goLong && (
            <span className="status-pill" style={{ color: '#fff', background: LONG_COLOR, animation: 'glowPulse 1.2s ease-in-out infinite' }}>
              ▲ GO LONG
            </span>
          )}
          {goShort && (
            <span className="status-pill" style={{ color: '#fff', background: SHORT_COLOR, animation: 'glowPulse 1.2s ease-in-out infinite' }}>
              ▼ GO SHORT
            </span>
          )}
        </div>
      </div>

      {/* Split dual gauge */}
      <div className="grid grid-cols-2 gap-3">
        {/* LONG panel */}
        <div className="flex flex-col gap-1.5 p-2 rounded" style={{
          background: longLeading ? 'rgba(34,197,94,0.06)' : 'rgba(255,255,255,0.02)',
          border: `1px solid ${longLeading ? 'rgba(34,197,94,0.35)' : 'rgba(255,255,255,0.05)'}`,
          opacity: blocked || shortLeading ? 0.55 : 1,
          transition: 'all 0.3s ease',
        }}>
          <div className="text-xs text-[var(--text-label)]">LONG SCORE</div>
          <div className="hero-number text-3xl" style={{ color: LONG_COLOR, textShadow: longLeading ? `0 0 18px ${LONG_COLOR}55` : 'none' }}>
            {longScore.toFixed(1)}<span className="text-base ml-1">%</span>
          </div>
          <GaugeBar value={longScore} color={LONG_COLOR} />
          <div className="flex items-center justify-between text-[10px] text-[var(--text-label)]">
            <span>{shortScore?.long_conditions_met ?? 0}/{shortScore?.total_conditions ?? 10} met</span>
            {goLong && <span className="font-bold" style={{ color: LONG_COLOR }}>▲ LONG SIGNAL</span>}
            {!goLong && shortScore?.scalp_long && <span className="font-bold" style={{ color: '#f59e0b' }}>SCALP LONG</span>}
          </div>
        </div>

        {/* SHORT panel */}
        <div className="flex flex-col gap-1.5 p-2 rounded" style={{
          background: shortLeading ? 'rgba(239,68,68,0.06)' : 'rgba(255,255,255,0.02)',
          border: `1px solid ${shortLeading ? 'rgba(239,68,68,0.35)' : 'rgba(255,255,255,0.05)'}`,
          opacity: blocked || longLeading ? 0.55 : 1,
          transition: 'all 0.3s ease',
        }}>
          <div className="text-xs text-[var(--text-label)]">SHORT SCORE</div>
          <div className="hero-number text-3xl" style={{ color: SHORT_COLOR, textShadow: shortLeading ? `0 0 18px ${SHORT_COLOR}55` : 'none' }}>
            {shortScoreV.toFixed(1)}<span className="text-base ml-1">%</span>
          </div>
          <GaugeBar value={shortScoreV} color={SHORT_COLOR} />
          <div className="flex items-center justify-between text-[10px] text-[var(--text-label)]">
            <span>{shortScore?.short_conditions_met ?? 0}/{shortScore?.total_conditions ?? 10} met</span>
            {goShort && <span className="font-bold" style={{ color: SHORT_COLOR }}>▼ SHORT SIGNAL</span>}
            {!goShort && shortScore?.scalp_short && <span className="font-bold" style={{ color: '#f59e0b' }}>SCALP SHORT</span>}
          </div>
        </div>
      </div>

      {/* Net signal banner */}
      <div className="text-center text-sm font-bold py-2 rounded" style={{
        background: blocked ? 'rgba(107,114,128,0.15)' : `${netColor}1a`,
        border: `1px solid ${blocked ? 'rgba(107,114,128,0.4)' : `${netColor}55`}`,
        color: netColor,
      }}>
        {blocked ? '⛔ ' : netSignal.includes('LONG') ? '▲ ' : netSignal.includes('SHORT') ? '▼ ' : '◆ '}
        {netSignal}
      </div>

      {/* BLOCKED warning banner */}
      {blocked && (
        <div className="text-xs px-3 py-2 rounded" style={{
          background: 'rgba(107,114,128,0.15)',
          border: '1px solid rgba(107,114,128,0.4)',
          color: '#9ca3af',
        }}>
          ⛔ <span className="font-bold">BOTH DIRECTIONS BLOCKED</span> — one or more pre-conditions failed.
          No long or short signal fires regardless of confluence scores until the safety net clears.
        </div>
      )}

      {/* Pre-conditions row */}
      <div className="flex flex-col gap-1">
        <div className="text-xs text-[var(--text-label)]">Pre-Conditions (hard filters — apply to both directions)</div>
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
        {spreadInfo && (
          <div className="text-[10px] text-[var(--text-muted)] px-2">
            spread ${spreadInfo.current_spread ?? '—'} / threshold ${spreadInfo.threshold} ({spreadInfo.account_type} account)
          </div>
        )}
      </div>

      {/* 10-condition grid — both L and S columns per row */}
      <div className="flex flex-col gap-1.5">
        <div className="text-xs text-[var(--text-label)]">Confluence Conditions (Long vs Short)</div>
        {conditionEntries.map(([key, c]) => {
          const winningLong  = c.direction === 'long'
          const winningShort = c.direction === 'short'
          return (
            <div key={key} className="flex flex-col gap-1 px-2 py-1.5 rounded" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-[var(--text-secondary)]" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {CONDITION_LABELS[key] ?? key}
                </span>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{
                    color: winningLong ? '#fff' : LONG_COLOR,
                    background: winningLong ? LONG_COLOR : `${LONG_COLOR}1a`,
                    opacity: winningLong ? 1 : 0.45,
                  }}>
                    L {c.long_met ? `+${c.points}` : '0'}
                  </span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{
                    color: winningShort ? '#fff' : SHORT_COLOR,
                    background: winningShort ? SHORT_COLOR : `${SHORT_COLOR}1a`,
                    opacity: winningShort ? 1 : 0.45,
                  }}>
                    S {c.short_met ? `+${c.points}` : '0'}
                  </span>
                </div>
              </div>
              <div className="text-[10px] text-[var(--text-label)]" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {String(c.value ?? 'unavailable')}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {c.threshold} · src: {c.source}
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
