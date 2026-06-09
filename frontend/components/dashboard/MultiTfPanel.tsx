'use client'
import { MultiTfSignal, TfScore } from '@/lib/types'
import UpdateBadge from './UpdateBadge'

interface Props {
  multiTf: MultiTfSignal | null
  signalChanged?: boolean
  signalChangedAt?: Date | null
  livePrice?: number
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

// Mirrors backend CONDITION_WEIGHTS / MAX_SCORE (engines/multi_tf_engine.py) —
// needed to honestly re-derive the displayed long/short % between backend
// refreshes when nudging price-sensitive conditions with the live tick.
const CONDITION_WEIGHTS: Record<string, number> = {
  dxy: 2, yield: 2, vwap: 1, delta: 2, cot: 1, etf: 1, risk: 1, break: 2, news: 1,
}
const MAX_SCORE = 14.0
const COND_LABEL: Record<string, string> = {
  dxy: 'DXY', yield: 'YIELD', vwap: 'VWAP', delta: 'DELTA', cot: 'COT',
  etf: 'ETF', risk: 'RISK', break: 'BREAK', news: 'NEWS', interaction: 'CONFLUENCE',
}

/**
 * Semi-live recompute (FIX 3 — "honest version"):
 * The backend's authoritative score refreshes every ~5 minutes. Between
 * refreshes, nudge ONLY the price-sensitive conditions (vwap, break) using
 * the live cTrader tick, re-sum, and re-derive the displayed percentage.
 * Everything else (macro/fundamental conditions) stays exactly as the
 * backend last computed it — never fabricated, just clearly labelled.
 */
function recomputeWithLivePrice(tf: TfScore, livePrice?: number) {
  const conditions = tf.conditions || {}
  if (!livePrice || !conditions) {
    return { longPct: tf.long_pct ?? 0, shortPct: tf.short_pct ?? 0, conditions }
  }

  let shortRaw = tf.short_raw ?? 0
  let longRaw  = tf.long_raw  ?? 0
  const next: Record<string, any> = { ...conditions }

  const nudge = (key: 'vwap' | 'break', nowLong: boolean, nowShort: boolean, value: string) => {
    const cond = conditions[key]
    if (!cond) return
    const w = CONDITION_WEIGHTS[key] ?? 0
    if (cond.long_met)  longRaw  -= w
    if (cond.short_met) shortRaw -= w
    if (nowLong)  longRaw  += w
    if (nowShort) shortRaw += w
    next[key] = { ...cond, long_met: nowLong, short_met: nowShort, value, live: true }
  }

  if (tf.vwap != null) {
    nudge('vwap', livePrice > tf.vwap, livePrice < tf.vwap,
      `$${livePrice.toFixed(2)} vs VWAP $${tf.vwap.toFixed(2)} · live tick`)
  }
  if (tf.prior_high != null && tf.prior_low != null) {
    const up = livePrice > tf.prior_high
    const down = livePrice < tf.prior_low
    nudge('break', up, down,
      `Break ${up ? 'up' : down ? 'down' : 'neutral'} (range $${tf.prior_low.toFixed(2)}-$${tf.prior_high.toFixed(2)}) · live tick`)
  }

  const shortPct = Math.round(Math.min(100, (shortRaw / MAX_SCORE) * 100) * 10) / 10
  const longPct  = Math.round(Math.min(100, (longRaw  / MAX_SCORE) * 100) * 10) / 10

  return { longPct, shortPct, conditions: next }
}

function ConditionRow({ name, cond }: { name: string; cond: any }) {
  const dir = cond.long_met ? 'long' : cond.short_met ? 'short' : 'neutral'
  const color = dir === 'long' ? '#22c55e' : dir === 'short' ? '#ef4444' : '#4a5068'
  const isLive = !!cond.live
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.6rem', color: '#6b7494', lineHeight: 1.5 }}>
      <span style={{ color: isLive ? '#ff7744' : '#4a5068', minWidth: '46px', letterSpacing: '0.06em' }}>
        {isLive ? '◆ LIVE' : '· cached'}
      </span>
      <span style={{ color: '#4a5068', minWidth: '52px', fontWeight: 700, letterSpacing: '0.06em' }}>
        {COND_LABEL[name] || name.toUpperCase()}
      </span>
      <span style={{ color, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {cond.value}
      </span>
    </div>
  )
}

function TfColumn({ label, tf, livePrice }: { label: string; tf: TfScore | undefined; livePrice?: number }) {
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

  const { longPct, shortPct, conditions } = recomputeWithLivePrice(tf, livePrice)
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

      {/* Per-condition breakdown — honestly tagged: ◆ LIVE conditions are
          nudged from the live cTrader tick between backend refreshes;
          · cached conditions reflect the backend's last ~5-min computation. */}
      {conditions && Object.keys(conditions).length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '2px', minHeight: '108px' }}>
          {Object.entries(conditions)
            .filter(([name]) => name !== 'interaction')
            .map(([name, cond]) => <ConditionRow key={name} name={name} cond={cond} />)}
        </div>
      )}
    </div>
  )
}

