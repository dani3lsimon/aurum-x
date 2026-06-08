'use client'
import { MultiTfSignal, TfScore } from '@/lib/types'

interface Props {
  multiTf: MultiTfSignal | null
}

const TF_ORDER: { key: string; label: string }[] = [
  { key: '15min', label: '15MIN' },
  { key: '1h',    label: '1H'    },
  { key: '4h',    label: '4H'    },
]

function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

function TfColumn({ label, tf }: { label: string; tf: TfScore | undefined }) {
  if (!tf || tf.error) {
    return (
      <div className="flex flex-col gap-2" style={{ minWidth: 0 }}>
        <div className="section-label">{label}</div>
        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
          {tf?.error ?? 'No data'}
        </div>
      </div>
    )
  }

  const longPct  = tf.long_pct ?? 0
  const shortPct = tf.short_pct ?? 0
  const badge =
    longPct > shortPct && longPct >= 60 ? { text: '▲ LONG BIAS',  color: '#22c55e' } :
    shortPct > longPct && shortPct >= 60 ? { text: '▼ SHORT BIAS', color: '#ef4444' } :
    { text: '— NEUTRAL', color: '#94a3b8' }

  return (
    <div className="flex flex-col gap-2" style={{ minWidth: 0 }}>
      <div className="section-label">{label}</div>

      <div className="flex justify-between items-baseline">
        <div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#22c55e', lineHeight: 1 }}>
            {fmt(longPct, 0)}%
          </div>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>LONG</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#ef4444', lineHeight: 1 }}>
            {fmt(shortPct, 0)}%
          </div>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>SHORT</div>
        </div>
      </div>

      {/* Bidirectional bar */}
      <div className="flex h-1.5 overflow-hidden" style={{ borderRadius: '2px', background: 'rgba(255,255,255,0.06)' }}>
        <div style={{ width: `${shortPct}%`, background: '#ef4444' }} />
        <div style={{ flex: 1 }} />
        <div style={{ width: `${longPct}%`, background: '#22c55e' }} />
      </div>

      <div style={{
        fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.08em', color: badge.color,
        border: `1px solid ${badge.color}55`, borderRadius: '2px', padding: '2px 6px',
        textAlign: 'center', background: `${badge.color}14`,
      }}>
        {badge.text}
      </div>

      <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.04em' }}>
        ATR {fmt(tf.atr)} · VWAP {tf.vwap ? `$${fmt(tf.vwap, 0)}` : '—'}
      </div>
    </div>
  )
}

export default function MultiTfPanel({ multiTf }: Props) {
  const dirColor =
    multiTf?.best_direction === 'long'  ? '#22c55e' :
    multiTf?.best_direction === 'short' ? '#ef4444' : '#94a3b8'

  return (
    <div className="aurum-card p-4" style={{ height: '100%' }}>
      <div className="section-label" style={{ marginBottom: '12px' }}>Multi-Timeframe Confluence</div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', minWidth: 0 }}>

        {TF_ORDER.map(({ key, label }) => (
          <TfColumn key={key} label={label} tf={multiTf?.timeframes?.[key]} />
        ))}

        {/* Best signal column */}
        <div className="flex flex-col gap-2" style={{ minWidth: 0, borderLeft: '1px solid rgba(240,13,23,0.12)', paddingLeft: '14px' }}>
          <div className="section-label">BEST SIGNAL</div>
          <div style={{
            fontSize: '1.15rem', fontWeight: 800, letterSpacing: '0.04em', lineHeight: 1.15,
            color: dirColor, textShadow: `0 0 14px ${dirColor}66`,
          }}>
            {multiTf?.best_signal ?? '— NO SIGNAL'}
          </div>
          {multiTf?.best_timeframe && (
            <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.06em' }}>
              TF: {multiTf.best_timeframe.toUpperCase()} · {multiTf.conviction ?? '—'}
            </div>
          )}
          <div style={{ fontSize: '0.65rem', color: 'var(--text-label)', letterSpacing: '0.04em', display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span>EDGE <strong style={{ color: '#fff' }}>{fmt(multiTf?.edge_strength, 1)}</strong></span>
            <span>RISK <strong style={{ color: '#fff' }}>{fmt(multiTf?.risk_pct, 2)}%</strong></span>
            <span>STOP <strong style={{ color: '#fff' }}>{multiTf?.stop_loss ? `$${fmt(multiTf.stop_loss, 0)}` : '—'}</strong></span>
          </div>
        </div>
      </div>
    </div>
  )
}
