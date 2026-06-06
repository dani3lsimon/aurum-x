'use client'
import { AgentScore } from '@/lib/types'

interface Props { scores: AgentScore[] }

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
}

const AGENT_WEIGHTS: Record<string, number> = {
  macro_agent: 20, fed_agent: 18, yield_agent: 15, dollar_agent: 12,
  positioning_agent: 10, news_agent: 8, geopolitical_agent: 7,
  liquidity_agent: 5, historical_agent: 3, regime_agent: 2,
}

export default function AgentScorePanel({ scores }: Props) {
  // Fill missing agents with placeholder
  const allAgents = Object.keys(AGENT_LABELS).map(name => {
    const found = scores.find(s => s.agent_name === name)
    return found ?? { agent_name: name, score: 0, confidence: 0, rationale: 'Pending...', timestamp: '', regime: '' }
  })

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
              <div className="text-xs font-bold w-10 text-right shrink-0" style={{ color }}>
                {score > 0 ? '+' : ''}{score.toFixed(0)}
              </div>

              {/* Confidence + weight */}
              <div className="text-xs text-[var(--text-muted)] w-16 text-right shrink-0">
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
