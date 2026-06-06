'use client'
import { useState, useEffect, useCallback } from 'react'
import { Forecast, AgentScore, Scenario, Alert, EconomicRelease, WSMessage } from '@/lib/types'
import { useWebSocket } from './useWebSocket'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
const WS_URL  = process.env.NEXT_PUBLIC_WS_URL     || 'ws://localhost:8000/forecast/ws'

export function useForecast() {
  const [forecast,     setForecast]     = useState<Forecast | null>(null)
  const [agentScores,  setAgentScores]  = useState<AgentScore[]>([])
  const [scenarios,    setScenarios]    = useState<Scenario[]>([])
  const [alerts,       setAlerts]       = useState<Alert[]>([])
  const [releases,     setReleases]     = useState<EconomicRelease[]>([])
  const [loading,      setLoading]      = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const { isConnected, lastMessage }    = useWebSocket(WS_URL)

  // Initial fetch
  useEffect(() => {
    async function fetchInitial() {
      try {
        const [fRes, aRes, sRes, alRes, relRes] = await Promise.all([
          fetch(`${BACKEND}/forecast/latest`),
          fetch(`${BACKEND}/agents/scores`),
          fetch(`${BACKEND}/scenarios/latest`),
          fetch(`${BACKEND}/alerts/recent`),
          fetch(`${BACKEND}/calendar/upcoming?days=7`),
        ])
        if (fRes.ok) {
          const f = await fRes.json()
          if (f && Object.keys(f).length > 0) setForecast(f)
        }
        if (aRes.ok)   setAgentScores(await aRes.json())
        if (sRes.ok)   setScenarios(await sRes.json())
        if (alRes.ok)  setAlerts(await alRes.json())
        if (relRes.ok) setReleases(await relRes.json())
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
    }
  }, [lastMessage])

  // Manual refresh trigger
  const triggerManualCycle = useCallback(async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    try {
      const res = await fetch(`${BACKEND}/forecast/trigger`, { method: 'POST' })
      if (!res.ok) {
        console.error('[AURUM-X] Trigger failed:', res.status)
        setIsRefreshing(false)
      }
    } catch (e) {
      console.error('[AURUM-X] Trigger error:', e)
      setIsRefreshing(false)
    }
  }, [isRefreshing])

  return {
    forecast, agentScores, scenarios, alerts, releases,
    loading, isConnected, isRefreshing, triggerManualCycle,
  }
}
