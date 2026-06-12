'use client'
import { useState, useEffect, useMemo, Fragment } from 'react'

const BACKEND    = process.env.NEXT_PUBLIC_BACKEND_URL || ''
const REFRESH_MS = 5 * 60_000

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

interface EventPattern {
  event_type:           string
  total_events:         number
  pre_15m_opposite_pct: number | null
  pre_1h_opposite_pct:  number | null
  avg_post_15m_abs:     number | null
  avg_post_30m_abs:     number | null
  avg_post_1h_abs:      number | null
  surprise_align_pct:   number | null
  last_updated:         string
}

const IMPACT_COLOR: Record<string, string> = {
  high:   '#ef4444',
  medium: '#ffb347',
}

const CURRENCY_FLAGS: Record<string, string> = {
  USD: '🇺🇸', EUR: '🇪🇺', GBP: '🇬🇧', JPY: '🇯🇵',
  CHF: '🇨🇭', CNY: '🇨🇳', CAD: '🇨🇦', AUD: '🇦🇺', NZD: '🇳🇿',
}

const EVENT_TYPE_RULES: Array<[string, string[]]> = [
  ['CPI',              ['cpi', 'consumer price']],
  ['NFP',              ['nonfarm', 'non-farm', 'nfp', 'employment']],
  ['FOMC',             ['fomc', 'federal funds', 'interest rate']],
  ['GDP',              ['gdp']],
  ['PCE',              ['pce', 'personal consumption']],
  ['PPI',              ['ppi', 'producer price']],
  ['Retail Sales',     ['retail sales']],
  ['ISM Manufacturing',['ism manufacturing']],
  ['ISM Services',     ['ism services', 'ism non-manufacturing']],
  ['Jobless Claims',   ['initial jobless', 'unemployment claims']],
  ['Michigan Sentiment',['michigan', 'uom', 'consumer sentiment', 'consumer confidence']],
  ['Durable Goods',    ['durable goods']],
  ['JOLTS',            ['jolts', 'job openings']],
  ['Housing Starts',   ['housing starts', 'building permits']],
  ['Trade Balance',    ['trade balance', 'trade deficit']],
]

function normalizeEventType(name: string): string | null {
  const n = name.toLowerCase()
  for (const [label, keywords] of EVENT_TYPE_RULES) {
    if (keywords.some(kw => n.includes(kw))) return label
  }
  return null
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
  if (diff < -60_000) return { text: 'RELEASED', isNow: false, isPast: true }
  if (diff <= 0)      return { text: '◆ NOW',    isNow: true,  isPast: false }
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor((diff % 3_600_000) / 60_000)
  const s = Math.floor((diff % 60_000) / 1_000)
  return { text: `${h > 0 ? `${h}h ` : ''}${m}m ${String(s).padStart(2, '0')}s`, isNow: false, isPast: false }
}

