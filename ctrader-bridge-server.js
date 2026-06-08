/**
 * AURUM-X cTrader Tick Bridge
 * Connects to cTrader Open API (via @reiryoku/ctrader-layer) and streams
 * live XAUUSD ticks. Serves a WebSocket (port 8080) and a REST API (port 8081).
 */
require('dotenv').config()
const { CTraderConnection } = require('@reiryoku/ctrader-layer')
const WebSocket = require('ws')
const express   = require('express')

const {
  CTRADER_HOST, CTRADER_PORT,
  CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET,
  CTRADER_ACCESS_TOKEN, CTRADER_ACCOUNT_ID,
  WS_PORT, REST_PORT, BRIDGE_AUTH_TOKEN,
} = process.env

const SYMBOL = 'XAUUSD'
const MAX_HISTORY = 500

// ── State ──────────────────────────────────────────────────
let latestTick  = null
let tickHistory = []

// ── WebSocket server ───────────────────────────────────────
const wss = new WebSocket.Server({ port: parseInt(WS_PORT || '8080') })
console.log(`[WS] WebSocket server listening on :${WS_PORT}`)

function broadcast(data) {
  const msg = JSON.stringify(data)
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) client.send(msg)
  })
}

wss.on('connection', (ws, req) => {
  const url   = new URL(req.url, 'http://localhost')
  const token = url.searchParams.get('token')
  if (token !== BRIDGE_AUTH_TOKEN) {
    ws.close(4001, 'Unauthorized')
    console.log(`[WS] Rejected unauthorized connection from ${req.socket.remoteAddress}`)
    return
  }

  console.log(`[WS] Client connected: ${req.socket.remoteAddress}`)
  if (latestTick) ws.send(JSON.stringify({ type: 'tick', data: latestTick }))

  ws.on('close', () => console.log(`[WS] Client disconnected: ${req.socket.remoteAddress}`))
})

// ── REST API server ────────────────────────────────────────
const app = express()
app.use((req, res, next) => {
  const auth  = req.headers['authorization'] || ''
  const token = auth.replace('Bearer ', '').trim()
  if (token !== BRIDGE_AUTH_TOKEN) return res.status(401).json({ error: 'Unauthorized' })
  next()
})

app.get('/price', (req, res) => {
  if (!latestTick) return res.status(503).json({ error: 'No data yet', status: 'connecting' })
  res.json(latestTick)
})

app.get('/health', (req, res) => {
  res.json({
    status:      'ok',
    symbol:      SYMBOL,
    latestTick,
    ticksStored: tickHistory.length,
    clients:     wss.clients.size,
    uptime:      Math.floor(process.uptime()),
  })
})

app.get('/history', (req, res) => {
  const limit = Math.min(parseInt(req.query.limit) || 100, MAX_HISTORY)
  res.json(tickHistory.slice(-limit))
})

app.listen(parseInt(REST_PORT || '8081'), () => {
  console.log(`[REST] API server listening on :${REST_PORT}`)
})

// ── cTrader Open API connection ────────────────────────────
let connection = null

