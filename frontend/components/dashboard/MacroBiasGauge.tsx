'use client'

interface Props {
  mbs: number | null
}

export default function MacroBiasGauge({ mbs }: Props) {
  const value  = mbs ?? 0
  const pct    = ((value + 100) / 200) * 100   // -100..+100 → 0..100%
  const label  = value > 20 ? 'BULLISH' : value < -20 ? 'BEARISH' : 'NEUTRAL'
  const color  = value > 20 ? '#22c55e' : value < -20 ? '#ef4444' : '#6b7494'

  return (
    <div className="aurum-card" style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%', boxSizing: 'border-box' }}>
      <div style={{ fontSize: '10px', letterSpacing: '0.18em', color: '#4a5068', marginBottom: '8px' }}>◆ MACRO BIAS</div>

      {/* Numeric */}
      <div style={{ fontSize: '28px', fontWeight: 800, color, lineHeight: 1, marginBottom: '6px', textShadow: `0 0 12px ${color}44` }}>
        {value > 0 ? '+' : ''}{value}
      </div>
      <div style={{ fontSize: '11px', letterSpacing: '0.15em', color, marginBottom: '10px' }}>{label}</div>

      {/* Bar */}
      <div style={{ position: 'relative', height: '6px', borderRadius: '3px', background: '#1a1d2e', overflow: 'hidden' }}>
        {/* Centre marker */}
        <div style={{ position: 'absolute', left: '50%', top: 0, width: '1px', height: '100%', background: '#2a3142', zIndex: 1 }} />
        {/* Fill from centre */}
        {value >= 0 ? (
          <div style={{
            position: 'absolute',
            left: '50%',
            width: `${pct - 50}%`,
            height: '100%',
            background: color,
            borderRadius: '0 3px 3px 0',
          }} />
        ) : (
          <div style={{
            position: 'absolute',
            right: `${100 - pct}%`,
            width: `${50 - pct}%`,
            height: '100%',
            background: color,
            borderRadius: '3px 0 0 3px',
          }} />
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: '#4a5068', marginTop: '4px' }}>
        <span>-100</span>
        <span>0</span>
        <span>+100</span>
      </div>
    </div>
  )
}
