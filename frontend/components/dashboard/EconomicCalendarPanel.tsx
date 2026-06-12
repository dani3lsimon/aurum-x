'use client'
import { useState, useEffect, useRef } from 'react'

const BACKEND     = process.env.NEXT_PUBLIC_BACKEND_URL || ''
const REFRESH_MS  = 5 * 60_000   // 5 min — matches backend cache TTL

interface EconomicEvent {
  date:          string
  country:       string
  currency:      string
  event:         string
  impact:        'medium' | 'high'
  actual:        string | null
  forecast:      string | null
  previous:      string | null
  gold_relevant: boolean
}

const IMPACT_COLOR: Record<string, string> = {
  high:   '#ef4444',
  medium: '#ffb347',
}

const CURRENCY_FLAGS: Record<string, string> = {
  USD: '🇺🇸', EUR: '🇪🇺', GBP: '🇬🇧', JPY: '🇯🇵',
  CHF: '🇨🇭', CNY: '🇨🇳', CAD: '🇨🇦', AUD: '🇦🇺', NZD: '🇳🇿',
}

function useCountdownTick() {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 1000)
    return () => clearInterval(t)
  }, [])
  return tick
}

function formatCountdown(isoDate: string): { text: string; isNow: boolean; isPast: boolean } {
  const diff = new Date(isoDate).getTime() - Date.now()
  if (diff < -60_000)  return { text: 'RELEASED', isNow: false, isPast: true }
  if (diff <= 0)       return { text: '◆ NOW',     isNow: true,  isPast: false }
  const h   = Math.floor(diff / 3_600_000)
  const m   = Math.floor((diff % 3_600_000) / 60_000)
  const s   = Math.floor((diff % 60_000) / 1_000)
  const hStr = h > 0 ? `${h}h ` : ''
  return { text: `${hStr}${m}m ${String(s).padStart(2, '0')}s`, isNow: false, isPast: false }
}

function fmtUTC(iso: string): string {
  try {
    return new Date(iso).toISOString().replace('T', ' ').slice(0, 16) + ' UTC'
  } catch { return iso }
}

