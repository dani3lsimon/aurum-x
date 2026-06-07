'use client'
import { useEffect, useState } from 'react'
import { useCOTCountdown } from '@/hooks/useCOTCountdown'

interface COTWeek {
  date: string
  mm_long: number
  mm_short: number
  mm_net: number
  mm_net_pct_oi: number
  comm_net: number
  open_interest: number
}

interface COTData {
  source?: string
  dataset?: string
  weeks_analysed?: number
  trend_8w?: string
  net_change_8w?: number
  current_streak?: number
  streak_direction?: string
  pct_of_8w_range?: number
  is_extreme_long?: boolean
  is_extreme_short?: boolean
  latest?: COTWeek
  all_weeks?: COTWeek[]
  error?: string
}

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

const FS = { label: '0.68rem', value: '0.8rem', meta: '0.7rem', big: '1.05rem' }

export default function COTPanel() {
  const countdown = useCOTCountdown()
  const [cot, setCot] = useState<COTData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${BACKEND}/agents/cot`)
      .then(r => r.json())
      .then(d => { setCot(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  // Auto-refresh ~70 minutes after release (CFTC publishes ~1hr after the 20:30 UTC mark)
  useEffect(() => {
    if (!countdown.justReleased) return
    const t = setTimeout(() => {
      fetch(`${BACKEND}/agents/cot/refresh`)
        .then(r => r.json())
        .then(d => setCot(d))
        .catch(() => {})
    }, 70 * 60 * 1000)
    return () => clearTimeout(t)
  }, [countdown.justReleased])

  const latest = cot?.latest
  const weeks  = cot?.all_weeks ?? []

  const countdownColor = countdown.isLive ? '#00ff88'
    : countdown.isImminent ? '#ffb347'
    : countdown.isToday ? '#ff6633'
    : '#4a5068'

  const shouldFlash = countdown.isImminent || countdown.isLive

  return (
    <div className="aurum-card p-4 flex flex-col gap-3 h-full" style={{ minWidth: 0, overflow: 'hidden' }}>
      <div className="flex items-center justify-between">
        <div>
          <div className="section-label">Speculative Positioning — Managed Money</div>
          <div style={{ fontSize: '0.62rem', color: '#4a5068', letterSpacing: '0.1em', marginTop: '2px' }}>
            HEDGE FUNDS · CTAS · COMMODITY POOL OPERATORS — CFTC PUBLIC DATA
          </div>
        </div>
        <div className="live-badge">CFTC</div>
      </div>

      {/* ── Countdown to next release ─────────────────────────── */}
      <div style={{
        border: `1px solid ${countdownColor}66`,
        borderRadius: '2px',
        padding: '10px 12px',
        background: countdown.isLive ? 'rgba(0,255,136,0.06)'
          : countdown.isImminent ? 'rgba(255,179,71,0.06)'
          : 'rgba(255,80,0,0.04)',
        animation: shouldFlash ? 'glowPulse 1s ease-in-out infinite' : 'none',
      }}>
        <div className="flex items-center justify-between">
          <div>
            <div style={{ fontSize: '0.62rem', letterSpacing: '0.12em', color: '#6b7494', marginBottom: '4px' }}>
              NEXT COT RELEASE — LOCAL TIME
            </div>
            <div style={{ fontSize: FS.value, letterSpacing: '0.06em', color: countdownColor, fontWeight: 600 }}>
              {countdown.dayLabel} · {countdown.localTimeString}
            </div>
          </div>
          <div style={{
            fontSize: countdown.isLive ? '0.85rem' : '1.05rem',
            fontWeight: 800,
            color: countdownColor,
            textShadow: shouldFlash ? `0 0 12px ${countdownColor}` : 'none',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            {countdown.formattedCountdown}
          </div>
        </div>

        {countdown.isImminent && !countdown.isLive && (
          <div style={{ marginTop: '6px', fontSize: FS.meta, color: '#ffb347', letterSpacing: '0.08em' }}>
            ⚠ INCOMING — NEW DATA IN {countdown.minutesUntil} MIN
          </div>
        )}
        {countdown.isLive && (
          <div style={{ marginTop: '6px', fontSize: FS.meta, color: '#00ff88', letterSpacing: '0.08em', animation: 'glowPulse 0.5s ease-in-out infinite' }}>
            ● CFTC RELEASING DATA NOW
          </div>
        )}
        {countdown.justReleased && (
          <div style={{ marginTop: '6px', fontSize: FS.meta, color: '#00ff88', letterSpacing: '0.08em' }}>
            ✓ RELEASED — auto-refresh scheduled
          </div>
        )}
      </div>

      {/* ── Live data / no-data states ────────────────────────── */}
      {loading && (
        <div style={{ fontSize: FS.meta, color: '#4a5068', textAlign: 'center', padding: '16px' }}>
          FETCHING CFTC DATA...
        </div>
      )}

      {!loading && cot?.error && (
        <div style={{
          fontSize: FS.meta, color: '#ef4444', padding: '10px 12px',
          background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.25)',
        }}>
          ⚠ NO DATA — {cot.error}
        </div>
      )}

      {!loading && latest && !cot?.error && (
        <>
          {(cot?.is_extreme_long || cot?.is_extreme_short) && (
            <div style={{
              background: cot.is_extreme_long ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
              border: `1px solid ${cot.is_extreme_long ? 'rgba(239,68,68,0.4)' : 'rgba(34,197,94,0.4)'}`,
              borderRadius: '2px', padding: '7px 10px',
              fontSize: FS.meta, letterSpacing: '0.08em', fontWeight: 600,
              color: cot.is_extreme_long ? '#ef4444' : '#22c55e',
              animation: 'glowPulse 2s ease-in-out infinite',
            }}>
              {cot.is_extreme_long
                ? '⚠ EXTREME LONG — CROWDED — REVERSAL RISK'
                : '● EXTREME SHORT — COILED — SQUEEZE / BULL RISK'}
            </div>
          )}

          {/* Key metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
            {[
              { label: 'MM NET LONG',  value: `${latest.mm_net >= 0 ? '+' : ''}${(latest.mm_net / 1000).toFixed(1)}K`, color: latest.mm_net >= 0 ? '#22c55e' : '#ef4444' },
              { label: 'MM % OF OI',   value: `${latest.mm_net_pct_oi}%`, color: '#ffb347' },
              { label: 'MM LONG/SHORT',value: `${(latest.mm_long/1000).toFixed(0)}K / ${(latest.mm_short/1000).toFixed(0)}K`, color: '#6b7494' },
              { label: 'OPEN INTEREST',value: `${(latest.open_interest/1000).toFixed(0)}K`, color: '#6b7494' },
            ].map(m => (
              <div key={m.label} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)', padding: '8px 10px' }}>
                <div style={{ fontSize: '0.62rem', color: '#4a5068', letterSpacing: '0.1em', marginBottom: '3px' }}>{m.label}</div>
                <div style={{ fontSize: FS.value, fontWeight: 700, color: m.color }}>{m.value}</div>
              </div>
            ))}
          </div>

          {/* Trend / streak / range */}
          <div className="flex justify-between items-center" style={{ paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
            <div>
              <div style={{ fontSize: '0.62rem', color: '#4a5068', letterSpacing: '0.1em' }}>8W TREND</div>
              <div style={{ fontSize: FS.value, fontWeight: 700, color: cot?.trend_8w === 'up' ? '#22c55e' : '#ef4444', marginTop: '2px' }}>
                {cot?.trend_8w === 'up' ? '▲' : '▼'} {cot?.trend_8w?.toUpperCase()}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.62rem', color: '#4a5068', letterSpacing: '0.1em' }}>STREAK</div>
              <div style={{ fontSize: FS.value, fontWeight: 700, color: '#ffb347', marginTop: '2px' }}>
                {cot?.current_streak}W {cot?.streak_direction?.toUpperCase()}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.62rem', color: '#4a5068', letterSpacing: '0.1em' }}>RANGE %</div>
              <div style={{ fontSize: FS.value, fontWeight: 700, color: '#ffb347', marginTop: '2px' }}>
                {cot?.pct_of_8w_range}%
              </div>
            </div>
          </div>

          {/* Sparkline — 8 week MM net */}
          {weeks.length > 1 && (
            <div>
              <div style={{ fontSize: '0.62rem', color: '#4a5068', letterSpacing: '0.1em', marginBottom: '6px' }}>
                8-WEEK MANAGED-MONEY NET POSITION
              </div>
              <div className="flex items-end gap-1" style={{ height: '36px' }}>
                {(() => {
                  const vals = weeks.map(w => w.mm_net)
                  const min = Math.min(...vals), max = Math.max(...vals)
                  const range = max - min || 1
                  return vals.map((v, i) => {
                    const h = Math.max(4, ((v - min) / range) * 36)
                    const isLatest = i === vals.length - 1
                    return (
                      <div key={i} style={{
                        flex: 1, height: `${h}px`,
                        background: isLatest ? '#ff4400' : (v >= 0 ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)'),
                        borderRadius: '1px',
                        boxShadow: isLatest ? '0 0 6px rgba(255,80,0,0.6)' : 'none',
                        transition: 'height 0.5s ease',
                      }} />
                    )
                  })
                })()}
              </div>
              <div className="flex justify-between" style={{ marginTop: '3px' }}>
                <span style={{ fontSize: '0.6rem', color: '#4a5068' }}>{weeks[0]?.date?.slice(5)}</span>
                <span style={{ fontSize: '0.6rem', color: '#ff4400' }}>{weeks[weeks.length - 1]?.date?.slice(5)} ◀ latest</span>
              </div>
            </div>
          )}

          <div style={{ fontSize: '0.62rem', color: '#4a5068', textAlign: 'right' }}>
            DATA AS OF {latest.date} · SOURCE: PUBLICREPORTING.CFTC.GOV
          </div>
        </>
      )}
    </div>
  )
}