async function startCTrader() {
  console.log(`[CTRADER] Connecting to ${CTRADER_HOST}:${CTRADER_PORT}`)

  try {
    connection = new CTraderConnection({
      host: CTRADER_HOST,
      port: parseInt(CTRADER_PORT || '5035'),
    })

    await connection.open()
    console.log('[CTRADER] Socket open. Authenticating application...')

    await connection.sendCommand('ProtoOAApplicationAuthReq', {
      clientId:     CTRADER_CLIENT_ID,
      clientSecret: CTRADER_CLIENT_SECRET,
    })
    console.log('[CTRADER] App authenticated. Authenticating account...')

    await connection.sendCommand('ProtoOAAccountAuthReq', {
      ctidTraderAccountId: parseInt(CTRADER_ACCOUNT_ID),
      accessToken:         CTRADER_ACCESS_TOKEN,
    })
    console.log('[CTRADER] Account authenticated. Looking up XAUUSD symbol...')

    const symbolsResponse = await connection.sendCommand('ProtoOASymbolsListReq', {
      ctidTraderAccountId: parseInt(CTRADER_ACCOUNT_ID),
    })

    const symbols = symbolsResponse.symbol || []
    const xauSymbol = symbols.find((s) =>
      s.symbolName === 'XAUUSD' ||
      s.symbolName === 'XAU/USD' ||
      (s.symbolName && s.symbolName.includes('XAU'))
    )

    if (!xauSymbol) {
      console.error('[CTRADER] XAUUSD symbol not found. Available symbols:')
      symbols.slice(0, 20).forEach((s) => console.log(`  ${s.symbolId}: ${s.symbolName}`))
      throw new Error('XAUUSD symbol not found in account')
    }

    const symbolId = parseInt(xauSymbol.symbolId)
    console.log(`[CTRADER] Found ${xauSymbol.symbolName} — symbol ID: ${symbolId}`)

    await connection.sendCommand('ProtoOASubscribeSpotsReq', {
      ctidTraderAccountId: parseInt(CTRADER_ACCOUNT_ID),
      symbolId:            [symbolId],
    })
    console.log(`[CTRADER] Subscribed to ${xauSymbol.symbolName} ticks. Waiting for data...`)

    // Heartbeat every 25s to keep the connection alive
    const heartbeat = setInterval(() => {
      try { connection.sendHeartbeat() } catch {}
    }, 25000)

    connection.on('ProtoOASpotEvent', (event) => {
      const d = event.descriptor || event
      if (parseInt(d.symbolId) !== symbolId) return

      const rawBid = d.bid != null ? Number(d.bid) : null
      const rawAsk = d.ask != null ? Number(d.ask) : null
      const bid = rawBid ? rawBid / 100000 : null
      const ask = rawAsk ? rawAsk / 100000 : null
      const mid = (bid && ask) ? Math.round(((bid + ask) / 2) * 100) / 100 : null

      const tick = {
        symbol:    SYMBOL,
        bid:       bid ? Math.round(bid * 100) / 100 : null,
        ask:       ask ? Math.round(ask * 100) / 100 : null,
        mid,
        spread:    (bid && ask) ? Math.round((ask - bid) * 100) / 100 : null,
        timestamp: new Date().toISOString(),
        unix_ms:   Date.now(),
        source:    'ctrader_live',
      }

      latestTick = tick
      tickHistory.push(tick)
      if (tickHistory.length > MAX_HISTORY) tickHistory.shift()

      broadcast({ type: 'tick', data: tick })

      if (tickHistory.length % 100 === 0) {
        console.log(`[TICK] ${SYMBOL}: bid=${tick.bid} ask=${tick.ask} mid=${tick.mid} | total=${tickHistory.length}`)
      }
    })

    connection.on('close', () => {
      clearInterval(heartbeat)
      console.log('[CTRADER] Connection closed. Reconnecting in 5s...')
      setTimeout(startCTrader, 5000)
    })

    connection.on('error', (err) => {
      console.error('[CTRADER] Error:', err && err.message ? err.message : err)
    })

  } catch (err) {
    console.error('[CTRADER] Connection failed:', err && err.message ? err.message : err)
    console.log('[CTRADER] Retrying in 10 seconds...')
    setTimeout(startCTrader, 10000)
  }
}

startCTrader()

process.on('SIGTERM', () => {
  console.log('[SERVER] SIGTERM received. Shutting down...')
  wss.close()
  process.exit(0)
})

console.log('[SERVER] AURUM-X cTrader Tick Bridge starting...')
console.log(`[SERVER] Symbol: ${SYMBOL}`)
console.log(`[SERVER] WebSocket: ws://70.156.8.139:${WS_PORT}`)
console.log(`[SERVER] REST API:  http://70.156.8.139:${REST_PORT}`)
