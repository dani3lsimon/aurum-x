'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { WSMessage } from '@/lib/types'

export function useWebSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        console.log('[AURUM-X] WebSocket connected to', url)
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as WSMessage
          setLastMessage(msg)
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        setIsConnected(false)
        console.log('[AURUM-X] WebSocket disconnected — reconnecting in 3s')
        reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    } catch {
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [url])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { isConnected, lastMessage }
}
