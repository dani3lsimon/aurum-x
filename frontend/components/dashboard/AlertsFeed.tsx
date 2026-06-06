'use client'
import { Alert } from '@/lib/types'
import { formatDistanceToNow } from 'date-fns'

interface Props { alerts: Alert[] }

const SEV_CONFIG = {
  critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', dot: '#ef4444' },
  high:     { color: '#f97316', bg: 'rgba(249,115,22,0.08)', border: 'rgba(249,115,22,0.3)', dot: '#f97316' },
  medium:   { color: '#ffb347', bg: 'rgba(255,179,71,0.08)', border: 'rgba(255,179,71,0.3)', dot: '#ffb347' },
  low:      { color: '#94a3b8', bg: 'rgba(148,163,184,0.06)', border: 'rgba(148,163,184,0.2)', dot: '#94a3b8' },
}

export default function AlertsFeed({ alerts }: Props) {
  return (
    <div className="aurum-card p-4 flex flex-col gap-3 h-full">
      <div className="flex items-center justify-between">
        <div className="section-label">Alert Feed</div>
        {alerts.length > 0 && (
          <div className="live-badge">LIVE</div>
        )}
      </div>

      <div className="flex flex-col gap-1.5 overflow-y-auto max-h-64">
        {alerts.length === 0 ? (
          <div className="text-xs text-[var(--text-muted)] text-center py-6">
            No alerts — system monitoring active
          </div>
        ) : (
          alerts.map((alert, i) => {
            const cfg = SEV_CONFIG[alert.severity] ?? SEV_CONFIG.low
            const timeAgo = alert.timestamp
              ? formatDistanceToNow(new Date(alert.timestamp), { addSuffix: true })
              : '—'

            return (
              <div
                key={alert.id ?? i}
                className="flex gap-2 p-2"
                style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
              >
                <div className="mt-1 shrink-0">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ background: cfg.dot }} />
                </div>
                <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-bold truncate" style={{ color: cfg.color }}>
                      {alert.title}
                    </div>
                    <div className="text-xs text-[var(--text-muted)] shrink-0" style={{ fontSize: '0.5rem' }}>
                      {alert.severity.toUpperCase()}
                    </div>
                  </div>
                  {alert.description && (
                    <div className="text-xs text-[var(--text-muted)] truncate normal-case" style={{ fontSize: '0.55rem', textTransform: 'none' }}>
                      {alert.description}
                    </div>
                  )}
                  <div className="text-xs text-[var(--text-muted)]" style={{ fontSize: '0.5rem' }}>
                    {timeAgo}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
