'use client'
import { useState, useEffect, useRef } from 'react'
import { useForecast } from '@/hooks/useForecast'
import ProbabilityGauge  from '@/components/dashboard/ProbabilityGauge'
import AgentScorePanel   from '@/components/dashboard/AgentScorePanel'
import RegimeClassifier  from '@/components/dashboard/RegimeClassifier'
import ForecastRanges    from '@/components/dashboard/ForecastRanges'
import ScenarioTree      from '@/components/dashboard/ScenarioTree'
import AlertsFeed        from '@/components/dashboard/AlertsFeed'
import ForecastChart     from '@/components/dashboard/ForecastChart'
import COTPanel          from '@/components/dashboard/COTPanel'
import ShortScoreWidget  from '@/components/dashboard/ShortScoreWidget'
import MultiTfPanel      from '@/components/dashboard/MultiTfPanel'
import { IntelligenceBrief } from '@/components/dashboard/IntelligenceBrief'

type TabId = 'live' | 'agents' | 'analysis'

export default function Page() {
  const {
    forecast, agentScores, scenarios, alerts, shortScore, loading,
    ohlcvData, multiTf, orderFlow, chartTf, setChartTf,
    isConnected, isRefreshing, triggerManualCycle,
  } = useForecast()

  const [toast, setToast]               = useState<string | null>(null)
  const prevRefreshing                  = useRef(false)

  const [activeTab, setActiveTab] = useState<TabId>('live')
  // Restore persisted tab from localStorage after mount (avoids SSR/CSR mismatch)
  useEffect(() => {
    const saved = window.localStorage.getItem('aurum_tab') as TabId | null
    if (saved === 'live' || saved === 'agents' || saved === 'analysis') {
      setActiveTab(saved)
    }
  }, [])
  const handleTab = (t: TabId) => {
    setActiveTab(t)
    window.localStorage.setItem('aurum_tab', t)
  }

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
  const conf   = forecast?.confidence_score ?? 0

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

  const TABS: { id: TabId; label: string }[] = [
    { id: 'live',     label: '① LIVE DASHBOARD' },
    { id: 'agents',   label: '② AGENT MATRIX' },
    { id: 'analysis', label: '③ ANALYSIS' },
  ]

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
          <div className="hero-number" style={{ fontSize: '44px', fontWeight: 800 }}>
            {price > 0
              ? `$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : '---'}
          </div>
          {/* Quick-stats strip — always visible regardless of active tab */}
          <div style={{ fontSize: '13px', color: '#6b7494', display: 'flex', gap: '16px', alignItems: 'center', marginTop: '4px' }}>
            <span>BULL <strong style={{ color: '#22c55e' }}>{bull.toFixed(0)}%</strong></span>
            <span>BEAR <strong style={{ color: '#ef4444' }}>{bear.toFixed(0)}%</strong></span>
            <span>CONF <strong style={{ color: '#ffb347' }}>{conf.toFixed(0)}%</strong></span>
            <span style={{ color: '#2a2d3a' }}>|</span>
            <span style={{ color: '#ff7744', fontWeight: 700 }}>{shortScore?.net_signal ?? '—'}</span>
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

      {/* ── Tab Navigation ───────────────────────────────────────────────── */}
      <nav style={{
        display: 'flex',
        borderBottom: '1px solid rgba(255,80,0,0.12)',
        background: '#06070b',
        padding: '0 20px',
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => handleTab(tab.id)}
            style={{
              padding: '14px 24px',
              fontSize: '13px',
              letterSpacing: '0.16em',
              color: activeTab === tab.id ? '#ff5500' : '#4a5068',
              borderBottom: activeTab === tab.id ? '2px solid #ff5500' : '2px solid transparent',
              background: 'transparent',
              border: 'none',
              borderBottomWidth: '2px',
              borderBottomStyle: 'solid',
              borderBottomColor: activeTab === tab.id ? '#ff5500' : 'transparent',
              cursor: 'pointer',
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
              transition: 'color 0.15s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* ── Tab 1: LIVE DASHBOARD ────────────────────────────────────────── */}
      {activeTab === 'live' && (
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>

          {/* Row 1: 3 huge probability numbers */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
            <ProbabilityGauge forecast={forecast} isRefreshing={isRefreshing} variant="trio" />
          </div>

          {/* Row 2: Signal engine (left) + right column stack */}
          <div style={{ display: 'grid', gridTemplateColumns: '5fr 4fr', gap: '8px', alignItems: 'start' }}>
            <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
              <ShortScoreWidget shortScore={shortScore} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minWidth: 0 }}>
              <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
                <RegimeClassifier forecast={forecast} />
              </div>

              {/* OANDA live strip — 6 metrics */}
              <div className="aurum-card p-4" style={{ minWidth: 0, overflow: 'hidden' }}>
                <div className="section-label" style={{ marginBottom: '10px' }}>OANDA Live — XAU/USD</div>
                <div className="grid" style={{ gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', fontSize: '0.7rem', letterSpacing: '0.04em' }}>
                  <div><span style={{ color: 'var(--text-muted)' }}>PRICE </span><strong>{orderFlow?.current_price ? `$${orderFlow.current_price.toFixed(2)}` : '—'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>VWAP </span><strong>{orderFlow?.session_vwap ? `$${orderFlow.session_vwap.toFixed(2)}` : '—'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>DELTA </span><strong>{orderFlow?.cumulative_delta ?? '—'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>POC </span><strong>{orderFlow?.poc_price ? `$${orderFlow.poc_price.toFixed(2)}` : '—'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>VAH </span><strong>{orderFlow?.vah ? `$${orderFlow.vah.toFixed(2)}` : '—'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>VAL </span><strong>{orderFlow?.val ? `$${orderFlow.val.toFixed(2)}` : '—'}</strong></div>
                </div>
              </div>

              {/* Alert feed — last 3 alerts */}
              <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
                <AlertsFeed alerts={alerts.slice(0, 3)} />
              </div>
            </div>
          </div>

          {/* Forecast chart + Multi-TF — real OANDA price action */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '8px' }}>
            <div style={{ minHeight: '380px', minWidth: 0, overflow: 'hidden' }}>
              <ForecastChart
                forecast={forecast}
                ohlcvData={ohlcvData}
                orderFlow={orderFlow}
                chartTf={chartTf}
                onTfChange={setChartTf}
              />
            </div>
            <div style={{ minWidth: 0, overflow: 'hidden' }}>
              <MultiTfPanel multiTf={multiTf} />
            </div>
          </div>
        </div>
      )}

      {/* ── Tab 2: AGENT MATRIX ──────────────────────────────────────────── */}
      {activeTab === 'agents' && (
        <div style={{ padding: '20px', flex: 1 }}>
          <AgentScorePanel scores={agentScores} layout="full" />
        </div>
      )}

      {/* ── Tab 3: ANALYSIS ──────────────────────────────────────────────── */}
      {activeTab === 'analysis' && (
        <div style={{ padding: '20px', display: 'grid', gridTemplateColumns: '5fr 4fr', gap: '8px', flex: 1, alignItems: 'start' }}>
          <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
            <IntelligenceBrief />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minWidth: 0 }}>
            <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
              <ScenarioTree scenarios={scenarios} />
            </div>
            <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
              <COTPanel />
            </div>
            <div className="aurum-card" style={{ minWidth: 0, overflow: 'hidden' }}>
              <ForecastRanges forecast={forecast} />
            </div>
          </div>
        </div>
      )}

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