function fmtLondon(iso: string): string {
  try {
    const d    = new Date(iso)
    const date = d.toLocaleDateString('en-GB',  { timeZone: 'Europe/London', day: '2-digit', month: 'short' })
    const time = d.toLocaleTimeString('en-GB',  { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit', hour12: false })
    return `${date} ${time} LON`
  } catch { return iso }
}

function PatternBadge({ pattern }: { pattern: EventPattern | undefined }) {
  if (!pattern || pattern.total_events < 5 || pattern.pre_15m_opposite_pct === null) {
    return <span style={{ color: '#3a3f52', fontSize: '10px' }}>—</span>
  }
  const pct = pattern.pre_15m_opposite_pct
  let label: string, color: string
  if (pct >= 60) {
    label = `FADES ${pct.toFixed(0)}%`; color = '#22c55e'
  } else if (pct <= 40) {
    label = `TRENDS ${(100 - pct).toFixed(0)}%`; color = '#ef4444'
  } else {
    label = `MIX ${pct.toFixed(0)}%`; color = '#6b7494'
  }
  return (
    <span style={{
      padding: '2px 6px', borderRadius: '2px', fontSize: '9px',
      letterSpacing: '0.08em', fontWeight: 600, color,
      background: `${color}14`, border: `1px solid ${color}30`, whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  )
}

function PatternDetail({ pattern }: { pattern: EventPattern }) {
  const rows: Array<[string, string]> = [
    ['SAMPLE SIZE',  `${pattern.total_events} events`],
    ['PRE-15m FADES', pattern.pre_15m_opposite_pct !== null ? `${pattern.pre_15m_opposite_pct.toFixed(1)}%` : '—'],
    ['PRE-1h FADES',  pattern.pre_1h_opposite_pct  !== null ? `${pattern.pre_1h_opposite_pct.toFixed(1)}%`  : '—'],
    ['AVG MOVE 15m',  pattern.avg_post_15m_abs      !== null ? `${pattern.avg_post_15m_abs.toFixed(2)}%`     : '—'],
    ['AVG MOVE 30m',  pattern.avg_post_30m_abs      !== null ? `${pattern.avg_post_30m_abs.toFixed(2)}%`     : '—'],
    ['AVG MOVE 1h',   pattern.avg_post_1h_abs       !== null ? `${pattern.avg_post_1h_abs.toFixed(2)}%`      : '—'],
  ]
  return (
    <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', padding: '2px 0' }}>
      {rows.map(([k, v]) => (
        <div key={k} style={{ fontSize: '9px', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono, monospace' }}>
          <span style={{ color: '#4a5068' }}>{k}: </span>
          <span style={{ color: '#e5e7eb', fontWeight: 600 }}>{v}</span>
        </div>
      ))}
      {pattern.last_updated && (
        <div style={{ fontSize: '9px', color: '#2a2d3a', letterSpacing: '0.08em', marginLeft: 'auto' }}>
          updated {pattern.last_updated.slice(0, 10)}
        </div>
      )}
    </div>
  )
}

export default function EconomicCalendarPanel() {
  const [events,   setEvents]   = useState<EconomicEvent[]>([])
  const [patterns, setPatterns] = useState<EventPattern[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [filter,   setFilter]   = useState<'all' | 'gold'>('gold')
  const [expanded, setExpanded] = useState<number | null>(null)
  const tick = useCountdownTick()

  const fetchEvents = async () => {
    try {
      const data = await fetch(`${BACKEND}/forecast/economic-calendar?days=7`).then(r => r.json())
      if (data.status === 'ok') { setEvents(data.events || []); setError(null) }
      else setError(data.message || 'API error')
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }

  const fetchPatterns = async () => {
    try {
      const data = await fetch(`${BACKEND}/forecast/event-patterns`).then(r => r.json())
      if (data.status === 'ok') setPatterns(data.patterns || [])
    } catch { /* patterns are optional — silently skip */ }
  }

  useEffect(() => {
    fetchEvents()
    fetchPatterns()
    const iv = setInterval(fetchEvents, REFRESH_MS)
    return () => clearInterval(iv)
  }, [])

  const patternMap = useMemo(
    () => new Map(patterns.map(p => [p.event_type, p])),
    [patterns]
  )

  const now     = Date.now()
  const visible = events
    .filter(e => new Date(e.date).getTime() >= now - 60_000)
    .filter(e => filter === 'all' || e.gold_relevant)

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
            NEXT 7 DAYS · MEDIUM + HIGH IMPACT · LONDON TIME (UTC+1)
          </span>
        </div>
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

      {nextEvent && <NextEventBanner event={nextEvent} tick={tick} />}

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
                  {['TIME (LONDON)', 'COUNTDOWN', 'CCY', 'EVENT', 'IMPACT', 'PATTERN', 'ACTUAL', 'FCST', 'PREV'].map(h => (
                    <th key={h} style={{
                      padding: '6px 10px',
                      textAlign: h === 'ACTUAL' || h === 'FCST' || h === 'PREV' ? 'right' : 'left',
                      fontSize: '9px',
                      color: h === 'PATTERN' ? 'rgba(255,119,68,0.6)' : '#4a5068',
                      letterSpacing: '0.12em', fontWeight: 600, whiteSpace: 'nowrap',
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((ev, i) => {
                  const cd          = formatCountdown(ev.date)
                  const isNext      = i === 0
                  const rowBg       = cd.isNow ? 'rgba(255,179,71,0.08)' : isNext ? 'rgba(255,80,0,0.04)' : 'transparent'
                  const impactColor = IMPACT_COLOR[ev.impact] || '#6b7494'
                  const flag        = CURRENCY_FLAGS[ev.currency] || ''
                  const etype       = normalizeEventType(ev.event)
                  const pat         = etype ? patternMap.get(etype) : undefined
                  const isExpanded  = expanded === i
                  const hasPattern  = pat && pat.total_events >= 5 && pat.pre_15m_opposite_pct !== null
                  return (
                    <Fragment key={i}>
                      <tr
                        onClick={() => hasPattern && setExpanded(isExpanded ? null : i)}
                        style={{
                          borderBottom: '1px solid rgba(255,255,255,0.03)',
                          background: rowBg, transition: 'background 0.3s',
                          cursor: hasPattern ? 'pointer' : 'default',
                        }}
                      >
                        <td style={{ padding: '8px 10px', color: '#6b7494', whiteSpace: 'nowrap', fontSize: '10px' }}>
                          {fmtLondon(ev.date)}
                        </td>
                        <td style={{
                          padding: '8px 10px', whiteSpace: 'nowrap',
                          color:     cd.isNow ? '#ffb347' : cd.isPast ? '#4a5068' : '#e5e7eb',
                          fontWeight: cd.isNow ? 800 : 400,
                          animation:  cd.isNow ? 'glowPulse 0.8s ease-in-out infinite' : 'none',
                        }}>
                          {cd.text}
                        </td>
                        <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                          <span style={{ fontSize: '13px' }}>{flag}</span>
                          <span style={{ marginLeft: '4px', color: '#9ca3af', fontSize: '10px' }}>{ev.currency}</span>
                        </td>
                        <td style={{ padding: '8px 10px', maxWidth: '220px', lineHeight: 1.4 }}>
                          <span style={{ color: ev.gold_relevant ? '#ff7744' : '#e5e7eb' }}>
                            {ev.gold_relevant && <span style={{ color: '#ffb347', marginRight: '4px' }}>◈</span>}
                            {ev.event}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                          <span style={{
                            padding: '2px 7px', borderRadius: '2px', fontSize: '9px',
                            letterSpacing: '0.1em', fontWeight: 700,
                            color: impactColor, background: `${impactColor}14`, border: `1px solid ${impactColor}40`,
                          }}>
                            {ev.impact.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                          <PatternBadge pattern={pat} />
                          {hasPattern && (
                            <span style={{ fontSize: '8px', color: '#4a5068', marginLeft: '4px' }}>
                              {isExpanded ? '▲' : '▼'}
                            </span>
                          )}
                        </td>
                        <td style={{
                          padding: '8px 10px', textAlign: 'right', whiteSpace: 'nowrap',
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
                      {isExpanded && pat && (
                        <tr style={{ background: 'rgba(255,255,255,0.015)' }}>
                          <td colSpan={9} style={{
                            padding: '8px 16px 10px',
                            borderBottom: '1px solid rgba(255,255,255,0.06)',
                          }}>
                            <PatternDetail pattern={pat} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      <div style={{ fontSize: '9px', color: '#2a2d3a', letterSpacing: '0.1em', marginTop: 'auto', paddingTop: '8px' }}>
        ◈ = GOLD-RELEVANT · PATTERN = PRE-15m FADE RATE · CLICK ROW FOR DETAILS · DATA: FOREXFACTORY / FRED
      </div>
    </div>
  )
}

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
        {fmtLondon(event.date)}
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
