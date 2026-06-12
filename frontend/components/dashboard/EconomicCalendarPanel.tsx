'use client'
import { useState, useEffect, useMemo, Fragment, useCallback } from 'react'

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
  event_type:              string
  total_events:            number
  pre_15m_opposite_pct:    number | null
  pre_1h_opposite_pct:     number | null
  avg_post_15m_abs:        number | null
  avg_post_30m_abs:        number | null
  avg_post_1h_abs:         number | null
  surprise_align_pct:      number | null
  recent_events:           number | null
  recent_pre_15m_opp_pct:  number | null
  recent_pre_1h_opp_pct:   number | null
  recent_avg_post_15m_abs: number | null
  recent_avg_post_30m_abs: number | null
  recent_avg_post_1h_abs:  number | null
  last_updated:            string
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

function pct(v: number | null | undefined) {
  return v != null ? `${v.toFixed(1)}%` : '—'
}
function move(v: number | null | undefined) {
  return v != null ? `${v.toFixed(2)}%` : '—'
}
function delta(full: number | null | undefined, recent: number | null | undefined): { text: string; color: string } | null {
  if (full == null || recent == null) return null
  const d = recent - full
  if (Math.abs(d) < 1) return null
  return { text: `${d > 0 ? '▲' : '▼'}${Math.abs(d).toFixed(1)}`, color: d > 0 ? '#22c55e' : '#ef4444' }
}

function PatternDetail({ pattern }: { pattern: EventPattern }) {
  const hasRecent = (pattern.recent_events ?? 0) >= 2

  const rows: Array<{ label: string; full: string; recent: string | null; d: ReturnType<typeof delta> }> = [
    { label: 'PRE-15m FADES', full: pct(pattern.pre_15m_opposite_pct), recent: hasRecent ? pct(pattern.recent_pre_15m_opp_pct) : null, d: delta(pattern.pre_15m_opposite_pct, pattern.recent_pre_15m_opp_pct) },
    { label: 'PRE-1h FADES',  full: pct(pattern.pre_1h_opposite_pct),  recent: hasRecent ? pct(pattern.recent_pre_1h_opp_pct)  : null, d: delta(pattern.pre_1h_opposite_pct,  pattern.recent_pre_1h_opp_pct) },
    { label: 'AVG MOVE 15m',  full: move(pattern.avg_post_15m_abs),     recent: hasRecent ? move(pattern.recent_avg_post_15m_abs) : null, d: delta(pattern.avg_post_15m_abs, pattern.recent_avg_post_15m_abs) },
    { label: 'AVG MOVE 30m',  full: move(pattern.avg_post_30m_abs),     recent: hasRecent ? move(pattern.recent_avg_post_30m_abs) : null, d: delta(pattern.avg_post_30m_abs, pattern.recent_avg_post_30m_abs) },
    { label: 'AVG MOVE 1h',   full: move(pattern.avg_post_1h_abs),      recent: hasRecent ? move(pattern.recent_avg_post_1h_abs)  : null, d: delta(pattern.avg_post_1h_abs,  pattern.recent_avg_post_1h_abs) },
  ]

  const colStyle: React.CSSProperties = { padding: '3px 10px', textAlign: 'right', whiteSpace: 'nowrap', fontSize: '9px', fontFamily: 'JetBrains Mono, monospace' }
  const hdStyle:  React.CSSProperties = { ...colStyle, color: '#4a5068', letterSpacing: '0.1em', fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.04)', paddingBottom: '5px' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: '9px', fontFamily: 'JetBrains Mono, monospace' }}>
        <thead>
          <tr>
            <th style={{ ...hdStyle, textAlign: 'left', paddingLeft: 0 }}> </th>
            <th style={hdStyle}>FULL SAMPLE ({pattern.total_events})</th>
            {hasRecent && <th style={{ ...hdStyle, color: '#ff7744' }}>LAST {pattern.recent_events}</th>}
            {hasRecent && <th style={{ ...hdStyle, color: '#4a5068' }}>ΔCHANGE</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, full, recent, d }) => (
            <tr key={label} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
              <td style={{ ...colStyle, textAlign: 'left', paddingLeft: 0, color: '#4a5068', letterSpacing: '0.08em' }}>{label}</td>
              <td style={{ ...colStyle, color: '#9ca3af' }}>{full}</td>
              {hasRecent && <td style={{ ...colStyle, color: '#e5e7eb', fontWeight: 600 }}>{recent}</td>}
              {hasRecent && (
                <td style={{ ...colStyle, color: d?.color ?? '#2a2d3a', fontWeight: 600 }}>
                  {d?.text ?? '—'}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {pattern.last_updated && (
        <div style={{ fontSize: '8px', color: '#2a2d3a', letterSpacing: '0.08em' }}>
          updated {pattern.last_updated.slice(0, 10)}
        </div>
      )}
    </div>
  )
}

// key = "YYYY-MM-DD_event_name_slug"
function makeEventKey(ev: EconomicEvent): string {
  const slug = ev.event.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 40)
  return `${ev.date.slice(0, 10)}_${slug}`
}

