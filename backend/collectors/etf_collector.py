# backend/collectors/etf_collector.py
# Gold ETF flows collector.
# Tracks GLD and IAU price/volume action via Yahoo Finance as a free proxy for
# institutional gold demand (real shares-outstanding/AUM feeds are paywalled).
# Cached 4 hours — daily-cadence data.
import asyncio
import httpx
from services.redis_service import cache_get, cache_set
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ETFCollector:

    async def get_etf_flows(self) -> dict:
        cache_key = "gold_etf_flows"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        async def fetch_etf(symbol: str, name: str) -> dict:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                params = {"interval": "1d", "range": "5d"}
                headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                result_data = data.get("chart", {}).get("result", [{}])[0]
                meta         = result_data.get("meta", {})
                quotes       = result_data.get("indicators", {}).get("quote", [{}])[0]
                closes       = quotes.get("close", [])
                volumes      = quotes.get("volume", [])
                timestamps   = result_data.get("timestamp", [])

                valid_closes = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
                valid_vols   = [(t, v) for t, v in zip(timestamps, volumes) if v is not None]

                if not valid_closes:
                    return {"symbol": symbol, "name": name, "error": "no data"}

                latest_price = valid_closes[-1][1]
                prev_price   = valid_closes[-2][1] if len(valid_closes) > 1 else latest_price
                latest_vol   = valid_vols[-1][1] if valid_vols else 0
                shares_outstanding = meta.get("sharesOutstanding", 0)

                aum_usd = latest_price * shares_outstanding if shares_outstanding else None
                price_change_pct = (
                    ((latest_price - prev_price) / prev_price) * 100
                    if prev_price else 0
                )

                return {
                    "symbol":             symbol,
                    "name":               name,
                    "price":              round(latest_price, 2),
                    "prev_price":         round(prev_price, 2),
                    "price_change_pct":   round(price_change_pct, 4),
                    "volume":             latest_vol,
                    "shares_outstanding": shares_outstanding,
                    "aum_usd":            aum_usd,
                    "flow_signal": (
                        "inflow"  if price_change_pct > 0.2 else
                        "outflow" if price_change_pct < -0.2 else
                        "neutral"
                    ),
                }
            except Exception as e:
                logger.warning(f"ETF {symbol} error: {e}")
                return {"symbol": symbol, "name": name, "error": str(e)}

        gld, iau = await asyncio.gather(
            fetch_etf("GLD", "SPDR Gold Shares"),
            fetch_etf("IAU", "iShares Gold Trust"),
        )

        combined_signal = "neutral"
        gld_sig = gld.get("flow_signal", "neutral")
        iau_sig = iau.get("flow_signal", "neutral")

        if gld_sig == "inflow" and iau_sig == "inflow":
            combined_signal = "strong_inflow"
        elif gld_sig == "outflow" and iau_sig == "outflow":
            combined_signal = "strong_outflow"
        elif "inflow" in (gld_sig, iau_sig):
            combined_signal = "mild_inflow"
        elif "outflow" in (gld_sig, iau_sig):
            combined_signal = "mild_outflow"

        result = {
            "source":          "yahoo_finance",
            "gld":             gld,
            "iau":             iau,
            "combined_signal": combined_signal,
            "gold_bullish":    combined_signal in ("strong_inflow", "mild_inflow"),
            "fetched_at":      datetime.now(timezone.utc).isoformat(),
        }

        await cache_set(cache_key, result, ttl_seconds=14400)
        logger.info(f"ETF flows: GLD={gld.get('flow_signal')} IAU={iau.get('flow_signal')} Combined={combined_signal}")
        return result
