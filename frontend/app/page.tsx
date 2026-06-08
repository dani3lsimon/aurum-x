'use client'
import { useState, useEffect, useRef } from 'react'
import { useForecast } from '@/hooks/useForecast'
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

type TabId = 'live' | 'chart' | 'analysis'

function ProbBox({ value, label, color, sub }: { value?: number; label: string; color: string; sub: string }) {
  return (
    <div className="aurum-card" style={{ textAlign: 'center', padding: '20px 16px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <div style={{ fontSize: '11px', color: '#4a5068', letterSpacing: '0.2em', marginBottom: '8px' }}>{label} PROBABILITY</div>
      <div style={{
        fontSize: 'clamp(3.5rem, 6vw, 5.5rem)',
        fontWeight: 800,
        color,
        letterSpacing: '-0.03em',
        lineHeight: 1,
        textShadow: `0 0 24px ${color}44`,
      }}>
        {value?.toFixed(1) ?? '—'}%
      </div>
      <div style={{ fontSize: '12px', color: '#4a5068', letterSpacing: '0.12em', marginTop: '8px' }}>{sub}</div>
    </div>
  )
}

export default function Page() {
  const {
    forecast, agentScores, scenarios, alerts, shortScore, loading,
    ohlcvData, setOhlcvData, multiTf, orderFlow, chartTf, setChartTf,
    isConnected, isRefreshing, triggerManualCycle,
    liveGoldPrice, priceChange, wsStatus,
  } = useForecast()

  const [toast, setToast]               = useState<string | null>(null)
  const prevRefreshing                  = useRef(false)

  const [activeTab, setActiveTab] = useState<TabId>('live')
  // Restore persisted tab from localStorage after mount (avoids SSR/CSR mismatch)
  useEffect(() => {
    const saved = window.localStorage.getItem('aurum_tab') as TabId | null
    if (saved === 'live' || saved === 'chart' || saved === 'analysis') {
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
    { id: 'live',     label: '① LIVE' },
    { id: 'chart',    label: '② CHART & AGENTS' },
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

        {/* Centre: gold price hero — live, polled every 5s direct from OANDA */}
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '10px', color: '#4a5068', letterSpacing: '0.18em', marginBottom: '2px' }}>
            XAUUSD SPOT
          </div>
          <div style={{
            fontSize: '40px',
            fontWeight: 800,
            color: '#ff5500',
            letterSpacing: '-0.02em',
            lineHeight: 1,
            textShadow: '0 0 20px rgba(255,80,0,0.35)',
            transition: 'color 0.3s ease',
          }}>
            ${(liveGoldPrice || forecast?.gold_price || 0).toLocaleString('en-US', {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </div>
          {priceChange !== 0 && (
            <div style={{
              fontSize: '12px',
              color: priceChange > 0 ? '#22c55e' : '#ef4444',
              letterSpacing: '0.08em',
              marginTop: '2px',
            }}>
              {priceChange > 0 ? '▲' : '▼'} {Math.abs(priceChange).toFixed(2)}
            </div>
          )}
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
            <span style={{ fontSize: '10px', color: wsStatus === 'connected' ? '#22c55e' : '#ef4444', letterSpacing: '0.12em' }}>
              {wsStatus === 'connected' ? '● CTRADER LIVE' : '○ CTRADER OFFLINE'}
            </span>
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

      {/* ── Tab 1: LIVE — fixed-height grid, fits one screen, no scrolling ── */}
      {activeTab === 'live' && (
        <div style={{
          padding: '12px 16px',
          height: 'calc(100vh - 110px)',
          display: 'grid',
          gridTemplateRows: 'auto 1fr',
          gridTemplateColumns: '1fr',
          gap: '8px',
          overflow: 'hidden',
        }}>

          {/* Row 1: Probabilities */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
            <ProbBox value={forecast?.bullish_prob} label="BULLISH" color="#22c55e" sub={`${(forecast?.forecast_momentum ?? 0) >= 0 ? '+' : ''}${(forecast?.forecast_momentum ?? 0).toFixed(1)} MOM`} />
            <ProbBox value={forecast?.bearish_prob} label="BEARISH" color="#ef4444" sub={`CONF ${(forecast?.confidence_score ?? 0).toFixed(0)}%`} />
            <ProbBox value={forecast?.neutral_prob} label="NEUTRAL" color="#6b7494" sub={`VOL ${(forecast?.volatility_score ?? 0).toFixed(0)}/100`} />
          </div>

          {/* Row 2: Signal + Right column — fills remaining space */}
          <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: '8px', minHeight: 0 }}>
            <div style={{ overflow: 'hidden', minHeight: 0 }}>
              <ShortScoreWidget shortScore={shortScore} compact={true} />
            </div>
            <div style={{ display: 'grid', gridTemplateRows: '1fr 1fr', gap: '8px', minHeight: 0 }}>
              <RegimeClassifier forecast={forecast} regimeData={shortScore?.regime_info} />
              <AlertsFeed alerts={alerts.slice(0, 3)} compact={true} />
            </div>
          </div>
        </div>
      )}

      {/* ── Tab 2: CHART & AGENTS ────────────────────────────────────────── */}
      {activeTab === 'chart' && (
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
          <div style={{ minHeight: '380px', minWidth: 0, overflow: 'hidden' }}>
            <ForecastChart
              forecast={forecast}
              ohlcvData={ohlcvData}
              setOhlcvData={setOhlcvData}
              orderFlow={orderFlow}
              chartTf={chartTf}
              onTfChange={setChartTf}
            />
          </div>
          <div style={{ minWidth: 0, overflow: 'hidden' }}>
            <MultiTfPanel multiTf={multiTf} />
          </div>
          <div style={{ minWidth: 0, overflow: 'hidden' }}>
            <AgentScorePanel scores={agentScores} layout="full" />
          </div>
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
