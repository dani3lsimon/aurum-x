'use client'
import { useState, useEffect, useCallback } from 'react'
import { Forecast, AgentScore, Scenario, Alert, EconomicRelease, ShortScore, WSMessage } from '@/lib/types'
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
  const [loading,      setLoading]      = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const { isConnected, lastMessage }    = useWebSocket(WS_URL)

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
    loading, isConnected, isRefreshing, triggerManualCycle,
  }
}
