'use client'
import { MultiTfSignal, TfScore } from '@/lib/types'

interface Props {
  multiTf: MultiTfSignal | null
  signalChanged?: boolean
  signalChangedAt?: Date | null
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
          <div style={{ fontSize: '28px', fontWeight: 700, color: '#22c55e', lineHeight: 1 }}>
            {fmt(longPct, 0)}%
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>LONG</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '28px', fontWeight: 700, color: '#ef4444', lineHeight: 1 }}>
            {fmt(shortPct, 0)}%
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', letterSpacing: '0.08em' }}>SHORT</div>
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

export default function MultiTfPanel({ multiTf, signalChanged, signalChangedAt }: Props) {
  const dirColor =
    multiTf?.best_direction === 'long'  ? '#22c55e' :
    multiTf?.best_direction === 'short' ? '#ef4444' : '#94a3b8'

  const isLong  = multiTf?.best_direction === 'long'
  const isShort = multiTf?.best_direction === 'short'

  return (
    <div className="aurum-card p-4" style={{ height: '100%' }}>
      <div className="section-label" style={{ marginBottom: '12px' }}>Multi-Timeframe Confluence</div>

      {signalChanged && (
        <div style={{
          padding: '10px 16px',
          background: 'rgba(255,179,71,0.1)',
          border: '1px solid rgba(255,179,71,0.5)',
          fontSize: '13px',
          fontWeight: 700,
          color: '#ffb347',
          letterSpacing: '0.12em',
          textAlign: 'center',
          marginBottom: '8px',
          animation: 'glowPulse 0.5s ease-in-out 6',
        }}>
          ⚡ SIGNAL DIRECTION CHANGED → {multiTf?.best_direction?.toUpperCase()}
          {signalChangedAt && (
            <span style={{ fontSize: '10px', color: '#4a5068', marginLeft: '12px' }}>
              {signalChangedAt.toLocaleTimeString()}
            </span>
          )}
        </div>
      )}

      <div className="grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', minWidth: 0 }}>

        {TF_ORDER.map(({ key, label }) => (
          <TfColumn key={key} label={label} tf={multiTf?.timeframes?.[key]} />
        ))}

        {/* Best Signal column — 4th column */}
        <div className="aurum-card" style={{ padding: '16px', borderColor: isLong ? 'rgba(34,197,94,0.3)' : isShort ? 'rgba(239,68,68,0.3)' : 'rgba(255,80,0,0.1)' }}>
          <div className="section-label" style={{ marginBottom: '10px' }}>◆ BEST SIGNAL</div>

          {/* Direction + conviction */}
          <div style={{
            fontSize: '22px', fontWeight: 800, letterSpacing: '0.08em',
            color: isLong ? '#22c55e' : isShort ? '#ef4444' : '#6b7494',
            marginBottom: '4px',
          }}>
            {isLong ? '▲' : isShort ? '▼' : '—'} {multiTf?.best_direction?.toUpperCase() ?? 'NO TRADE'}
          </div>
          <div style={{ fontSize: '13px', color: isLong ? '#22c55e' : '#ef4444', letterSpacing: '0.1em', marginBottom: '12px' }}>
            {multiTf?.conviction ?? '—'} · {multiTf?.best_timeframe?.toUpperCase()}
          </div>

          {/* Trade levels — the key section */}
          {multiTf?.entry_price ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '12px' }}>

              {/* Entry */}
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', background: 'rgba(255,80,0,0.08)', border: '1px solid rgba(255,80,0,0.2)' }}>
                <span style={{ fontSize: '11px', color: '#ff7744', letterSpacing: '0.12em' }}>ENTRY</span>
                <span style={{ fontSize: '14px', fontWeight: 700, color: '#ff7744' }}>
                  ${multiTf.entry_price.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </span>
              </div>

              {/* TP1 */}
              {multiTf.take_profits?.tp1 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.2)' }}>
                  <div>
                    <span style={{ fontSize: '11px', color: '#22c55e', letterSpacing: '0.12em' }}>TP1 · 1:1</span>
                    <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.1em' }}>
                      CLOSE 50% · +${multiTf.take_profits.tp1.reward_usd}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '14px', fontWeight: 700, color: '#22c55e' }}>
                      ${multiTf.take_profits.tp1.price?.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </div>
                    <div style={{ fontSize: '10px', color: '#4a5068' }}>
                      {multiTf.expected_move?.prob_tp1}% probability
                    </div>
                  </div>
                </div>
              )}

              {/* TP2 */}
              {multiTf.take_profits?.tp2 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', background: 'rgba(34,197,94,0.04)', border: '1px solid rgba(34,197,94,0.15)' }}>
                  <div>
                    <span style={{ fontSize: '11px', color: '#22c55e', letterSpacing: '0.12em', opacity: 0.8 }}>TP2 · 1:2</span>
                    <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.1em' }}>
                      CLOSE 25% · +${multiTf.take_profits.tp2.reward_usd}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '14px', fontWeight: 700, color: '#22c55e', opacity: 0.8 }}>
                      ${multiTf.take_profits.tp2.price?.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </div>
                    <div style={{ fontSize: '10px', color: '#4a5068' }}>
                      {multiTf.expected_move?.prob_tp2}% probability
                    </div>
                  </div>
                </div>
              )}

              {/* TP3 */}
              {multiTf.take_profits?.tp3 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', background: 'rgba(34,197,94,0.02)', border: '1px solid rgba(34,197,94,0.1)' }}>
                  <div>
                    <span style={{ fontSize: '11px', color: '#22c55e', letterSpacing: '0.12em', opacity: 0.6 }}>TP3 · 1:3</span>
                    <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.1em' }}>
                      TRAIL 25% · +${multiTf.take_profits.tp3.reward_usd}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '14px', fontWeight: 700, color: '#22c55e', opacity: 0.6 }}>
                      ${multiTf.take_profits.tp3.price?.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </div>
                    <div style={{ fontSize: '10px', color: '#4a5068' }}>
                      {multiTf.expected_move?.prob_tp3}% probability
                    </div>
                  </div>
                </div>
              )}

              {/* Stop Loss */}
              {multiTf.stop_loss && (
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.25)' }}>
                  <div>
                    <span style={{ fontSize: '11px', color: '#ef4444', letterSpacing: '0.12em' }}>STOP LOSS</span>
                    <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.1em' }}>
                      RISK −${multiTf.risk_usd} ({multiTf.risk_pct}%)
                    </div>
                  </div>
                  <span style={{ fontSize: '14px', fontWeight: 700, color: '#ef4444' }}>
                    ${multiTf.stop_loss.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', letterSpacing: '0.06em', marginBottom: '12px' }}>
              {multiTf?.best_signal ?? '— NO SIGNAL'}
            </div>
          )}

          {/* Expected move summary */}
          {!!multiTf?.expected_move && multiTf.expected_move.min_pts > 0 && (
            <div style={{
              padding: '6px 10px',
              background: 'rgba(255,179,71,0.05)',
              border: '1px solid rgba(255,179,71,0.2)',
              fontSize: '11px',
              color: '#c8a870',
              letterSpacing: '0.08em',
              lineHeight: 1.5,
              marginBottom: '8px',
            }}>
              EXPECTED MOVE: {multiTf.expected_move.min_pts}–{multiTf.expected_move.max_pts} PTS
            </div>
          )}

          {/* Edge + ATR */}
          <div style={{ display: 'flex', gap: '12px', fontSize: '11px', color: '#4a5068', letterSpacing: '0.1em' }}>
            <span>EDGE <strong style={{ color: '#ff7744' }}>{fmt(multiTf?.edge_strength, 1)}</strong></span>
            <span>ATR <strong style={{ color: '#ff7744' }}>{multiTf?.atr?.toFixed(2)}</strong></span>
          </div>
        </div>
      </div>
    </div>
  )
}
