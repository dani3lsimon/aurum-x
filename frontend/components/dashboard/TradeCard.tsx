'use client'
import { TradeCard as TradeCardData } from '@/lib/types'

interface Props {
  tradeCard: TradeCardData | null
}

function Row({ label, value, mono, color }: { label: string; value: unknown; mono?: boolean; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ color: '#8a92ab' }}>{label}</span>
      <span style={{ fontFamily: mono ? 'JetBrains Mono, monospace' : undefined, color: color ?? '#fff' }}>
        {value != null && value !== '' ? String(value) : '—'}
      </span>
    </div>
  )
}

export default function TradeCard({ tradeCard }: Props) {
  if (!tradeCard) {
    return (
      <div className="aurum-card" style={{ textAlign: 'center', padding: '20px', color: '#4a5068', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <div style={{ fontSize: '13px', letterSpacing: '0.15em', fontWeight: 700 }}>
          ◆ AWAITING NEXT HIGH-CONVICTION SETUP
        </div>
        <div style={{ fontSize: '11px', marginTop: '6px' }}>
          No actionable trade — macro / fusion / pre-condition filter active
        </div>
      </div>
    )
  }

  const isLong   = tradeCard.direction === 'LONG'
  const dirColor = isLong ? '#22c55e' : '#ef4444'
  const bg       = isLong ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)'

  return (
    <div className="aurum-card" style={{ padding: '14px 16px', background: bg, border: `1px solid ${dirColor}33`, height: '100%', boxSizing: 'border-box' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <div style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.18em', color: '#fff' }}>◆ NEXT TRADE</div>
        <span style={{ fontSize: '10px', color: dirColor, fontFamily: 'JetBrains Mono, monospace' }}>LIVE</span>
      </div>

      {/* Direction + conviction */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '24px', fontWeight: 800, color: dirColor, lineHeight: 1 }}>
          {isLong ? '▲' : '▼'} {tradeCard.direction}
        </span>
        <span style={{ background: '#1e2433', padding: '2px 8px', borderRadius: '4px', fontSize: '10px', color: '#fff', letterSpacing: '0.1em' }}>
          {tradeCard.conviction}
        </span>
        <span style={{ fontSize: '11px', color: '#8a92ab' }}>{tradeCard.timeframe}</span>
        {!tradeCard.direction_agreement && (
          <span title="Multi-TF engine disagrees — levels from fusion only"
                style={{ fontSize: '12px', color: '#f59e0b' }}>⚠</span>
        )}
      </div>

      {/* Prob + Edge */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', marginBottom: '8px', fontSize: '11px' }}>
        <div>PROB <strong style={{ color: '#fff' }}>{tradeCard.probability}%</strong></div>
        <div>EDGE <strong style={{ color: '#fff' }}>{tradeCard.edge}</strong></div>
      </div>

      {/* Levels */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', fontSize: '11px', marginBottom: '8px' }}>
        <Row label="ENTRY" value={tradeCard.entry_zone} mono />
        <Row label="STOP"  value={tradeCard.stop_loss}  mono color="#ef4444" />
        <Row label="TP1"   value={tradeCard.target_1}   mono color="#22c55e" />
        {tradeCard.target_2 != null && <Row label="TP2" value={tradeCard.target_2} mono color="#22c55e" />}
      </div>

      {/* Risk + Macro */}
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
        <span style={{ color: '#8a92ab' }}>RISK</span>
        <strong style={{ color: '#fff' }}>{tradeCard.risk_pct}%</strong>
      </div>
      <div style={{ fontSize: '10px', color: '#f59e0b', fontStyle: 'italic', marginBottom: '6px' }}>
        ⚠ {tradeCard.macro_note} (MBS {tradeCard.mbs})
      </div>

      {/* Collapsible rationale */}
      {tradeCard.reasoning && (
        <details style={{ fontSize: '10px', color: '#8a92ab' }}>
          <summary style={{ cursor: 'pointer', letterSpacing: '0.1em' }}>FUSION RATIONALE</summary>
          <p style={{ marginTop: '4px', lineHeight: 1.5 }}>{tradeCard.reasoning}</p>
          {tradeCard.timeframe_alignment && (
            <p style={{ marginTop: '4px', fontStyle: 'italic' }}>{tradeCard.timeframe_alignment}</p>
          )}
        </details>
      )}
    </div>
  )
}