export default function EconomicCalendarPanel() {
  const [events,  setEvents]  = useState<EconomicEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [filter,  setFilter]  = useState<'all' | 'gold'>('gold')
  const tick = useCountdownTick()   // triggers re-render every second for live countdowns

  const fetchEvents = async () => {
    try {
      const data = await fetch(`${BACKEND}/forecast/economic-calendar?days=7`).then(r => r.json())
      if (data.status === 'ok') {
        setEvents(data.events || [])
        setError(null)
      } else {
        setError(data.message || 'API error')
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchEvents()
    const iv = setInterval(fetchEvents, REFRESH_MS)
    return () => clearInterval(iv)
  }, [])

  const now       = Date.now()
  const visible   = events
    .filter(e => new Date(e.date).getTime() >= now - 60_000)   // 1 min grace
    .filter(e => filter === 'all' || e.gold_relevant)

  // Next upcoming event for the banner
  const nextEvent = events.find(e => new Date(e.date).getTime() >= now)

  return (
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', minHeight: '400px' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <span style={{ fontSize: '12px', fontWeight: 800, letterSpacing: '0.16em', color: '#ff7744' }}>
            ◆ ECONOMIC CALENDAR
          </span>
          <span style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.1em', marginLeft: '10px', fontFamily: 'JetBrains Mono, monospace' }}>
            NEXT 7 DAYS · MEDIUM + HIGH IMPACT
          </span>
        </div>

        {/* Filter toggle */}
        <div style={{ display: 'flex', gap: '4px' }}>
          {(['gold', 'all'] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '3px 10px', fontSize: '9px', letterSpacing: '0.1em',
              fontFamily: 'JetBrains Mono, monospace',
              background: filter === f ? 'rgba(255,119,68,0.15)' : 'transparent',
              border: `1px solid ${filter === f ? 'rgba(255,119,68,0.5)' : 'rgba(255,255,255,0.06)'}`,
              borderRadius: '2px',
              color: filter === f ? '#ff7744' : '#4a5068',
              cursor: 'pointer',
            }}>
              {f === 'gold' ? '◈ GOLD' : 'ALL'}
            </button>
          ))}
        </div>
      </div>

      {/* Next event banner */}
      {nextEvent && (
        <NextEventBanner event={nextEvent} tick={tick} />
      )}

      {/* Loading / error */}
      {loading && (
        <div style={{ textAlign: 'center', fontSize: '10px', color: '#4a5068', letterSpacing: '0.14em', padding: '40px 0', animation: 'glowPulse 1s ease-in-out infinite' }}>
          LOADING CALENDAR...
        </div>
      )}
      {error && !loading && (
        <div style={{ padding: '12px', fontSize: '10px', color: '#ef4444', letterSpacing: '0.1em', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: '2px' }}>
          ⚠ {error}
        </div>
      )}

      {/* Table */}
      {!loading && !error && (
        visible.length === 0 ? (
          <div style={{ textAlign: 'center', fontSize: '10px', color: '#4a5068', letterSpacing: '0.12em', padding: '40px 0' }}>
            {filter === 'gold' ? 'NO GOLD-RELEVANT EVENTS UPCOMING — SWITCH TO ALL TO SEE ALL EVENTS' : 'NO UPCOMING EVENTS'}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                  {['TIME (UTC)', 'COUNTDOWN', 'CCY', 'EVENT', 'IMPACT', 'ACTUAL', 'FCST', 'PREV'].map(h => (
                    <th key={h} style={{ padding: '6px 10px', textAlign: h === 'ACTUAL' || h === 'FCST' || h === 'PREV' ? 'right' : 'left',
                      fontSize: '9px', color: '#4a5068', letterSpacing: '0.12em', fontWeight: 600, whiteSpace: 'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((ev, i) => {
                  const cd      = formatCountdown(ev.date)
                  const isNext  = i === 0
                  const rowBg   = cd.isNow
                    ? 'rgba(255,179,71,0.08)'
                    : isNext
                    ? 'rgba(255,80,0,0.04)'
                    : 'transparent'
                  const impactColor = IMPACT_COLOR[ev.impact] || '#6b7494'
                  const flag = CURRENCY_FLAGS[ev.currency] || ''
                  return (
                    <tr key={i} style={{
                      borderBottom: '1px solid rgba(255,255,255,0.03)',
                      background: rowBg,
                      transition: 'background 0.3s',
                    }}>
                      <td style={{ padding: '8px 10px', color: '#6b7494', whiteSpace: 'nowrap', fontSize: '10px' }}>
                        {fmtUTC(ev.date)}
                      </td>
                      <td style={{ padding: '8px 10px', whiteSpace: 'nowrap',
                        color:     cd.isNow ? '#ffb347' : cd.isPast ? '#4a5068' : '#e5e7eb',
                        fontWeight: cd.isNow ? 800 : 400,
                        animation: cd.isNow ? 'glowPulse 0.8s ease-in-out infinite' : 'none',
                      }}>
                        {cd.text}
                      </td>
                      <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                        <span style={{ fontSize: '13px' }}>{flag}</span>
                        <span style={{ marginLeft: '4px', color: '#9ca3af', fontSize: '10px' }}>{ev.currency}</span>
                      </td>
                      <td style={{ padding: '8px 10px', maxWidth: '260px', lineHeight: 1.4 }}>
                        <span style={{ color: ev.gold_relevant ? '#ff7744' : '#e5e7eb' }}>
                          {ev.gold_relevant && <span style={{ color: '#ffb347', marginRight: '4px' }}>◈</span>}
                          {ev.event}
                        </span>
                      </td>
                      <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                        <span style={{
                          padding: '2px 7px', borderRadius: '2px', fontSize: '9px',
                          letterSpacing: '0.1em', fontWeight: 700,
                          color: impactColor,
                          background: `${impactColor}14`,
                          border: `1px solid ${impactColor}40`,
                        }}>
                          {ev.impact.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', whiteSpace: 'nowrap',
                        color: ev.actual != null ? '#22c55e' : '#4a5068',
                        fontWeight: ev.actual != null ? 700 : 400,
                      }}>
                        {ev.actual ?? '—'}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', whiteSpace: 'nowrap', color: '#6b7494' }}>
                        {ev.forecast ?? '—'}
                      </td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', whiteSpace: 'nowrap', color: '#4a5068' }}>
                        {ev.previous ?? '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      <div style={{ fontSize: '9px', color: '#2a2d3a', letterSpacing: '0.1em', marginTop: 'auto', paddingTop: '8px' }}>
        ◈ = GOLD-RELEVANT EVENT · DATA: FINNHUB · REFRESHES EVERY 5 MIN
      </div>
    </div>
  )
}

// Inline next-event banner used inside the calendar tab
function NextEventBanner({ event, tick }: { event: EconomicEvent; tick: number }) {
  const cd = formatCountdown(event.date)
  if (cd.isPast) return null
  const impactColor = IMPACT_COLOR[event.impact] || '#ffb347'
  return (
    <div style={{
      padding: '8px 14px',
      background: 'rgba(255,80,0,0.04)',
      border: `1px solid ${cd.isNow ? 'rgba(255,179,71,0.5)' : 'rgba(255,80,0,0.15)'}`,
      borderRadius: '2px',
      display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
    }}>
      <span style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.14em', whiteSpace: 'nowrap' }}>NEXT EVENT</span>
      <span style={{ fontSize: '11px', fontWeight: 700, color: event.gold_relevant ? '#ff7744' : '#e5e7eb', flex: 1, minWidth: '120px' }}>
        {event.gold_relevant && <span style={{ color: '#ffb347', marginRight: '6px' }}>◈</span>}
        {event.event}
      </span>
      <span style={{ fontSize: '9px', color: '#6b7494', letterSpacing: '0.1em', whiteSpace: 'nowrap', fontFamily: 'JetBrains Mono, monospace' }}>
        {fmtUTC(event.date)}
      </span>
      <span style={{
        fontSize: '12px', fontWeight: 800, fontFamily: 'JetBrains Mono, monospace',
        color: cd.isNow ? '#ffb347' : '#e5e7eb',
        minWidth: '90px', textAlign: 'right', whiteSpace: 'nowrap',
        animation: cd.isNow ? 'glowPulse 0.8s ease-in-out infinite' : 'none',
      }}>
        {cd.text}
      </span>
      <span style={{
        padding: '2px 8px', borderRadius: '2px', fontSize: '9px', letterSpacing: '0.1em',
        color: impactColor, background: `${impactColor}14`, border: `1px solid ${impactColor}40`,
        fontWeight: 700, whiteSpace: 'nowrap',
      }}>
        {event.impact.toUpperCase()}
      </span>
    </div>
  )
}