export default function MultiTfPanel({ multiTf, signalChanged, signalChangedAt, livePrice }: Props) {
  const dirColor =
    multiTf?.best_direction === 'long'  ? '#22c55e' :
    multiTf?.best_direction === 'short' ? '#ef4444' : '#94a3b8'

  const isLong  = multiTf?.best_direction === 'long'
  const isShort = multiTf?.best_direction === 'short'

  return (
    <div className="aurum-card p-4" style={{ height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '4px' }}>
        <div className="section-label">Multi-Timeframe Confluence</div>
        <UpdateBadge
          lastUpdated={multiTf?.timestamp ? new Date(multiTf.timestamp) : null}
          intervalMs={300_000}
          label="OANDA · FRED"
        />
      </div>

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
          <TfColumn key={key} label={label} tf={multiTf?.timeframes?.[key]} livePrice={livePrice} />
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

          {/* Live P&L — updates on every tick */}
          {multiTf?.entry_price && livePrice ? (() => {
            const entryPrice = multiTf.entry_price as number
            const pnlPts   = isLong
              ? livePrice - entryPrice
              : entryPrice - livePrice
            const riskDist = multiTf.risk_distance || 1
            const pnlUsd   = multiTf.risk_usd
              ? (pnlPts / riskDist) * multiTf.risk_usd
              : 0

            // Progress toward TP1 (0-100%)
            const tp1      = multiTf.take_profits?.tp1?.price
            const sl       = multiTf.stop_loss
            const progress = tp1
              ? Math.max(0, Math.min(100, (pnlPts / Math.abs(tp1 - entryPrice)) * 100))
              : 0

            const pnlColor = pnlPts >= 0 ? '#22c55e' : '#ef4444'
            const inProfit = pnlPts >= 0

            // Distance to next target
            const distToTp1 = tp1 ? Math.abs(tp1 - livePrice).toFixed(2) : null
            const distToSl  = sl  ? Math.abs(livePrice - sl).toFixed(2)  : null

            return (
              <div style={{ marginBottom: '10px' }}>
                {/* Live P&L hero number */}
                <div style={{
                  padding: '10px',
                  background: `${pnlColor}10`,
                  border: `1px solid ${pnlColor}40`,
                  textAlign: 'center',
                  marginBottom: '6px',
                }}>
                  <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.14em', marginBottom: '4px' }}>
                    LIVE P&L
                  </div>
                  <div style={{ fontSize: '24px', fontWeight: 800, color: pnlColor, letterSpacing: '-0.01em' }}>
                    {pnlPts >= 0 ? '+' : ''}{pnlPts.toFixed(2)} PTS
                  </div>
                  <div style={{ fontSize: '12px', color: pnlColor, opacity: 0.8 }}>
                    {pnlUsd >= 0 ? '+' : ''}${pnlUsd.toFixed(2)} USD
                  </div>
                </div>

                {/* Progress bar toward TP1 */}
                {tp1 && (
                  <div style={{ marginBottom: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#4a5068', marginBottom: '3px' }}>
                      <span>ENTRY ${entryPrice.toFixed(0)}</span>
                      <span style={{ color: '#22c55e' }}>TP1 ${tp1.toFixed(0)}</span>
                    </div>
                    <div style={{ height: '5px', background: 'rgba(255,255,255,0.05)', position: 'relative' }}>
                      <div style={{
                        width: `${Math.max(0, Math.min(100, progress))}%`,
                        height: '100%',
                        background: inProfit ? '#22c55e' : '#ef4444',
                        transition: 'width 0.2s ease',
                        boxShadow: `0 0 6px ${pnlColor}60`,
                      }} />
                    </div>
                    <div style={{ fontSize: '10px', color: '#4a5068', marginTop: '3px', textAlign: 'right' }}>
                      {progress.toFixed(0)}% to TP1
                    </div>
                  </div>
                )}

                {/* Distance to next levels */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
                  {distToTp1 && (
                    <div style={{ padding: '5px 8px', background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.15)', fontSize: '11px' }}>
                      <div style={{ color: '#4a5068', fontSize: '9px', letterSpacing: '0.1em', marginBottom: '2px' }}>TO TP1</div>
                      <div style={{ color: '#22c55e', fontWeight: 700 }}>{distToTp1} PTS</div>
                    </div>
                  )}
                  {distToSl && (
                    <div style={{ padding: '5px 8px', background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.15)', fontSize: '11px' }}>
                      <div style={{ color: '#4a5068', fontSize: '9px', letterSpacing: '0.1em', marginBottom: '2px' }}>TO STOP</div>
                      <div style={{ color: '#ef4444', fontWeight: 700 }}>{distToSl} PTS</div>
                    </div>
                  )}
                </div>
              </div>
            )
          })() : null}

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
