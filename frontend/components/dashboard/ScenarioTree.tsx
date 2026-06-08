'use client'
import { Scenario } from '@/lib/types'

interface Props { scenarios: Scenario[] }

const SCENARIO_COLORS = ['#22c55e', '#ffb347', '#ef4444']
const SCENARIO_LABELS = ['BASE CASE', 'ALT CASE', 'TAIL RISK']

export default function ScenarioTree({ scenarios }: Props) {
  const sorted = [...scenarios].sort((a, b) => b.probability - a.probability)

  if (sorted.length === 0) {
    return (
      <div className="aurum-card p-4 flex flex-col gap-3">
        <div className="section-label">Scenario Tree</div>
        <div className="text-xs text-[var(--text-muted)] text-center py-4">
          Awaiting first scenario generation...
        </div>
      </div>
    )
  }

  return (
    <div className="aurum-card p-4 flex flex-col gap-3">
      <div className="section-label">Scenario Probability Tree</div>

      <div className="flex flex-col gap-3">
        {sorted.slice(0, 3).map((sc, i) => {
          const color = SCENARIO_COLORS[i] ?? '#94a3b8'
          const tag   = SCENARIO_LABELS[i] ?? `SCENARIO ${sc.scenario_label}`

          return (
            <div key={sc.id ?? i} className="flex flex-col gap-1.5" style={{ borderLeft: `2px solid ${color}30`, paddingLeft: '8px' }}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="text-xs font-bold" style={{ color }}>{sc.scenario_label}</div>
                  <div className="agent-badge" style={{ color, borderColor: `${color}60`, background: `${color}12` }}>{tag}</div>
                </div>
                <div className="font-bold" style={{ color, fontSize: '22px' }}>{sc.probability}%</div>
              </div>

              <div style={{ color: '#fff', fontSize: '14px', fontWeight: 600 }}>{sc.scenario_name}</div>

              {/* Probability bar */}
              <div className="prob-bar">
                <div className="prob-bar-fill" style={{ width: `${sc.probability}%`, background: color }} />
              </div>

              {/* Target & drivers */}
              <div className="flex justify-between items-start gap-2">
                {sc.expected_gold_target > 0 && (
                  <div style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
                    Target: <span style={{ color }}>${sc.expected_gold_target.toLocaleString()}</span>
                  </div>
                )}
                {sc.confidence > 0 && (
                  <div style={{ color: 'var(--text-muted)', fontSize: '14px' }}>Conf {sc.confidence}%</div>
                )}
              </div>

              {sc.key_drivers && sc.key_drivers.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {sc.key_drivers.slice(0, 3).map((d, di) => (
                    <span key={di} style={{ background: `${color}12`, color: `${color}cc`, fontSize: '0.68rem', border: `1px solid ${color}25`, padding: '2px 8px', letterSpacing: '0.06em' }}>
                      {d}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