// outcome: true=✓ correct, false=✗ wrong, undefined=unset
function OutcomeToggle({ value, onToggle, disabled }: { value: boolean | undefined; onToggle: () => void; disabled?: boolean }) {
  if (disabled) return null
  return (
    <span
      onClick={e => { e.stopPropagation(); onToggle() }}
      title={value === true ? 'Correct — click to mark wrong' : value === false ? 'Wrong — click to clear' : 'Click to mark correct'}
      style={{
        cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: '18px', height: '18px', borderRadius: '2px', fontSize: '11px', fontWeight: 800,
        border: `1px solid ${value === true ? 'rgba(34,197,94,0.4)' : value === false ? 'rgba(239,68,68,0.4)' : 'rgba(255,255,255,0.08)'}`,
        background: value === true ? 'rgba(34,197,94,0.1)' : value === false ? 'rgba(239,68,68,0.1)' : 'transparent',
        color: value === true ? '#22c55e' : value === false ? '#ef4444' : '#3a3f52',
        transition: 'all 0.15s',
      }}
    >
      {value === true ? '✓' : value === false ? '✗' : '○'}
    </span>
  )
}

export default function EconomicCalendarPanel() {
  const [events,   setEvents]   = useState<EconomicEvent[]>([])
  const [patterns, setPatterns] = useState<EventPattern[]>([])
  const [outcomes, setOutcomes] = useState<Map<string, boolean>>(new Map())
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [filter,   setFilter]   = useState<'all' | 'gold'>('gold')
  const [expanded, setExpanded] = useState<number | null>(null)
  const tick = useCountdownTick()

  const fetchEvents = async () => {
    try {
      const data = await fetch(`${BACKEND}/forecast/economic-calendar?days=28`).then(r => r.json())
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

  const fetchOutcomes = async () => {
    try {
      const data = await fetch(`${BACKEND}/forecast/calendar-outcomes`).then(r => r.json())
      if (data.status === 'ok') {
        const m = new Map<string, boolean>()
        for (const o of (data.outcomes || [])) m.set(o.event_key, o.correct)
        setOutcomes(m)
      }
    } catch { /* silently skip */ }
  }

  const handleOutcomeToggle = useCallback(async (ev: EconomicEvent, etype: string | null, predicted: string | null) => {
    const key     = makeEventKey(ev)
    const current = outcomes.get(key)
    const next    = current === undefined ? true : current === true ? false : undefined

    // Optimistic update
    setOutcomes(prev => {
      const m = new Map(prev)
      if (next === undefined) m.delete(key)
      else m.set(key, next)
      return m
    })

    if (next === undefined) {
      await fetch(`${BACKEND}/forecast/calendar-outcome/${encodeURIComponent(key)}`, { method: 'DELETE' })
    } else {
      await fetch(`${BACKEND}/forecast/calendar-outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_key:  key,
          event_name: ev.event,
          event_date: ev.date.slice(0, 10),
          event_type: etype,
          predicted,
          correct: next,
        }),
      })
    }
  }, [outcomes])

  useEffect(() => {
    fetchEvents()
    fetchPatterns()
    fetchOutcomes()
    const iv = setInterval(fetchEvents, REFRESH_MS)
    return () => clearInterval(iv)
  }, [])

  const patternMap = useMemo(
    () => new Map(patterns.map(p => [p.event_type, p])),
    [patterns]
  )

  const outcomeValues = useMemo(() => Array.from(outcomes.values()), [outcomes])
  const trackedTotal  = outcomeValues.length
  const trackedRight  = outcomeValues.filter(Boolean).length
  const accuracyPct   = trackedTotal > 0 ? Math.round(trackedRight / trackedTotal * 100) : null

  const now            = Date.now()
  const startOfTodayMs = new Date(now).setHours(0, 0, 0, 0)

  const allFiltered    = events.filter(e => filter === 'all' || e.gold_relevant)
  const releasedToday  = allFiltered.filter(e => {
    const t = new Date(e.date).getTime()
    return t >= startOfTodayMs && t < now - 60_000
  })
  const upcoming       = allFiltered.filter(e => new Date(e.date).getTime() >= now - 60_000)
  const visible        = [...releasedToday, ...upcoming.slice(0, 10)]

  const nextEvent = events.find(e => new Date(e.date).getTime() >= now)

  return (
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', minHeight: '400px' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', fontWeight: 800, letterSpacing: '0.16em', color: '#ff7744' }}>
            ◆ ECONOMIC CALENDAR
          </span>
          <span style={{ fontSize: '9px', color: '#4a5068', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono, monospace' }}>
            NEXT 10 EVENTS · MEDIUM + HIGH IMPACT · LONDON TIME (UTC+1)
          </span>
          {accuracyPct !== null && (
            <span style={{
              fontSize: '9px', letterSpacing: '0.1em', fontFamily: 'JetBrains Mono, monospace',
              color: accuracyPct >= 60 ? '#22c55e' : accuracyPct >= 45 ? '#ffb347' : '#ef4444',
              background: accuracyPct >= 60 ? 'rgba(34,197,94,0.08)' : accuracyPct >= 45 ? 'rgba(255,179,71,0.08)' : 'rgba(239,68,68,0.08)',
              border: `1px solid ${accuracyPct >= 60 ? 'rgba(34,197,94,0.25)' : accuracyPct >= 45 ? 'rgba(255,179,71,0.25)' : 'rgba(239,68,68,0.25)'}`,
              padding: '1px 7px', borderRadius: '2px',
            }}>
              YOUR ACCURACY {trackedRight}/{trackedTotal} ({accuracyPct}%)
            </span>
          )}
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
                  {['TIME (LONDON)', 'COUNTDOWN', 'CCY', 'EVENT', 'IMPACT', 'PATTERN', '✓/✗', 'ACTUAL', 'FCST', 'PREV'].map(h => (
                    <th key={h} style={{
                      padding: '6px 10px',
                      textAlign: h === 'ACTUAL' || h === 'FCST' || h === 'PREV' ? 'right' : 'center',
                      fontSize: '9px',
                      color: h === 'PATTERN' ? 'rgba(255,119,68,0.6)' : h === '✓/✗' ? 'rgba(255,255,255,0.2)' : '#4a5068',
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
                  const eventKey    = makeEventKey(ev)
                  const outcome     = outcomes.get(eventKey)
                  const predicted   = hasPattern
                    ? (pat!.pre_15m_opposite_pct! >= 60 ? 'FADES' : pat!.pre_15m_opposite_pct! <= 40 ? 'TRENDS' : 'MIX')
                    : null
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
                        {/* OUTCOME toggle — only for released events with a pattern */}
                        <td style={{ padding: '8px 10px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                          <OutcomeToggle
                            value={outcome}
                            disabled={!cd.isPast || !hasPattern}
                            onToggle={() => handleOutcomeToggle(ev, etype, predicted)}
                          />
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
                          <td colSpan={10} style={{
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
        ◈ = GOLD-RELEVANT · PATTERN = PRE-15m FADE RATE · ✓/✗ = MARK OUTCOME AFTER RELEASE · CLICK ROW FOR DETAILS
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
