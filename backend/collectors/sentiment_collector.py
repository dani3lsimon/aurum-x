# backend/collectors/sentiment_collector.py
# Risk-on/off sentiment collector.
# Sources: Yahoo Finance chart API (free, no key) + FMP gold price for the ratio.
# Tracks: VIX, S&P 500 (SPY), copper futures, 10Y yield, gold/copper ratio.
import asyncio
import httpx
from services.redis_service import cache_get, cache_set
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

YF_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


class SentimentCollector:

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _fetch_yf(self, symbol: str, interval: str = "1d", range_: str = "5d") -> dict:
        url = f"{YF_BASE}/{symbol}"
        params = {"interval": interval, "range": range_}
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def _get_latest_price(self, symbol: str) -> dict:
        try:
            data = await self._fetch_yf(symbol, interval="1d", range_="5d")
            result = data.get("chart", {}).get("result", [{}])[0]
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            timestamps = result.get("timestamp", [])

            if not closes or not timestamps:
                return {"symbol": symbol, "price": None, "error": "no data"}

            valid = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
            if not valid:
                return {"symbol": symbol, "price": None, "error": "no valid closes"}

            latest_ts, latest_close = valid[-1]
            prev_close = valid[-2][1] if len(valid) > 1 else latest_close

            return {
                "symbol":      symbol,
                "price":       round(latest_close, 4),
                "prev_close":  round(prev_close, 4),
                "change":      round(latest_close - prev_close, 4),
                "change_pct":  round(((latest_close - prev_close) / prev_close) * 100, 4) if prev_close else 0.0,
                "timestamp":   datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"Yahoo Finance {symbol} error: {e}")
            return {"symbol": symbol, "price": None, "error": str(e)}

    async def get_risk_sentiment(self) -> dict:
        """
        Fetch all risk-on/off indicators. Cached 15 minutes.
        Honest no-data: any symbol Yahoo can't serve comes back with price=None
        and an "error" field — no fabricated levels.
        """
        cache_key = "sentiment_risk_indicators"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        vix, spy, copper, tnx = await asyncio.gather(
            self._get_latest_price("^VIX"),
            self._get_latest_price("SPY"),
            self._get_latest_price("HG=F"),   # Copper futures
            self._get_latest_price("^TNX"),   # 10Y yield
        )

        # Gold/copper ratio — real FMP gold price vs real copper futures price.
        gold_copper_ratio = None
        from collectors.fmp_collector import FMPCollector
        fmp = FMPCollector()
        gold = await fmp.get_gold_price()
        if gold.get("price") and copper.get("price"):
            try:
                # Copper (HG=F) quoted in USD/lb; gold in USD/oz.
                gold_copper_ratio = round(gold["price"] / copper["price"], 4)
            except Exception:
                pass

        # Interpret risk regime from real VIX level + SPY momentum.
        risk_regime = "neutral"
        risk_score = 0  # -100..+100, positive = risk-on (bearish gold)

        vix_price   = vix.get("price")
        spy_chg_pct = spy.get("change_pct") or 0

        if vix_price is not None:
            if vix_price > 30:
                risk_regime = "extreme_fear"
                risk_score  = -80
            elif vix_price > 20:
                risk_regime = "elevated_fear"
                risk_score  = -40
            elif vix_price < 12:
                risk_regime = "extreme_complacency"
                risk_score  = 60
            elif vix_price < 16:
                risk_regime = "risk_on"
                risk_score  = 30
            else:
                risk_regime = "neutral"
                risk_score  = 0

        if spy_chg_pct > 1.0:
            risk_score += 20
        elif spy_chg_pct < -1.0:
            risk_score -= 20

        result = {
            "source":            "yahoo_finance",
            "vix":               vix,
            "spy":               spy,
            "copper":            copper,
            "tnx_10y":           tnx,
            "gold_copper_ratio": gold_copper_ratio,
            "risk_regime":       risk_regime,
            "risk_score":        max(-100, min(100, risk_score)),
            "interpretation": (
                "risk-off environment supportive of gold" if risk_score < -20 else
                "risk-on environment pressuring gold" if risk_score > 20 else
                "neutral risk environment"
            ),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        await cache_set(cache_key, result, ttl_seconds=900)
        logger.info(f"Sentiment: VIX={vix_price} SPY={spy_chg_pct:+.2f}% regime={risk_regime}")
        return result
