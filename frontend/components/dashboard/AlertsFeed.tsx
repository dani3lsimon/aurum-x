'use client'
import { Alert } from '@/lib/types'
import { formatDistanceToNow } from 'date-fns'

interface Props { alerts: Alert[]; compact?: boolean }

const SEV_CONFIG = {
  critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', dot: '#ef4444' },
  high:     { color: '#f97316', bg: 'rgba(249,115,22,0.08)', border: 'rgba(249,115,22,0.3)', dot: '#f97316' },
  medium:   { color: '#ffb347', bg: 'rgba(255,179,71,0.08)', border: 'rgba(255,179,71,0.3)', dot: '#ffb347' },
  low:      { color: '#94a3b8', bg: 'rgba(148,163,184,0.06)', border: 'rgba(148,163,184,0.2)', dot: '#94a3b8' },
}

const FS = { title: '0.78rem', body: '0.72rem', meta: '0.68rem' }

export default function AlertsFeed({ alerts, compact = false }: Props) {
  return (
    <div className="aurum-card p-4 flex flex-col gap-3 h-full">
      <div className="flex items-center justify-between">
        <div className="section-label">Alert Feed</div>
        {alerts.length > 0 && <div className="live-badge">LIVE</div>}
      </div>

      <div className="flex flex-col gap-2 overflow-y-auto" style={{ maxHeight: compact ? '180px' : '280px' }}>
        {alerts.length === 0 ? (
          <div className="text-center py-6" style={{ fontSize: FS.body, color: 'var(--text-muted)' }}>
            No alerts — system monitoring active
          </div>
        ) : (
          alerts.map((alert, i) => {
            const cfg    = SEV_CONFIG[alert.severity] ?? SEV_CONFIG.low
            const timeAgo = alert.timestamp
              ? formatDistanceToNow(new Date(alert.timestamp), { addSuffix: true })
              : '—'

            return (
              <div
                key={alert.id ?? i}
                className="flex gap-3 p-3"
                style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
              >
                <div style={{ marginTop: '3px', flexShrink: 0 }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: cfg.dot, boxShadow: `0 0 6px ${cfg.dot}` }} />
                </div>
                <div className="flex flex-col gap-1 flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div style={{ color: cfg.color, fontSize: FS.title, fontWeight: 700, lineHeight: 1.4 }}>
                      {alert.title}
                    </div>
                    <div style={{ color: cfg.color, fontSize: FS.meta, flexShrink: 0, fontWeight: 600 }}>
                      {alert.severity.toUpperCase()}
                    </div>
                  </div>
                  {alert.description && (
                    <div style={{ color: 'var(--text-muted)', fontSize: FS.body, textTransform: 'none', lineHeight: 1.5 }}>
                      {alert.description}
                    </div>
                  )}
                  <div style={{ color: 'var(--text-muted)', fontSize: FS.meta }}>
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
