'use client'
import { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'

interface Brief {
  headline:         string
  situation:        string
  supporting_gold:  string[]
  pressuring_gold:  string[]
  key_tension:      string
  bottom_line:      string
  watch_for:        string
  confidence_note:  string
  generated_at:     string
  gold_price:       number
  bullish_prob:     number
  bearish_prob:     number
  confidence:       number
  regime:           string
}

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

export function IntelligenceBrief() {
  const [brief,     setBrief]     = useState<Brief | null>(null)
  const [loading,   setLoading]   = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error,     setError]     = useState<string | null>(null)

  const fetchBrief = async (forceRefresh = false) => {
    try {
      const url      = forceRefresh ? `${BACKEND}/forecast/brief/refresh` : `${BACKEND}/forecast/brief`
      const method   = forceRefresh ? 'POST' : 'GET'
      const response = await fetch(url, { method })
      const data     = await response.json()
      if (data.error) setError(data.error)
      else { setBrief(data); setError(null) }
    } catch (e) {
      setError('Failed to load intelligence brief')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchBrief()
    // Auto-refresh every 30 minutes
    const interval = setInterval(() => fetchBrief(), 1800000)
    return () => clearInterval(interval)
  }, [])

  const handleRefresh = () => {
    setRefreshing(true)
    fetchBrief(true)
  }

  const isBull    = (brief?.bullish_prob ?? 0) > (brief?.bearish_prob ?? 0)
  const timeAgo   = brief?.generated_at
    ? formatDistanceToNow(new Date(brief.generated_at), { addSuffix: true })
    : ''

  return (
    <div className="aurum-card" style={{ padding: '24px', height: '100%' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <div className="section-label">● INTELLIGENCE BRIEF</div>
          <div style={{ fontSize: '0.5rem', color: '#4a5068', letterSpacing: '0.12em', marginTop: '3px' }}>
            PLAIN ENGLISH MARKET ANALYSIS · POWERED BY CLAUDE
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {timeAgo && (
            <span style={{ fontSize: '0.5rem', color: '#4a5068', letterSpacing: '0.1em' }}>
              {timeAgo}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            style={{
              background:    'rgba(255,80,0,0.08)',
              border:        '1px solid rgba(255,80,0,0.3)',
              color:         refreshing ? 'rgba(255,80,0,0.3)' : '#ff6633',
              fontFamily:    'JetBrains Mono, monospace',
              fontSize:      '0.55rem',
              letterSpacing: '0.12em',
              padding:       '4px 10px',
              cursor:        refreshing ? 'not-allowed' : 'pointer',
              textTransform: 'uppercase',
            }}
          >
            {refreshing ? '● THINKING...' : '⟳ REFRESH'}
          </button>
        </div>
      </div>

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {[100, 80, 60, 90, 70].map((w, i) => (
            <div key={i} style={{
              height: '12px',
              width: `${w}%`,
              background: 'rgba(255,80,0,0.06)',
              borderRadius: '1px',
              animation: 'glowPulse 1.5s ease-in-out infinite',
              animationDelay: `${i * 0.1}s`,
            }} />
          ))}
          <div style={{ fontSize: '0.55rem', color: '#4a5068', letterSpacing: '0.12em', marginTop: '8px' }}>
            CLAUDE IS ANALYSING {brief ? '10' : ''} AGENT SIGNALS...
          </div>
        </div>
      )}

      {error && !loading && (
        <div style={{
          padding:    '12px',
          border:     '1px solid rgba(239,68,68,0.3)',
          background: 'rgba(239,68,68,0.05)',
          fontSize:   '0.6rem',
          color:      '#ef4444',
          letterSpacing: '0.1em',
        }}>
          ⚠ {error}
        </div>
      )}

      {brief && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Headline */}
          <div style={{
            padding:    '16px 20px',
            background: isBull ? 'rgba(34,197,94,0.05)' : 'rgba(239,68,68,0.05)',
            border:     `1px solid ${isBull ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
          }}>
            <div style={{
              fontSize:      'clamp(0.85rem, 1.5vw, 1.1rem)',
              fontWeight:    700,
              color:         isBull ? '#22c55e' : '#ef4444',
              lineHeight:    1.4,
              letterSpacing: '0.03em',
            }}>
              {brief.headline}
            </div>
            <div style={{
              display:    'flex',
              gap:        '16px',
              marginTop:  '10px',
              paddingTop: '10px',
              borderTop:  `1px solid ${isBull ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'}`,
            }}>
              {[
                { label: 'BULL',       value: `${brief.bullish_prob?.toFixed(0)}%`,  color: '#22c55e' },
                { label: 'BEAR',       value: `${brief.bearish_prob?.toFixed(0)}%`,  color: '#ef4444' },
                { label: 'CONFIDENCE', value: `${brief.confidence?.toFixed(0)}%`,    color: '#ffb347' },
                { label: 'REGIME',     value: (brief.regime || '').replace(/_/g, ' '), color: '#ff6633' },
              ].map(m => (
                <div key={m.label}>
                  <div style={{ fontSize: '0.45rem', color: '#4a5068', letterSpacing: '0.15em' }}>{m.label}</div>
                  <div style={{ fontSize: '0.65rem', fontWeight: 700, color: m.color, marginTop: '2px' }}>{m.value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Situation */}
          <div>
            <div style={{ fontSize: '0.5rem', color: '#4a5068', letterSpacing: '0.18em', marginBottom: '8px' }}>
              SITUATION
            </div>
            <p style={{
              fontSize:      '0.7rem',
              color:         '#c0c8d8',
              lineHeight:    1.7,
              letterSpacing: '0.02em',
              margin:        0,
            }}>
              {brief.situation}
            </p>
          </div>

          {/* Supporting + Pressuring columns */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1px' }}>

            {/* Supporting gold */}
            <div style={{ padding: '14px', background: 'rgba(34,197,94,0.04)', border: '1px solid rgba(34,197,94,0.12)' }}>
              <div style={{ fontSize: '0.5rem', color: '#22c55e', letterSpacing: '0.15em', marginBottom: '10px', fontWeight: 700 }}>
                ▲ SUPPORTING GOLD
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {brief.supporting_gold?.map((factor, i) => (
                  <div key={i} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                    <span style={{ color: '#22c55e', flexShrink: 0, fontSize: '0.55rem', marginTop: '1px' }}>●</span>
                    <span style={{ fontSize: '0.62rem', color: '#a0b0a8', lineHeight: 1.5, letterSpacing: '0.02em' }}>
                      {factor}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Pressuring gold */}
            <div style={{ padding: '14px', background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.12)' }}>
              <div style={{ fontSize: '0.5rem', color: '#ef4444', letterSpacing: '0.15em', marginBottom: '10px', fontWeight: 700 }}>
                ▼ PRESSURING GOLD
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {brief.pressuring_gold?.map((factor, i) => (
                  <div key={i} style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                    <span style={{ color: '#ef4444', flexShrink: 0, fontSize: '0.55rem', marginTop: '1px' }}>●</span>
                    <span style={{ fontSize: '0.62rem', color: '#b0a0a0', lineHeight: 1.5, letterSpacing: '0.02em' }}>
                      {factor}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Key Tension — the most important section */}
          <div style={{
            padding:    '16px',
            background: 'rgba(255,179,71,0.04)',
            border:     '1px solid rgba(255,179,71,0.2)',
          }}>
            <div style={{ fontSize: '0.5rem', color: '#ffb347', letterSpacing: '0.18em', marginBottom: '8px', fontWeight: 700 }}>
              ⚡ KEY TENSION
            </div>
            <p style={{
              fontSize:      '0.68rem',
              color:         '#c8b88a',
              lineHeight:    1.7,
              letterSpacing: '0.02em',
              margin:        0,
            }}>
              {brief.key_tension}
            </p>
          </div>

          {/* Bottom line */}
          <div style={{
            padding:    '16px',
            background: 'rgba(255,80,0,0.05)',
            border:     '1px solid rgba(255,80,0,0.2)',
          }}>
            <div style={{ fontSize: '0.5rem', color: '#ff6633', letterSpacing: '0.18em', marginBottom: '8px', fontWeight: 700 }}>
              ◆ BOTTOM LINE
            </div>
            <p style={{
              fontSize:      '0.72rem',
              fontWeight:    600,
              color:         '#e0c8b8',
              lineHeight:    1.6,
              letterSpacing: '0.02em',
              margin:        0,
            }}>
              {brief.bottom_line}
            </p>
          </div>

          {/* Watch for + Confidence note */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1px' }}>
            <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,80,0,0.08)' }}>
              <div style={{ fontSize: '0.48rem', color: '#4a5068', letterSpacing: '0.15em', marginBottom: '6px' }}>
                👁 WATCH FOR
              </div>
              <p style={{ fontSize: '0.6rem', color: '#8892a4', lineHeight: 1.5, margin: 0, letterSpacing: '0.02em' }}>
                {brief.watch_for}
              </p>
            </div>
            <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,80,0,0.08)' }}>
              <div style={{ fontSize: '0.48rem', color: '#4a5068', letterSpacing: '0.15em', marginBottom: '6px' }}>
                📊 CONFIDENCE NOTE
              </div>
              <p style={{ fontSize: '0.6rem', color: '#8892a4', lineHeight: 1.5, margin: 0, letterSpacing: '0.02em' }}>
                {brief.confidence_note}
              </p>
            </div>
          </div>

        </div>
      )}
    </div>
  )
}
