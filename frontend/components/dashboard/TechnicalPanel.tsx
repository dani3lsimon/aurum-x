'use client'
import { useState, useEffect } from 'react'
import UpdateBadge from './UpdateBadge'

const BACKEND    = process.env.NEXT_PUBLIC_BACKEND_URL || ''
const REFRESH_MS = 30_000   // 30s — backend SMC cache is 30s
const KRONOS_REFRESH_MS = 300_000  // 5 min — matches Kronos cache TTL

const DIR_COLOR: Record<string, string> = {
  bullish: '#22c55e',
  bearish: '#ef4444',
  neutral: '#6b7494',
}

const TF_LABEL: Record<string, string> = { '15min': '15MIN', '1h': '1H', '4h': '4H' }

const PATTERN_LABEL: Record<string, string> = {
  liquidity_grab: 'LIQ GRAB',
  fvg: 'FVG',
  order_block: 'ORDER BLOCK',
  breaker_block: 'BREAKER',
  head_shoulders_top: 'H&S TOP',
  inverse_head_shoulders: 'INV H&S',
  double_top: 'DOUBLE TOP',
  double_bottom: 'DOUBLE BOTTOM',
}

function patternTag(p: any, idx: number) {
  const dir   = p.direction || 'neutral'
  const color = DIR_COLOR[dir] || '#6b7494'
  const label = PATTERN_LABEL[p.type] || p.type?.toUpperCase()
  const extra = p.state ? ` · ${p.state.toUpperCase()}` : p.status ? ` · ${p.status.toUpperCase()}` : ''
  return (
    <span key={idx} style={{
      display: 'inline-block', padding: '3px 8px', margin: '2px 4px 2px 0',
      fontSize: '10px', letterSpacing: '0.08em', fontFamily: 'JetBrains Mono, monospace',
      color, background: `${color}14`, border: `1px solid ${color}40`, borderRadius: '2px',
      textTransform: 'uppercase', whiteSpace: 'nowrap',
    }}>
      {dir === 'bullish' ? '▲' : dir === 'bearish' ? '▼' : '·'} {label}{extra}
    </span>
  )
}

