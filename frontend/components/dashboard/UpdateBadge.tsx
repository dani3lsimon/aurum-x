'use client'
import { useState, useEffect } from 'react'

interface Props {
  lastUpdated: Date | null
  intervalMs: number        // how often this panel refreshes (ms)
  label?: string            // optional source label e.g. "OANDA · FRED"
}

function ageStr(ms: number): string {
  if (ms < 5000)   return 'just now'
  if (ms < 60000)  return `${Math.floor(ms / 1000)}s ago`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s ago`
}

function countdownStr(ms: number): string {
  if (ms <= 0)     return 'updating...'
  if (ms < 60000)  return `${Math.ceil(ms / 1000)}s`
  return `${Math.floor(ms / 60000)}m ${Math.ceil((ms % 60000) / 1000)}s`
}

export default function UpdateBadge({ lastUpdated, intervalMs, label }: Props) {
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const age      = lastUpdated ? now - lastUpdated.getTime() : null
  const nextInMs = lastUpdated ? Math.max(0, intervalMs - (now - lastUpdated.getTime())) : null
  const isStale  = age != null && age > intervalMs * 1.5

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '8px',
      fontSize: '9px', letterSpacing: '0.1em', color: '#4a5068',
      fontFamily: 'JetBrains Mono, monospace',
    }}>
      {label && (
        <span style={{ color: '#2a2d3a', borderRight: '1px solid #2a2d3a', paddingRight: '8px' }}>
          {label}
        </span>
      )}
      <span style={{ color: isStale ? '#ef4444' : '#4a5068' }}>
        UPDATED {age != null ? ageStr(age) : '—'}
      </span>
      <span style={{ color: '#2a2d3a' }}>·</span>
      <span style={{ color: nextInMs != null && nextInMs < 5000 ? '#ff7744' : '#4a5068' }}>
        NEXT {nextInMs != null ? countdownStr(nextInMs) : '—'}
      </span>
    </div>
  )
}
