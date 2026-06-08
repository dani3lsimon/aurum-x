'use client'
import { useState, useEffect, useRef } from 'react'
import { useForecast } from '@/hooks/useForecast'
import ProbabilityGauge  from '@/components/dashboard/ProbabilityGauge'
import AgentScorePanel   from '@/components/dashboard/AgentScorePanel'
import RegimeClassifier  from '@/components/dashboard/RegimeClassifier'
import ForecastRanges    from '@/components/dashboard/ForecastRanges'
import ScenarioTree      from '@/components/dashboard/ScenarioTree'
import TailRiskPanel     from '@/components/dashboard/TailRiskPanel'
import AlertsFeed        from '@/components/dashboard/AlertsFeed'
import ForecastChart     from '@/components/dashboard/ForecastChart'
import COTPanel          from '@/components/dashboard/COTPanel'
import ShortScoreWidget  from '@/components/dashboard/ShortScoreWidget'
import MultiTfPanel      from '@/components/dashboard/MultiTfPanel'
import { IntelligenceBrief } from '@/components/dashboard/IntelligenceBrief'

export default function Page() {
  const {
    forecast, agentScores, scenarios, alerts, shortScore, loading,
    ohlcvData, multiTf, orderFlow, chartTf, setChartTf,
    isConnected, isRefreshing, triggerManualCycle,
  } = useForecast()

  const [toast, setToast]               = useState<string | null>(null)
  const prevRefreshing                  = useRef(false)

  // Show toast when refresh completes (isRefreshing flips true → false)
  useEffect(() => {
    if (prevRefreshing.current && !isRefreshing) {
      setToast('INTEL UPDATED')
      const t = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(t)
    }
    prevRefreshing.current = isRefreshing
  }, [isRefreshing])

  const price  = forecast?.gold_price ?? 0
  const regime = forecast?.macro_regime ?? 'INITIALISING'
  const bull   = forecast?.bullish_prob ?? 0
  const bear   = forecast?.bearish_prob ?? 0

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: '#06070b' }}>
        <div className="flex flex-col items-center gap-4">
          <div className="text-2xl font-bold text-[#ff4400]"
            style={{ textShadow: '0 0 20px rgba(255,68,0,0.8)', fontFamily: "'JetBrains Mono', monospace" }}>
            AURUM-X
          </div>
          <div className="text-xs text-[#6b7494] animate-pulse">INITIALISING INTELLIGENCE LAYER...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#06070b', position: 'relative', zIndex: 1 }}>

      {/* ── Header Bar ─────────────────────────────────────────────────── */}
      <header className="aurum-card border-b border-[var(--border-subtle)] px-4 py-3 flex items-center justify-between shrink-0" style={{ zIndex: 10 }}>

        {/* Left: wordmark */}
        <div className="flex items-center gap-3">
          <div className="text-[#ff4400] text-lg" style={{ textShadow: 'var(--glow-text)', lineHeight: 1 }}>◆</div>
          <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: '1.1rem', color: '#fff', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
            AURUM<span style={{ color: '#ff4400' }}>-X</span>
          </div>
          <div className="version-badge">v2.0</div>
          <div className="hidden sm:block text-[var(--text-muted)]" style={{ fontSize: '0.75rem' }}>GOLD MACRO INTELLIGENCE</div>
        </div>

        {/* Centre: gold price hero */}
        <div className="flex flex-col items-center">
          <div className="text-[var(--text-label)] mb-0.5" style={{ fontSize: '0.75rem' }}>XAUUSD SPOT</div>
          <div className="hero-number text-2xl sm:text-3xl">
            {price > 0
              ? `$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : '---'}
          </div>
        </div>

        {/* Right: regime + pills + REFRESH button + live dot */}
        <div className="flex items-center gap-3">
          <div className="hidden md:flex flex-col items-end gap-0.5">
            <div className="text-[var(--text-label)]" style={{ fontSize: '0.72rem' }}>REGIME</div>
            <div className="font-bold text-[#ff4400]" style={{ fontSize: '0.75rem' }}>{regime.replace(/_/g, ' ')}</div>
          </div>
          <div className="hidden md:flex gap-1.5">
            <span className="status-pill bull">B {bull.toFixed(0)}%</span>
            <span className="status-pill bear">S {bear.toFixed(0)}%</span>
          </div>

          {/* REFRESH INTEL button */}
          <button
            onClick={triggerManualCycle}
            disabled={isRefreshing}
            style={{
              background:    isRefreshing ? 'rgba(255,80,0,0.05)' : 'rgba(255,80,0,0.12)',
              border:        '1px solid rgba(255,80,0,0.4)',
              borderRadius:  '2px',
              color:         isRefreshing ? 'rgba(255,80,0,0.4)' : '#ff6633',
              fontFamily:    "'JetBrains Mono', monospace",
              fontSize:      '0.6rem',
              letterSpacing: '0.15em',
              padding:       '6px 14px',
              cursor:        isRefreshing ? 'not-allowed' : 'pointer',
              textTransform: 'uppercase',
              display:       'flex',
              alignItems:    'center',
              gap:           '8px',
              transition:    'all 0.2s ease',
            }}
          >
            {isRefreshing ? (
              <>
                <span style={{
                  width: '6px', height: '6px', borderRadius: '50%',
                  background: '#ff4400', display: 'inline-block',
                  animation: 'glowPulse 0.8s ease-in-out infinite',
                }} />
                ANALYSING...
              </>
            ) : (
              <> &#8635; REFRESH INTEL </>
            )}
          </button>

          <div className="flex flex-col items-end gap-0.5">
            <div className={`live-badge ${isConnected ? '' : 'opacity-40'}`}>
              {isConnected ? 'LIVE' : 'OFFLINE'}
            </div>
            <div className="text-xs text-[var(--text-muted)]">10 AGENTS</div>
          </div>
        </div>
      </header>

      {/* ── Dashboard Grid — 7-row layout (v3.0 spec) ───────────────────── */}
      <main style={{
        flex: 1, display: 'grid', gap: '1px',
        background: 'rgba(255,80,0,0.06)',
        gridTemplateColumns: 'repeat(12, 1fr)',
        alignItems: 'stretch',
        margin: '8px 12px 12px',
        border: '1px solid var(--border-subtle)',
      }}>

        {/* Row 2 — Probability Gauge + Short-Setup Score */}
        <div className="aurum-card" style={{ gridColumn: 'span 8', minHeight: '380px', minWidth: 0, overflow: 'hidden' }}>
          <ProbabilityGauge forecast={forecast} isRefreshing={isRefreshing} />
        </div>
        <div className="aurum-card" style={{ gridColumn: 'span 4', minWidth: 0, overflow: 'hidden' }}>
          <ShortScoreWidget shortScore={shortScore} />
        </div>

        {/* Row 3 — Forecast Chart (real OANDA price action + bands) + (Regime stacked above Ranges) */}
        <div style={{ gridColumn: 'span 8', minHeight: '380px', minWidth: 0, overflow: 'hidden' }}>
          <ForecastChart
            forecast={forecast}
            ohlcvData={ohlcvData}
            orderFlow={orderFlow}
            chartTf={chartTf}
            onTfChange={setChartTf}
          />
        </div>
        <div style={{ gridColumn: 'span 4', display: 'grid', gridTemplateRows: 'auto auto', gap: '1px', minWidth: 0 }}>
          <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
            <RegimeClassifier forecast={forecast} />
          </div>
          <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
            <ForecastRanges forecast={forecast} />
          </div>
        </div>

        {/* Row 3b — Multi-Timeframe Confluence Panel (full width) */}
        <div style={{ gridColumn: '1 / 13', minWidth: 0, overflow: 'hidden' }}>
          <MultiTfPanel multiTf={multiTf} />
        </div>

        {/* Row 4 — Agent Score Matrix (full width, all 11 agents) */}
        <div className="aurum-card" style={{ gridColumn: '1 / 13', minWidth: 0, overflow: 'hidden' }}>
          <AgentScorePanel scores={agentScores} />
        </div>

        {/* Row 5 — Intelligence Brief (full width) */}
        <div className="aurum-card" style={{ gridColumn: '1 / 13', minWidth: 0, overflow: 'hidden' }}>
          <IntelligenceBrief />
        </div>

        {/* Row 6 — Scenarios + Tail Risk + Alerts */}
        <div className="aurum-card" style={{ gridColumn: 'span 5', minWidth: 0, overflow: 'hidden' }}>
          <ScenarioTree scenarios={scenarios} />
        </div>
        <div className="aurum-card" style={{ gridColumn: 'span 4', minWidth: 0, overflow: 'hidden' }}>
          <TailRiskPanel forecast={forecast} />
        </div>
        <div className="aurum-card" style={{ gridColumn: 'span 3', minWidth: 0, overflow: 'hidden' }}>
          <AlertsFeed alerts={alerts} />
        </div>

        {/* Row 7 — COT Panel (full width) */}
        <div className="aurum-card" style={{ gridColumn: '1 / 13', minWidth: 0, overflow: 'hidden' }}>
          <COTPanel />
        </div>
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="px-4 py-1.5 flex items-center justify-between border-t border-[var(--border-subtle)] shrink-0" style={{ zIndex: 10 }}>
        <div className="text-xs text-[var(--text-muted)]">
          AURUM-X // CLAUDE SONNET+HAIKU // FMP + Yahoo Finance + FRED
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-[#00ff88]' : 'bg-[#4a5068]'}`}
            style={isConnected ? { animation: 'glowPulse 2s ease-in-out infinite', boxShadow: '0 0 6px #00ff88' } : {}} />
          <div className="text-xs text-[var(--text-muted)]">
            {isConnected ? 'CONNECTED' : 'RECONNECTING...'}
          </div>
        </div>
      </footer>

      {/* ── Toast notification ──────────────────────────────────────────── */}
      {toast && (
        <div style={{
          position:   'fixed',
          bottom:     '24px',
          right:      '24px',
          background: 'rgba(13,15,23,0.95)',
          border:     '1px solid rgba(255,80,0,0.5)',
          borderRadius: '2px',
          padding:    '10px 20px',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize:   '0.65rem',
          letterSpacing: '0.2em',
          color:      '#ff6633',
          textTransform: 'uppercase',
          boxShadow:  '0 0 20px rgba(255,80,0,0.3)',
          zIndex:     1000,
          animation:  'cardMount 0.3s ease-out forwards',
        }}>
          ● {toast}
        </div>
      )}
    </div>
  )
}
