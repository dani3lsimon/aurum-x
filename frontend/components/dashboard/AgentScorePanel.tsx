'use client'
import { AgentScore } from '@/lib/types'

interface Props { scores: AgentScore[]; layout?: 'compact' | 'full' }

const AGENT_LABELS: Record<string, string> = {
  macro_agent:        'MACRO',
  fed_agent:          'FED',
  yield_agent:        'YIELD',
  dollar_agent:       'USD',
  positioning_agent:  'COT',
  news_agent:         'NEWS',
  geopolitical_agent: 'GEO',
  liquidity_agent:    'LIQ',
  historical_agent:   'HIST',
  regime_agent:       'REGIME',
  sentiment_agent:    'SENTIMENT',
}

const AGENT_WEIGHTS: Record<string, number> = {
  macro_agent: 20, fed_agent: 18, yield_agent: 15, dollar_agent: 12,
  positioning_agent: 10, news_agent: 8, geopolitical_agent: 7,
  liquidity_agent: 5, historical_agent: 3, regime_agent: 2, sentiment_agent: 5,
}

const BIAS_COLOR: Record<string, string> = {
  bullish: '#22c55e', bearish: '#ef4444', neutral: '#94a3b8',
}

export default function AgentScorePanel({ scores, layout = 'compact' }: Props) {
  // Fill missing agents with placeholder
  const allAgents = Object.keys(AGENT_LABELS).map(name => {
    const found = scores.find(s => s.agent_name === name)
    return found ?? { agent_name: name, score: 0, confidence: 0, rationale: 'Pending...', timestamp: '', regime: '' } as AgentScore
  })

  if (layout === 'full') {
    return (
      <div className="flex flex-col gap-3">
        <div className="section-label">Agent Score Matrix — Full Detail (11 Agents)</div>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
          {allAgents.map(agent => {
            const score  = agent.score ?? 0
            const conf   = agent.confidence ?? 0
            const label  = AGENT_LABELS[agent.agent_name] ?? agent.agent_name
            const weight = AGENT_WEIGHTS[agent.agent_name] ?? 5
            const color  = score > 10 ? '#22c55e' : score < -10 ? '#ef4444' : '#94a3b8'
            const raw    = agent.raw_data ?? {}
            const bias   = (raw.directional_bias as string) ?? ''
            const biasColor = BIAS_COLOR[bias?.toLowerCase()] ?? '#94a3b8'
            const factors = Array.isArray(raw.key_factors) ? (raw.key_factors as string[]) : []

            return (
              <div key={agent.agent_name} className="aurum-card p-4 flex flex-col gap-3"
                style={{ minHeight: '280px', borderLeft: `3px solid ${color}`, minWidth: 0 }}>

                {/* Card header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="agent-badge">{label}</div>
                    {bias && (
                      <span style={{
                        fontSize: '0.65rem', letterSpacing: '0.1em', color: biasColor,
                        border: `1px solid ${biasColor}55`, borderRadius: '2px', padding: '2px 8px',
                        background: `${biasColor}14`, textTransform: 'uppercase',
                      }}>
                        {bias}
                      </span>
                    )}
                  </div>
                  <div className="font-bold" style={{ color, fontSize: '1.1rem' }}>
                    {score > 0 ? '+' : ''}{score.toFixed(0)}
                  </div>
                </div>

                {/* Bidirectional bar */}
                <div className="flex items-center gap-px h-4">
                  <div className="flex-1 flex justify-end">
                    <div className="h-2 transition-all duration-700"
                      style={{ width: score < 0 ? `${Math.abs(score)}%` : '0%', background: '#ef4444', maxWidth: '100%' }} />
                  </div>
                  <div className="w-px h-3 bg-[var(--border-subtle)] shrink-0" />
                  <div className="flex-1">
                    <div className="h-2 transition-all duration-700"
                      style={{ width: score > 0 ? `${Math.abs(score)}%` : '0%', background: '#22c55e', maxWidth: '100%' }} />
                  </div>
                </div>

                {/* Rationale — full text */}
                <div style={{ fontSize: '0.72rem', lineHeight: 1.5, color: 'var(--text-primary)', textTransform: 'none', letterSpacing: '0.01em', flex: 1 }}>
                  {agent.rationale || 'Pending analysis...'}
                </div>

                {/* Key factors */}
                {factors.length > 0 && (
                  <ul style={{ fontSize: '0.68rem', lineHeight: 1.5, color: 'var(--text-label)', textTransform: 'none', paddingLeft: '14px', listStyle: 'disc' }}>
                    {factors.slice(0, 3).map((f, i) => <li key={i} style={{ marginBottom: '2px' }}>{f}</li>)}
                  </ul>
                )}

                {/* Footer meta — confidence / weight / signal_strength / data_quality */}
                <div className="flex items-center justify-between border-t border-[var(--border-subtle)] pt-2"
                  style={{ fontSize: '0.65rem', color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
                  <span>CONF {conf.toFixed(0)}% · WEIGHT {weight}%</span>
                  <span>
                    {raw.signal_strength ? `STRENGTH ${String(raw.signal_strength).toUpperCase()}` : ''}
                    {raw.data_quality ? ` · QUALITY ${String(raw.data_quality).toUpperCase()}` : ''}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <div className="aurum-card p-4 flex flex-col gap-3">
      <div className="section-label">Agent Score Matrix</div>

      <div className="flex flex-col gap-1">
        {allAgents.map((agent) => {
          const score = agent.score ?? 0
          const conf  = agent.confidence ?? 0
          const label = AGENT_LABELS[agent.agent_name] ?? agent.agent_name
          const weight = AGENT_WEIGHTS[agent.agent_name] ?? 5
          const isPos  = score >= 0
          const pct    = Math.abs(score)
          const color  = score > 10 ? '#22c55e' : score < -10 ? '#ef4444' : '#94a3b8'

          return (
            <div key={agent.agent_name} className="flex items-center gap-2">
              {/* Label */}
              <div className="agent-badge w-14 text-center shrink-0">{label}</div>

              {/* Bidirectional bar */}
              <div className="flex-1 flex items-center gap-px h-4">
                {/* Left (bear) side */}
                <div className="flex-1 flex justify-end">
                  <div
                    className="h-2 transition-all duration-700"
                    style={{
                      width: !isPos ? `${pct}%` : '0%',
                      background: '#ef4444',
                      maxWidth: '100%',
                    }}
                  />
                </div>
                {/* Centre line */}
                <div className="w-px h-3 bg-[var(--border-subtle)] shrink-0" />
                {/* Right (bull) side */}
                <div className="flex-1">
                  <div
                    className="h-2 transition-all duration-700"
                    style={{
                      width: isPos ? `${pct}%` : '0%',
                      background: '#22c55e',
                      maxWidth: '100%',
                    }}
                  />
                </div>
              </div>

              {/* Score value */}
              <div className="font-bold w-10 text-right shrink-0" style={{ color, fontSize: '0.75rem' }}>
                {score > 0 ? '+' : ''}{score.toFixed(0)}
              </div>

              {/* Confidence + weight */}
              <div className="text-right shrink-0" style={{ color: 'var(--text-muted)', fontSize: '0.68rem', width: '4.5rem' }}>
                {conf.toFixed(0)}% / {weight}%
              </div>
            </div>
          )
        })}
      </div>

      <div className="text-xs text-[var(--text-muted)] border-t border-[var(--border-subtle)] pt-2 mt-1">
        Score: -100 (bearish) to +100 (bullish) | Conf / Weight
      </div>
    </div>
  )
}