function ConfluenceGauge({ score }: { score: number }) {
  // -5..+5 → 0..100%
  const pct   = Math.max(0, Math.min(100, ((score + 5) / 10) * 100))
  const color = score > 1 ? '#22c55e' : score < -1 ? '#ef4444' : '#ffb347'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ flex: 1, height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${pct}%`, background: color, opacity: 0.7, transition: 'width 0.5s ease' }} />
        <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.15)' }} />
      </div>
      <span style={{ fontSize: '13px', fontWeight: 800, color, minWidth: '38px', textAlign: 'right' }}>{score > 0 ? '+' : ''}{score.toFixed(2)}</span>
    </div>
  )
}

const QUALITY_COLOR: Record<string, string> = {
  HIGH_CONVICTION: '#22c55e',
  SCALP:           '#60a5fa',
  WEAK:            '#ffb347',
  NO_TRADE:        '#4a5068',
}

const ALIGNMENT_LABEL: Record<string, { label: string; color: string }> = {
  aligned_bullish: { label: '▲ ALIGNED BULLISH', color: '#22c55e' },
  aligned_bearish: { label: '▼ ALIGNED BEARISH', color: '#ef4444' },
  conflicting:     { label: '⚡ CONFLICTING',     color: '#ffb347' },
  neutral:         { label: '· NEUTRAL',          color: '#6b7494' },
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function TechnicalPanel() {
  const [smc, setSmc]                   = useState<any>(null)
  const [fusion, setFusion]             = useState<any>(null)
  const [kronos, setKronos]             = useState<any>(null)
  const [kronosAccuracy, setKronosAccuracy] = useState<any>(null)
  const [loading, setLoading]           = useState(true)
  const [lastUpdated, setLastUpdated]   = useState<Date | null>(null)
  const [changeAlert, setChangeAlert]   = useState<any[] | null>(null)
  const [alertFlash, setAlertFlash]     = useState(false)

  const fetchData = async () => {
    try {
      const [p, f] = await Promise.all([
        fetch(`${BACKEND}/forecast/patterns`).then(r => r.json()),
        fetch(`${BACKEND}/agents/technical-fusion`).then(r => r.json()),
      ])
      setSmc(p)
      setFusion(f)
      setLastUpdated(new Date())
    } catch {}
    setLoading(false)
  }

  const fetchKronos = async () => {
    try {
      const [k, acc] = await Promise.all([
        fetch(`${BACKEND}/forecast/kronos/latest`).then(r => r.json()),
        fetch(`${BACKEND}/forecast/kronos/accuracy`).then(r => r.json()),
      ])
      setKronos(k)
      setKronosAccuracy(acc)
    } catch {}
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, REFRESH_MS)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetchKronos()
    const interval = setInterval(fetchKronos, KRONOS_REFRESH_MS)
    return () => clearInterval(interval)
  }, [])

  // WebSocket: listen for smc_change events broadcast by the backend monitor
  useEffect(() => {
    const WS_URL = (process.env.NEXT_PUBLIC_WS_URL || BACKEND.replace(/^http/, 'ws')) + '/ws'
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout>

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL)
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data)
            if (msg.type === 'smc_change' && msg.changes?.length) {
              setChangeAlert(msg.changes)
              setAlertFlash(true)
              // Immediately re-fetch so panel shows the new data
              fetchData()
              // Auto-dismiss flash after 8s but keep the change list visible
              setTimeout(() => setAlertFlash(false), 8000)
            }
          } catch {}
        }
        ws.onclose = () => { reconnectTimer = setTimeout(connect, 5000) }
        ws.onerror = () => { ws?.close() }
      } catch {}
    }

    connect()
    return () => {
      clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [])

  if (loading && !smc) {
    return (
      <div className="aurum-card" style={{ padding: '16px', textAlign: 'center', fontSize: '11px', color: '#4a5068', letterSpacing: '0.14em', minHeight: '420px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        LOADING SMC STRUCTURE...
      </div>
    )
  }

  const alignment = smc?.alignment ? ALIGNMENT_LABEL[smc.alignment] || ALIGNMENT_LABEL.neutral : ALIGNMENT_LABEL.neutral

  return (
    <div className="aurum-card" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '12px', minWidth: 0 }}>

      {/* AI Change Alert Banner — shown when backend monitor detects a flip */}
      {changeAlert && (
        <div style={{
          padding: '8px 12px',
          background: alertFlash ? 'rgba(255,119,68,0.15)' : 'rgba(255,119,68,0.06)',
          border: `1px solid ${alertFlash ? 'rgba(255,119,68,0.7)' : 'rgba(255,119,68,0.2)'}`,
          borderRadius: '2px',
          transition: 'background 0.5s, border-color 0.5s',
          display: 'flex', flexDirection: 'column', gap: '4px',
        }}>
          <div style={{ fontSize: '10px', fontWeight: 800, color: '#ff7744', letterSpacing: '0.12em' }}>
            ◆ MONITOR DETECTED {changeAlert.length} CHANGE{changeAlert.length > 1 ? 'S' : ''}
          </div>
          {changeAlert.map((c, i) => (
            <div key={i} style={{ fontSize: '10px', color: c.urgent ? '#ffb347' : '#6b7494', letterSpacing: '0.08em' }}>
              {c.label}: {String(c.from).toUpperCase()} → {String(c.to).toUpperCase()}
            </div>
          ))}
          <button onClick={() => setChangeAlert(null)} style={{
            alignSelf: 'flex-end', fontSize: '9px', color: '#4a5068', background: 'none',
            border: 'none', cursor: 'pointer', letterSpacing: '0.1em', padding: '0',
          }}>DISMISS</button>
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '4px' }}>
        <span style={{ fontSize: '12px', fontWeight: 800, letterSpacing: '0.16em', color: '#ff7744' }}>
          ⌬ SMART MONEY STRUCTURE
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <UpdateBadge lastUpdated={lastUpdated} intervalMs={REFRESH_MS} label="OANDA" />
          <span style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.1em' }}>
            NET {smc?.net_confluence != null ? (smc.net_confluence > 0 ? '+' : '') + smc.net_confluence.toFixed(2) : '—'}
          </span>
          <span style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em', color: alignment.color }}>
            {alignment.label}
          </span>
        </div>
      </div>

      {/* SMC server-side timestamp */}
      {smc?.fetched_at && (
        <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono, monospace', marginTop: '-8px' }}>
          SERVER COMPUTED {fmtTime(smc.fetched_at)} UTC · CACHE {smc.cache_ttl_s ?? 30}s
        </div>
      )}

      {/* Per-timeframe structure */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
        {(['15min', '1h', '4h'] as const).map(tf => {
          const t = smc?.[tf]
          if (!t || t.error) {
            return (
              <div key={tf} style={{ padding: '10px', border: '1px solid rgba(255,80,0,0.08)', borderRadius: '2px' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#ff7744', marginBottom: '4px' }}>{TF_LABEL[tf]}</div>
                <div style={{ fontSize: '10px', color: '#4a5068' }}>{t?.error || 'no data'}</div>
              </div>
            )
          }
          const trend = t.structure?.trend
          const bos   = t.structure?.bos
          const choch = t.structure?.choch
          return (
            <div key={tf} style={{ padding: '10px', border: '1px solid rgba(255,80,0,0.08)', borderRadius: '2px', display: 'flex', flexDirection: 'column', gap: '6px', minHeight: '168px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#ff7744', letterSpacing: '0.08em' }}>{TF_LABEL[tf]}</span>
                <span style={{ fontSize: '10px', fontWeight: 700, color: DIR_COLOR[t.bias] || '#6b7494', textTransform: 'uppercase' }}>{t.bias}</span>
              </div>

              <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', minHeight: '20px' }}>
                <span style={{ fontSize: '9px', padding: '2px 6px', borderRadius: '2px', letterSpacing: '0.08em',
                  color: DIR_COLOR[trend] || '#6b7494', background: `${DIR_COLOR[trend] || '#6b7494'}14`,
                  border: `1px solid ${DIR_COLOR[trend] || '#6b7494'}40`, textTransform: 'uppercase' }}>
                  TREND: {trend || '—'}
                </span>
                {bos && (
                  <span style={{ fontSize: '9px', padding: '2px 6px', borderRadius: '2px', letterSpacing: '0.08em',
                    color: DIR_COLOR[bos], background: `${DIR_COLOR[bos]}14`, border: `1px solid ${DIR_COLOR[bos]}40` }}>
                    BOS {bos.toUpperCase()}
                  </span>
                )}
                {choch && (
                  <span style={{ fontSize: '9px', padding: '2px 6px', borderRadius: '2px', letterSpacing: '0.08em',
                    color: DIR_COLOR[choch], background: `${DIR_COLOR[choch]}14`, border: `1px solid ${DIR_COLOR[choch]}40` }}>
                    CHoCH {choch.toUpperCase()}
                  </span>
                )}
              </div>

              <ConfluenceGauge score={t.confluence_score ?? 0} />

              <div style={{ display: 'flex', flexWrap: 'wrap', minHeight: '46px', alignContent: 'flex-start', overflow: 'hidden', maxHeight: '70px' }}>
                {(t.patterns || []).length > 0
                  ? t.patterns.slice(0, 6).map((p: any, i: number) => patternTag(p, i))
                  : <span style={{ fontSize: '10px', color: '#4a5068' }}>No active patterns</span>}
              </div>
            </div>
          )
        })}
      </div>

      {/* Fusion agent thesis card */}
      <div style={{ minHeight: '180px' }}>
      {fusion && !fusion.error && (
        <div style={{ padding: '12px', border: '1px solid rgba(255,80,0,0.14)', borderRadius: '2px', background: 'rgba(255,80,0,0.02)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '4px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
              <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.14em', color: '#ff7744' }}>⚡ FUSION THESIS</span>
              {fusion.generated_at && (
                <span style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono, monospace' }}>
                  {fusion.provider === 'deepseek_chat' ? 'DEEPSEEK' : 'CLAUDE SONNET'} · GENERATED {fmtTime(fusion.generated_at)} UTC · NEXT ~5MIN
                </span>
              )}
              {fusion.live_price_used && (
                <span style={{ fontSize: '9px', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono, monospace',
                  color: '#22c55e', background: 'rgba(34,197,94,0.08)', padding: '1px 6px',
                  border: '1px solid rgba(34,197,94,0.25)', borderRadius: '2px', display: 'inline-block', marginTop: '1px' }}>
                  ◎ ANCHORED TO LIVE ${fusion.live_price_used.toFixed(2)} [{(fusion.live_price_src || 'oanda').toUpperCase()}]
                </span>
              )}
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '13px', fontWeight: 800, color: DIR_COLOR[fusion.direction === 'LONG' ? 'bullish' : fusion.direction === 'SHORT' ? 'bearish' : 'neutral'] }}>
                {fusion.direction === 'LONG' ? '▲ LONG' : fusion.direction === 'SHORT' ? '▼ SHORT' : '· NEUTRAL'}
              </span>
              <span style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '2px', letterSpacing: '0.08em',
                color: QUALITY_COLOR[fusion.setup_quality] || '#6b7494',
                background: `${QUALITY_COLOR[fusion.setup_quality] || '#6b7494'}14`,
                border: `1px solid ${QUALITY_COLOR[fusion.setup_quality] || '#6b7494'}40` }}>
                {fusion.setup_quality?.replace('_', ' ')}
              </span>
              <span style={{ fontSize: '11px', color: '#4a5068' }}>{fusion.probability}% PROB</span>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '8px' }}>
            <div>
              <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.12em' }}>ENTRY ZONE</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#ff7744' }}>{fusion.entry_zone || '—'}</div>
            </div>
            <div>
              <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.12em' }}>INVALIDATION</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#ef4444' }}>{fusion.invalidation || '—'}</div>
            </div>
            <div>
              <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.12em' }}>TARGET 1</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#22c55e' }}>{fusion.first_target || '—'}</div>
            </div>
            <div>
              <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.12em' }}>TARGET 2</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#22c55e' }}>{fusion.second_target || '—'}</div>
            </div>
          </div>

          {fusion.entry_rationale && (
            <div style={{ fontSize: '11px', color: '#6b7494', lineHeight: 1.5 }}>
              <span style={{ color: '#4a5068' }}>ENTRY: </span>{fusion.entry_rationale}
            </div>
          )}
          {fusion.target_rationale && (
            <div style={{ fontSize: '11px', color: '#6b7494', lineHeight: 1.5 }}>
              <span style={{ color: '#4a5068' }}>TARGETS: </span>{fusion.target_rationale}
            </div>
          )}
          {fusion.timeframe_alignment && (
            <div style={{ fontSize: '11px', color: '#6b7494', lineHeight: 1.5 }}>
              <span style={{ color: '#4a5068' }}>TF ALIGNMENT: </span>{fusion.timeframe_alignment}
            </div>
          )}
          {fusion.reasoning && (
            <div style={{ fontSize: '11px', color: '#9ca3af', lineHeight: 1.5, fontStyle: 'italic' }}>
              {fusion.reasoning}
            </div>
          )}
          {fusion.risk_note && (
            <div style={{ fontSize: '10px', color: '#ffb347', lineHeight: 1.5 }}>
              <span style={{ color: '#4a5068' }}>RISK: </span>{fusion.risk_note}
            </div>
          )}
          {fusion.entry_error && (
            <div style={{ fontSize: '9px', color: '#ef4444', letterSpacing: '0.08em', padding: '4px 8px', background: 'rgba(239,68,68,0.10)', borderRadius: '2px', border: '1px solid rgba(239,68,68,0.3)' }}>
              ⛔ {fusion.entry_error}
            </div>
          )}
          {fusion.target_error && (
            <div style={{ fontSize: '9px', color: '#ef4444', letterSpacing: '0.08em', padding: '4px 8px', background: 'rgba(239,68,68,0.08)', borderRadius: '2px', border: '1px solid rgba(239,68,68,0.2)' }}>
              ⚠ {fusion.target_error} — targets will refresh next cycle
            </div>
          )}
        </div>
      )}
      {fusion?.error && (
        <div style={{ padding: '10px', fontSize: '10px', color: '#4a5068', letterSpacing: '0.1em', textAlign: 'center' }}>
          FUSION THESIS UNAVAILABLE — {fusion.error}
        </div>
      )}
      </div>

      {/* ── Kronos-mini probabilistic forecast panel ────────────────────── */}
      <KronosSection kronos={kronos} accuracy={kronosAccuracy} />

    </div>
  )
}

// ── Kronos sub-component ─────────────────────────────────────────────────────

function KronosSection({ kronos, accuracy }: { kronos: any; accuracy: any }) {
  const TF_ORDER = ['15min', '1h', '4h'] as const

  const allOffline = !kronos || TF_ORDER.every(tf => !kronos[tf]?.available)

  const accBadge = (tf: string) => {
    const a = accuracy?.[tf]
    if (!a || a.n === 0) return { label: 'UNPROVEN (no data)', color: '#4a5068' }
    if (a.trusted)       return { label: `TRUSTED ${a.hit_rate}% (n=${a.n})`, color: '#22c55e' }
    return { label: `UNPROVEN ${a.hit_rate ?? '?'}% (n=${a.n})`, color: '#ffb347' }
  }

  return (
    <div style={{ position: 'relative' }}>
      {/* Greyed overlay when all offline */}
      {allOffline && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 2,
          background: 'rgba(10,12,20,0.72)', borderRadius: '2px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <span style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.14em' }}>
            KRONOS OFFLINE — SET KRONOS_SERVICE_URL TO ENABLE
          </span>
        </div>
      )}

      <div style={{ padding: '12px', border: '1px solid rgba(96,165,250,0.14)', borderRadius: '2px', background: 'rgba(96,165,250,0.02)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.14em', color: '#60a5fa' }}>
          ◈ KRONOS-MINI PROBABILISTIC FORECAST
        </div>
        <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono, monospace', marginTop: '-4px' }}>
          TIME-SERIES MODEL · MEASURED SECOND OPINION · TRUST GROWS WITH SAMPLE SIZE
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
          {TF_ORDER.map(tf => {
            const fc  = kronos?.[tf]
            const avail = fc?.available === true
            const badge = accBadge(tf)
            const dirColor = fc?.direction === 'bullish' ? '#22c55e' : fc?.direction === 'bearish' ? '#ef4444' : '#6b7494'

            return (
              <div key={tf} style={{ padding: '10px', border: '1px solid rgba(96,165,250,0.1)', borderRadius: '2px', display: 'flex', flexDirection: 'column', gap: '4px', opacity: avail ? 1 : 0.35 }}>
                <div style={{ fontSize: '10px', fontWeight: 700, color: '#60a5fa', letterSpacing: '0.08em' }}>{tf.toUpperCase()}</div>

                {avail ? (
                  <>
                    <div style={{ fontSize: '12px', fontWeight: 800, color: dirColor }}>
                      {fc.direction === 'bullish' ? '▲' : '▼'} {fc.direction?.toUpperCase()}
                    </div>
                    <div style={{ fontSize: '11px', color: '#ff7744', fontWeight: 700 }}>
                      {fc.expected_move_pts > 0 ? '+' : ''}{fc.expected_move_pts} pts
                    </div>
                    <div style={{ fontSize: '10px', color: '#6b7494' }}>
                      → {fc.predicted_close}
                    </div>
                    <div style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.06em' }}>
                      range {fc.predicted_low}–{fc.predicted_high}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: '10px', color: '#4a5068' }}>offline</div>
                )}

                <div style={{ fontSize: '8px', color: badge.color, letterSpacing: '0.06em', marginTop: '2px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '4px' }}>
                  {badge.label}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
