'use client'

interface RangeLine {
  label:        string
  low:          number | null
  high:         number | null
  pct_to_low:   number
  pct_to_high:  number
  inside:       boolean
  above_high:   boolean
  below_low:    boolean
  period:       string
}

interface LiveRanges {
  ranges:        RangeLine[]
  anchor_price:  number
  live_price:    number
  price_delta:   number
  last_updated:  string
}

interface Props {
  liveRanges:  LiveRanges | null
  livePrice:   number
  volScore?:   number
  vix?:        number
}

export function ForecastRanges({ liveRanges, livePrice, volScore, vix }: Props) {

  if (!liveRanges) {
    return (
      <div className="aurum-card" style={{ padding: '16px' }}>
        <div className="section-label">PRICE RANGE FORECAST</div>
        <div style={{ fontSize: '11px', color: '#4a5068', marginTop: '12px' }}>
          AWAITING FORECAST DATA...
        </div>
      </div>
    )
  }

  const { ranges, anchor_price, price_delta } = liveRanges
  const deltaColor   = price_delta >= 0 ? '#22c55e' : '#ef4444'
  const deltaSign    = price_delta >= 0 ? '+' : ''

  return (
    <div className="aurum-card" style={{ padding: '16px' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <div>
          <div className="section-label">PRICE RANGE FORECAST</div>
          <div style={{ fontSize: '10px', color: '#2a2d3a', letterSpacing: '0.1em', marginTop: '2px' }}>
            ANCHOR ${anchor_price.toLocaleString('en-US', { minimumFractionDigits: 2 })}
            <span style={{ color: deltaColor, marginLeft: '6px' }}>
              {deltaSign}{price_delta.toFixed(2)} LIVE SHIFT
            </span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.1em', marginBottom: '3px' }}>
            VOL SCORE
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: '48px', height: '4px', background: 'rgba(255,255,255,0.06)' }}>
              <div style={{
                width: `${volScore ?? 50}%`,
                height: '100%',
                background: (volScore ?? 50) > 70
                  ? '#ef4444'
                  : (volScore ?? 50) > 40
                  ? '#ffb347'
                  : '#22c55e',
                transition: 'width 0.5s ease',
              }} />
            </div>
            <span style={{
              fontSize: '13px',
              fontWeight: 700,
              color: (volScore ?? 50) > 70 ? '#ef4444' : (volScore ?? 50) > 40 ? '#ffb347' : '#22c55e',
            }}>
              {volScore ?? 50}
            </span>
            {vix ? (
              <span style={{ fontSize: '10px', color: '#4a5068' }}>VIX {vix.toFixed(1)}</span>
            ) : null}
          </div>
        </div>
      </div>

      {/* Range rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', marginBottom: '12px' }}>
        {ranges.map(r => {
          if (!r.low || !r.high) return null

          // Visual fill bar — shows where current price is within range
          const rangeWidth    = r.high - r.low
          const pricePosition = Math.max(0, Math.min(100,
            ((livePrice - r.low) / rangeWidth) * 100
          ))
          const isOutside = r.above_high || r.below_low

          return (
            <div key={r.label} style={{
              padding: '8px 10px',
              background: r.inside
                ? 'rgba(255,80,0,0.06)'
                : 'rgba(255,255,255,0.02)',
              border: `1px solid ${r.inside ? 'rgba(255,80,0,0.2)' : 'rgba(255,255,255,0.04)'}`,
            }}>
              {/* Main row */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>

                {/* Label */}
                <div style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  color: r.inside ? '#ff7744' : '#6b7494',
                  letterSpacing: '0.12em',
                  minWidth: '28px',
                }}>
                  {r.label}
                </div>

                {/* Low side */}
                <div style={{ textAlign: 'right', minWidth: '80px' }}>
                  <span style={{
                    fontSize: '13px',
                    fontWeight: 700,
                    color: r.below_low ? '#ef4444' : '#6b7494',
                  }}>
                    ${r.low.toLocaleString('en-US', { minimumFractionDigits: 0 })}
                  </span>
                  <span style={{
                    fontSize: '10px',
                    color: r.pct_to_low < 0 ? '#ef4444' : '#22c55e',
                    marginLeft: '4px',
                  }}>
                    {r.pct_to_low > 0 ? '+' : ''}{r.pct_to_low.toFixed(1)}%
                  </span>
                </div>

                {/* Status badge */}
                <div style={{
                  fontSize: '9px',
                  padding: '2px 6px',
                  border: '1px solid',
                  letterSpacing: '0.1em',
                  ...(r.inside
                    ? { color: '#ff7744', borderColor: 'rgba(255,80,0,0.3)', background: 'rgba(255,80,0,0.08)' }
                    : r.above_high
                    ? { color: '#22c55e', borderColor: 'rgba(34,197,94,0.3)', background: 'rgba(34,197,94,0.06)' }
                    : { color: '#ef4444', borderColor: 'rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.06)' }
                  ),
                }}>
                  {r.inside ? 'IN RANGE' : r.above_high ? 'ABOVE' : 'BELOW'}
                </div>

                {/* High side */}
                <div style={{ textAlign: 'left', minWidth: '80px' }}>
                  <span style={{
                    fontSize: '10px',
                    color: r.pct_to_high > 0 ? '#22c55e' : '#ef4444',
                    marginRight: '4px',
                  }}>
                    {r.pct_to_high > 0 ? '+' : ''}{r.pct_to_high.toFixed(1)}%
                  </span>
                  <span style={{
                    fontSize: '13px',
                    fontWeight: 700,
                    color: r.above_high ? '#22c55e' : '#6b7494',
                  }}>
                    ${r.high.toLocaleString('en-US', { minimumFractionDigits: 0 })}
                  </span>
                </div>
              </div>

              {/* Position bar — shows where price sits within the range */}
              <div style={{ position: 'relative', height: '3px', background: 'rgba(255,255,255,0.05)' }}>
                {/* Filled portion up to current price */}
                <div style={{
                  position: 'absolute',
                  left: 0,
                  width: `${pricePosition}%`,
                  height: '100%',
                  background: 'rgba(255,80,0,0.3)',
                  transition: 'width 0.3s ease',
                }} />
                {/* Current price marker */}
                {!isOutside && (
                  <div style={{
                    position: 'absolute',
                    left: `${pricePosition}%`,
                    top: '-2px',
                    transform: 'translateX(-50%)',
                    width: '3px',
                    height: '7px',
                    background: '#ff5500',
                    boxShadow: '0 0 4px rgba(255,80,0,0.8)',
                  }} />
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer: current price + live indicator */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid rgba(255,80,0,0.08)' }}>
        <div>
          <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.12em', marginBottom: '2px' }}>
            CURRENT
          </div>
          <div style={{ fontSize: '18px', fontWeight: 800, color: '#ff5500', letterSpacing: '-0.01em' }}>
            ${livePrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '10px', color: '#22c55e', letterSpacing: '0.12em', marginBottom: '2px' }}>
            ● TICK UPDATE
          </div>
          <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.08em' }}>
            EVERY CTRADER TICK
          </div>
        </div>
      </div>
    </div>
  )
}

export default ForecastRanges
