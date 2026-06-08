'use client'
import { useState, useEffect, useCallback, useRef } from 'react'
import { Forecast, AgentScore, Scenario, Alert, EconomicRelease, ShortScore, WSMessage, OHLCVBar, MultiTfSignal, OrderFlowData } from '@/lib/types'
import { useWebSocket } from './useWebSocket'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
const WS_URL  = process.env.NEXT_PUBLIC_WS_URL     || 'ws://localhost:8000/forecast/ws'

export function useForecast() {
  const [forecast,     setForecast]     = useState<Forecast | null>(null)
  const [agentScores,  setAgentScores]  = useState<AgentScore[]>([])
  const [scenarios,    setScenarios]    = useState<Scenario[]>([])
  const [alerts,       setAlerts]       = useState<Alert[]>([])
  const [releases,     setReleases]     = useState<EconomicRelease[]>([])
  const [shortScore,   setShortScore]   = useState<ShortScore | null>(null)
  const [ohlcvData,    setOhlcvData]    = useState<OHLCVBar[]>([])
  const [multiTf,      setMultiTf]      = useState<MultiTfSignal | null>(null)
  const [orderFlow,    setOrderFlow]    = useState<OrderFlowData | null>(null)
  const [chartTf,      setChartTf]      = useState<'15m' | '1h' | '4h' | '1d'>('1h')
  const [loading,      setLoading]      = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const { isConnected, lastMessage }    = useWebSocket(WS_URL)

  // ── Live gold price — direct cTrader broker tick stream (no agent) ────────
  // Connects straight to the AURUM-X VPS tick bridge (70.156.8.139), which
  // holds the live cTrader Open API session and re-broadcasts XAUUSD ticks.
  // Falls back to 5s polling of /market/orderflow (OANDA-backed) if the
  // bridge WebSocket is unreachable.
  const [liveGoldPrice, setLiveGoldPrice] = useState<number>(0)
  const [priceChange,   setPriceChange]   = useState<number>(0)
  const [wsStatus,      setWsStatus]      = useState<'connected' | 'disconnected' | 'error'>('disconnected')
  const prevPriceRef = useRef<number>(0)

  const applyTick = useCallback((price: number) => {
    if (!(price > 0)) return
    setPriceChange(price - (prevPriceRef.current || price))
    prevPriceRef.current = price
    setLiveGoldPrice(price)
  }, [])

  useEffect(() => {
    const bridgeWs    = process.env.NEXT_PUBLIC_CTRADER_WS
    const bridgeToken = process.env.NEXT_PUBLIC_CTRADER_TOKEN

    // No bridge configured — fall back to polling the backend directly.
    if (!bridgeWs) {
      setWsStatus('disconnected')
      const poll = async () => {
        try {
          const r = await fetch(`${BACKEND}/market/orderflow`)
          const d = await r.json()
          applyTick(d.current_price || d.bid || 0)
        } catch {}
      }
      poll()
      const interval = setInterval(poll, 5000)
      return () => clearInterval(interval)
    }

    let ws: WebSocket | undefined
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let fallbackInterval: ReturnType<typeof setInterval> | undefined
    let cancelled = false

    const startFallbackPolling = () => {
      if (fallbackInterval) return
      const poll = async () => {
        try {
          const r = await fetch(`${BACKEND}/market/orderflow`)
          const d = await r.json()
          applyTick(d.current_price || d.bid || 0)
        } catch {}
      }
      poll()
      fallbackInterval = setInterval(poll, 5000)
    }

    const stopFallbackPolling = () => {
      if (fallbackInterval) { clearInterval(fallbackInterval); fallbackInterval = undefined }
    }

    const connect = () => {
      if (cancelled) return
      try {
        const url = bridgeToken ? `${bridgeWs}?token=${bridgeToken}` : bridgeWs
        ws = new WebSocket(url)

        ws.onopen = () => {
          setWsStatus('connected')
          stopFallbackPolling()
        }

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data)
            if (msg.type === 'tick' && msg.data?.mid) {
              applyTick(msg.data.mid)
            }
          } catch {}
        }

        ws.onclose = () => {
          if (cancelled) return
          setWsStatus('disconnected')
          startFallbackPolling()
          reconnectTimer = setTimeout(connect, 5000)
        }

        ws.onerror = () => {
          setWsStatus('error')
          ws?.close()
        }
      } catch {
        startFallbackPolling()
        reconnectTimer = setTimeout(connect, 5000)
      }
    }

    connect()

    return () => {
      cancelled = true
      ws?.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
      stopFallbackPolling()
    }
  }, [applyTick])

  // Fetch OHLCV candles on mount and whenever the chart timeframe changes
  useEffect(() => {
    const tfMap:    Record<string, string> = { '15m': 'M15', '1h': 'H1', '4h': 'H4', '1d': 'D' }
    const countMap: Record<string, number> = { '15m': 96,   '1h': 48,   '4h': 24,   '1d': 14  }
    fetch(`${BACKEND}/market/candles?granularity=${tfMap[chartTf]}&count=${countMap[chartTf]}`)
      .then(r => r.ok ? r.json() : [])
      .then(d => { if (Array.isArray(d)) setOhlcvData(d) })
      .catch(() => {})
  }, [chartTf])

  // Fetch live OANDA order-flow (VWAP/delta/POC/VAH/VAL) on mount + every 60s
  useEffect(() => {
    const fetchOrderFlow = () => {
      fetch(`${BACKEND}/market/orderflow`)
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d && Object.keys(d).length > 0) setOrderFlow(d) })
        .catch(() => {})
    }
    fetchOrderFlow()
    const interval = setInterval(fetchOrderFlow, 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  // Fetch the multi-timeframe signal on mount
  useEffect(() => {
    fetch(`${BACKEND}/forecast/multi-tf`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && Object.keys(d).length > 0) setMultiTf(d) })
      .catch(() => {})
  }, [])

  // Auto-refresh the multi-TF signal every 5 minutes (matches scheduler cadence)
  useEffect(() => {
    const fetchMultiTf = async () => {
      try {
        const r = await fetch(`${BACKEND}/forecast/multi-tf`)
        if (r.ok) {
          const d = await r.json()
          if (d && Object.keys(d).length > 0) setMultiTf(d)
        }
      } catch { /* keep previous value */ }
    }
    const interval = setInterval(fetchMultiTf, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  // Initial fetch
  useEffect(() => {
    async function fetchInitial() {
      try {
        const [fRes, aRes, sRes, alRes, relRes, ssRes] = await Promise.all([
          fetch(`${BACKEND}/forecast/latest`),
          fetch(`${BACKEND}/agents/scores`),
          fetch(`${BACKEND}/scenarios/latest`),
          fetch(`${BACKEND}/alerts/recent`),
          fetch(`${BACKEND}/calendar/upcoming?days=7`),
          fetch(`${BACKEND}/forecast/short-score`),
        ])
        if (fRes.ok) {
          const f = await fRes.json()
          if (f && Object.keys(f).length > 0) setForecast(f)
        }
        if (aRes.ok)   setAgentScores(await aRes.json())
        if (sRes.ok)   setScenarios(await sRes.json())
        if (alRes.ok)  setAlerts(await alRes.json())
        if (relRes.ok) setReleases(await relRes.json())
        if (ssRes.ok) {
          const ss = await ssRes.json()
          if (ss && Object.keys(ss).length > 0) setShortScore(ss)
        }
      } catch (e) {
        console.error('[AURUM-X] Initial fetch error:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchInitial()
  }, [])

  // WebSocket message handler
  useEffect(() => {
    if (!lastMessage) return
    const msg = lastMessage as WSMessage

    switch (msg.type) {
      case 'forecast_update':
      case 'initial_state':
        if (msg.data && typeof msg.data === 'object') {
          setForecast(msg.data as Forecast)
          setIsRefreshing(false)   // cycle complete — reset button
        }
        break

      case 'agent_update': {
        const d = msg.data as AgentScore
        setAgentScores(prev => {
          const idx = prev.findIndex(a => a.agent_name === d.agent_name)
          if (idx >= 0) { const n = [...prev]; n[idx] = d; return n }
          return [d, ...prev]
        })
        break
      }

      case 'alert':
        setAlerts(prev => [msg.data as Alert, ...prev.slice(0, 19)])
        break

      case 'release_alert':
        setReleases(prev => [msg.data as EconomicRelease, ...prev.slice(0, 19)])
        break

      case 'short_score_update':
        if (msg.data && typeof msg.data === 'object') {
          setShortScore(msg.data as ShortScore)
        }
        break

      case 'multi_tf_update':
        if (msg.data && typeof msg.data === 'object') {
          setMultiTf(msg.data as MultiTfSignal)
        }
        break
    }
  }, [lastMessage])

  // Auto-refresh short-score every 5 minutes (matches the backend scheduler cadence)
  useEffect(() => {
    const fetchShortScore = async () => {
      try {
        const r = await fetch(`${BACKEND}/forecast/short-score`)
        if (r.ok) {
          const ss = await r.json()
          if (ss && Object.keys(ss).length > 0) setShortScore(ss)
        }
      } catch { /* keep previous value */ }
    }
    const interval = setInterval(fetchShortScore, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  // Manual refresh trigger — polls for result so button never stays stuck
  const triggerManualCycle = useCallback(async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    const triggerTime = Date.now()

    try {
      const res = await fetch(`${BACKEND}/forecast/trigger`, { method: 'POST' })
      if (!res.ok) { setIsRefreshing(false); return }
    } catch {
      setIsRefreshing(false)
      return
    }

    // Brief refresh fires 90 seconds later, once the agent cycle has completed
    setTimeout(() => {
      fetch(`${BACKEND}/forecast/brief/refresh`, { method: 'POST' }).catch(() => {})
    }, 90000)

    // Poll every 3s until a forecast newer than trigger time arrives (max 120s)
    let attempts = 0
    const poll = setInterval(async () => {
      attempts++
      if (attempts > 40) {
        clearInterval(poll)
        setIsRefreshing(false)
        return
      }
      try {
        const r = await fetch(`${BACKEND}/forecast/latest`)
        if (!r.ok) return
        const f = await r.json()
        const fTime = f?.timestamp ? new Date(f.timestamp).getTime() : 0
        if (fTime > triggerTime) {
          clearInterval(poll)
          setForecast(f)
          const [aRes, alRes, sRes] = await Promise.all([
            fetch(`${BACKEND}/agents/scores`),
            fetch(`${BACKEND}/alerts/recent`),
            fetch(`${BACKEND}/scenarios/latest`),
          ])
          if (aRes.ok)  setAgentScores(await aRes.json())
          if (alRes.ok) setAlerts(await alRes.json())
          if (sRes.ok)  setScenarios(await sRes.json())
          setIsRefreshing(false)
        }
      } catch { /* keep polling */ }
    }, 3000)
  }, [isRefreshing])

  return {
    forecast, agentScores, scenarios, alerts, releases, shortScore,
    ohlcvData, setOhlcvData, multiTf, orderFlow, chartTf, setChartTf,
    loading, isConnected, isRefreshing, triggerManualCycle,
    liveGoldPrice, priceChange, wsStatus,
  }
}
