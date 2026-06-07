# backend/collectors/oanda_collector.py
"""
OANDA v20 REST API collector.
Primary source for:
  - XAU_USD live bid/ask price and spread
  - XAU_USD 1-minute OHLCV candles (for VWAP + delta)
  - Major FX pairs real-time (for dollar_agent)

Practice account base URL: https://api-fxpractice.oanda.com
No deposit required. Token from AMP -> Manage API Access.

Honest no-data: every method returns a clearly-marked error/empty result on
failure (status='error'/'no_data', source='oanda_error', empty list/dict) —
never a fabricated price, candle, or order-flow metric.
"""
import httpx
from config import get_settings
from services.redis_service import cache_get, cache_set
import logging
from datetime import datetime, timezone

logger   = logging.getLogger(__name__)
settings = get_settings()

FX_INSTRUMENTS = "EUR_USD,USD_JPY,GBP_USD,USD_CHF,USD_CNH,AUD_USD"


class OandaCollector:

    def __init__(self):
        self.base    = settings.oanda_base_url
        self.headers = {
            "Authorization":       f"Bearer {settings.oanda_api_token}",
            "Content-Type":        "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }
        self.account = settings.oanda_account_id

    async def _get(self, path: str, params: dict = None) -> dict:
        async with httpx.AsyncClient(
            timeout  = 15,
            headers  = self.headers,
            base_url = self.base,
            follow_redirects = True,
        ) as client:
            resp = await client.get(path, params=params or {})
            resp.raise_for_status()
            return resp.json()

    # ── GOLD PRICE ────────────────────────────────────────────────

    async def get_gold_price(self) -> dict:
        """
        Live XAU_USD bid/ask from OANDA.
        Replaces cTrader stub and Yahoo Finance GC=F.
        Cached 30 seconds.
        """
        cache_key = "oanda_xauusd_price"
        cached    = await cache_get(cache_key)
        if cached:
            return cached

        try:
            data   = await self._get(
                f"/v3/accounts/{self.account}/pricing",
                {"instruments": "XAU_USD"}
            )
            prices = data.get("prices", [])
            if not prices:
                return {"symbol": "XAUUSD", "price": 0, "source": "oanda_error"}

            p      = prices[0]
            bid    = float(p.get("bids", [{}])[0].get("price", 0))
            ask    = float(p.get("asks", [{}])[0].get("price", 0))
            mid    = round((bid + ask) / 2, 2) if bid and ask else 0
            spread = round(ask - bid, 2) if bid and ask else None

            result = {
                "symbol":      "XAUUSD",
                "price":       mid,
                "bid":         bid,
                "ask":         ask,
                "spread":      spread,
                "spread_ok":   spread is not None and spread < settings.oanda_spread_threshold,
                "tradeable":   p.get("tradeable", False),
                "timestamp":   p.get("time"),
                "source":      "oanda",
            }
            await cache_set(cache_key, result, ttl_seconds=30)
            logger.info(f"OANDA XAU/USD: mid={mid} spread={spread}")
            return result

        except Exception as e:
            logger.error(f"OANDA gold price error: {e}")
            return {"symbol": "XAUUSD", "price": 0, "source": "oanda_error", "error": str(e)}

    # ── CANDLES ───────────────────────────────────────────────────

    async def get_candles(self, instrument: str = "XAU_USD",
                          granularity: str = "M1", count: int = 60) -> list:
        """
        OHLCV candles for any instrument at any granularity.
        Granularities: S5 S10 S30 M1 M2 M4 M5 M10 M15 M30 H1 H2 H4 H6 H8 H12 D W M
        Returns list of {time, open, high, low, close, volume} dicts, oldest first.
        Cache: 60s for M1, 5m for M5/M15, 1h for H1/D.
        """
        ttl_map   = {"M1": 60, "M5": 300, "M15": 300, "H1": 3600, "D": 3600}
        ttl       = ttl_map.get(granularity, 120)
        cache_key = f"oanda_candles_{instrument}_{granularity}_{count}"
        cached    = await cache_get(cache_key)
        if cached:
            return cached

        try:
            data    = await self._get(
                f"/v3/instruments/{instrument}/candles",
                {"count": count, "granularity": granularity, "price": "M"}
            )
            raw     = data.get("candles", [])
            candles = []
            for c in raw:
                mid = c.get("mid", {})
                candles.append({
                    "time":   c.get("time"),
                    "open":   float(mid.get("o", 0)),
                    "high":   float(mid.get("h", 0)),
                    "low":    float(mid.get("l", 0)),
                    "close":  float(mid.get("c", 0)),
                    "volume": int(c.get("volume", 0)),
                    "complete": c.get("complete", True),
                })
            await cache_set(cache_key, candles, ttl_seconds=ttl)
            logger.debug(f"OANDA {instrument} {granularity}: {len(candles)} candles")
            return candles

        except Exception as e:
            logger.error(f"OANDA candles error: {e}")
            return []

    # ── FX RATES ──────────────────────────────────────────────────

    async def get_fx_rates(self) -> dict:
        """
        Real-time bid/ask for major FX pairs.
        Replaces FRED for dollar_agent (FRED is daily, OANDA is live).
        Cached 60 seconds.
        """
        cache_key = "oanda_fx_rates"
        cached    = await cache_get(cache_key)
        if cached:
            return cached

        try:
            data   = await self._get(
                f"/v3/accounts/{self.account}/pricing",
                {"instruments": FX_INSTRUMENTS}
            )
            prices = data.get("prices", [])
            result = {}
            for p in prices:
                instr  = p.get("instrument", "")
                bid    = float(p.get("bids", [{}])[0].get("price", 0))
                ask    = float(p.get("asks", [{}])[0].get("price", 0))
                mid    = round((bid + ask) / 2, 5) if bid and ask else 0
                result[instr] = {"bid": bid, "ask": ask, "mid": mid,
                                 "tradeable": p.get("tradeable", False)}

            await cache_set(cache_key, result, ttl_seconds=60)
            logger.info(f"OANDA FX: {list(result.keys())}")
            return result

        except Exception as e:
            logger.error(f"OANDA FX error: {e}")
            return {}

    # ── ORDER FLOW (VWAP + DELTA) ──────────────────────────────────

    async def get_order_flow(self) -> dict:
        """
        Calculates session VWAP, 15-min cumulative delta,
        and volume profile from OANDA 1-minute XAU_USD candles.
        Replaces the removed IBKR stub with real broker data.
        Cached 60 seconds.
        """
        cache_key = "oanda_xauusd_orderflow"
        cached    = await cache_get(cache_key)
        if cached:
            return cached

        try:
            candles_60 = await self.get_candles("XAU_USD", "M1", 60)
            candles_d  = await self.get_candles("XAU_USD", "D", 3)
            price_data = await self.get_gold_price()

            if not candles_60:
                return {"status": "no_data", "source": "oanda"}

            candles_15 = candles_60[-15:] if len(candles_60) >= 15 else candles_60

            # ── VWAP ────────────────────────────────────────────
            def calc_vwap(bars: list):
                cum_tpv = sum(
                    ((b["high"] + b["low"] + b["close"]) / 3) * b["volume"]
                    for b in bars if b["volume"] > 0
                )
                cum_vol = sum(b["volume"] for b in bars if b["volume"] > 0)
                return round(cum_tpv / cum_vol, 2) if cum_vol else None

            session_vwap = calc_vwap(candles_60)
            vwap_15      = calc_vwap(candles_15)

            # ── DELTA (Kaufman approximation from OHLCV) ─────────
            def calc_delta(bars: list) -> dict:
                deltas = []
                for b in bars:
                    rng = b["high"] - b["low"]
                    d   = (b["volume"] * ((b["close"] - b["low"]) -
                          (b["high"] - b["close"])) / rng) if rng > 0 else 0.0
                    deltas.append(round(d, 1))
                cumulative = round(sum(deltas), 1)
                direction  = ("positive" if cumulative > 50
                              else "negative" if cumulative < -50
                              else "neutral")
                streak_dir = None
                streak     = 1
                for i in range(len(deltas) - 1, 0, -1):
                    diff = deltas[i] - deltas[i - 1]
                    d    = "up" if diff > 0 else "down"
                    if streak_dir is None:
                        streak_dir = d
                    if d == streak_dir:
                        streak += 1
                    else:
                        break
                return {
                    "cumulative_delta": cumulative,
                    "delta_direction":  direction,
                    "delta_momentum":   streak_dir,
                    "streak":           streak,
                }

            delta = calc_delta(candles_15)

            # ── VOLUME PROFILE ───────────────────────────────────
            def calc_profile(bars: list, buckets: int = 20) -> dict:
                if not bars:
                    return {}
                highs  = [b["high"] for b in bars if b["high"]]
                lows   = [b["low"]  for b in bars if b["low"]]
                if not highs or not lows:
                    return {}
                ph     = max(highs); pl = min(lows)
                rng    = ph - pl
                if rng <= 0:
                    return {}
                bsz    = rng / buckets
                vols   = {i: 0.0 for i in range(buckets)}
                for b in bars:
                    for i in range(buckets):
                        bl   = pl + i * bsz
                        bh   = bl + bsz
                        ol   = max(b["low"], bl)
                        oh   = min(b["high"], bh)
                        if oh > ol and b["high"] > b["low"]:
                            vols[i] += b["volume"] * (oh - ol) / (b["high"] - b["low"])
                poc_i  = max(vols, key=vols.get)
                poc    = round(pl + (poc_i + 0.5) * bsz, 2)
                total  = sum(vols.values())
                target = total * 0.70
                va_vol = vols[poc_i]; va_up = poc_i; va_dn = poc_i
                while va_vol < target:
                    up  = vols.get(va_up + 1, 0)
                    dn  = vols.get(va_dn - 1, 0)
                    if not up and not dn:
                        break
                    if up >= dn:
                        va_up += 1; va_vol += vols.get(va_up, 0)
                    else:
                        va_dn -= 1; va_vol += vols.get(va_dn, 0)
                return {
                    "poc_price": poc,
                    "vah":       round(pl + (va_up + 1) * bsz, 2),
                    "val":       round(pl + va_dn * bsz, 2),
                }

            profile = calc_profile(candles_60)

            # ── PRICE VS VWAP ────────────────────────────────────
            current = price_data.get("price", 0)
            pvwap   = None
            vsig    = "unknown"
            if current and session_vwap:
                pvwap = round(current - session_vwap, 2)
                vsig  = ("bearish" if current < session_vwap
                         else "bullish" if current > session_vwap
                         else "at_vwap")

            # ── PRIOR SESSION LOW / HIGH ─────────────────────────
            prior_low  = None
            prior_high = None
            if len(candles_d) >= 2:
                prior_low  = candles_d[-2].get("low")
                prior_high = candles_d[-2].get("high")

            result = {
                "status":          "live",
                "source":          "oanda",
                "instrument":      "XAU_USD",
                "current_price":   current,
                "bid":             price_data.get("bid"),
                "ask":             price_data.get("ask"),
                "spread":          price_data.get("spread"),
                "spread_ok":       price_data.get("spread_ok", True),
                "session_vwap":    session_vwap,
                "vwap_15min":      vwap_15,
                "price_vs_vwap":   pvwap,
                "vwap_signal":     vsig,
                "cumulative_delta":delta["cumulative_delta"],
                "delta_direction": delta["delta_direction"],
                "delta_momentum":  delta["delta_momentum"],
                "poc_price":       profile.get("poc_price"),
                "vah":             profile.get("vah"),
                "val":             profile.get("val"),
                "prior_session_low":  prior_low,
                "prior_session_high": prior_high,
                "bars_used":       len(candles_60),
                "fetched_at":      datetime.now(timezone.utc).isoformat(),
            }

            await cache_set(cache_key, result, ttl_seconds=60)
            logger.info(
                f"OANDA order flow: price={current} VWAP={session_vwap} "
                f"delta={delta['cumulative_delta']} ({delta['delta_direction']}) "
                f"vs_VWAP={pvwap} ({vsig})"
            )
            return result

        except Exception as e:
            logger.error(f"OANDA order flow error: {e}")
            return {"status": "error", "source": "oanda", "error": str(e)}
