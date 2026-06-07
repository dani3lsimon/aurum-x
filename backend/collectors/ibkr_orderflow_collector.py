# backend/collectors/ibkr_orderflow_collector.py
"""
IBKR (Interactive Brokers) order-flow collector for GC (gold futures front month) —
session VWAP, cumulative delta, and volume profile for the Short-Setup Score Engine.

NOTE on IBKR connectivity (read before "fixing" this to call MCP tools):
A real IBKR account exists (IBEAM_ACCOUNT/IBEAM_PASSWORD in ibkr.env) and an
"IBKR MCP connector" (mcp__de04a17f-...__search_contracts / get_price_history /
get_price_snapshot) is wired into the Claude Code *agent session* that authored
this file. That connector is a tool surface available only inside the interactive
agent session — it is NOT a Python library, and is NOT reachable from this
*standalone Railway backend process* at runtime. Importing/calling it here would
crash or hang on every invocation. This is the exact same situation already
documented and solved honestly in collectors/ctrader_collector.py for the
cTrader Open API.

config.py's ibkr_host/ibkr_port (127.0.0.1:7497) point at a local TWS/Gateway
socket — also unreachable from Railway's cloud servers. No IBeam Client Portal
Gateway is deployed alongside this backend, and no HTTP client for IBKR's real
Client Portal Web API exists yet (tracked separately as a broker-integration task).

Per the no-fake-data rule: rather than fabricate "live" order-flow numbers that
aren't actually being computed from a real feed, this collector is HONEST —
status="disconnected" with a clear rationale — until a reachable IBKR gateway
is built and deployed. The calculation methods below (_calculate_vwap,
_calculate_delta, _calculate_volume_profile) are real, correct, pure functions
ready to run the instant real 1-minute bars start flowing in; only the data
*fetchers* (_get_1min_bars / _get_snapshot / _resolve_contract_id) are stubbed
to honestly return nothing until that connection exists.
"""
import logging
from datetime import datetime, timezone
from services.redis_service import cache_get, cache_set

logger = logging.getLogger(__name__)

CACHE_KEY          = "ibkr_gc_order_flow"
CONTRACT_CACHE_KEY = "ibkr_gc_contract_id"


class IBKROrderFlowCollector:
    """
    Order-flow analytics for GC (COMEX 100oz gold futures, front month):
      - Session VWAP   (volume-weighted average price)
      - Cumulative delta (Kaufman OHLCV approximation of buy/sell pressure)
      - Volume profile (POC / VAH / VAL)

    get_order_flow() is cached 60 seconds. Returns status='live' with real
    numbers once a reachable IBKR feed exists; status='disconnected' with an
    honest rationale until then — the short-score engine handles both cases.
    """

    def __init__(self):
        self._contract_id = None

    # ── Contract resolution ────────────────────────────────────────────────

    async def _resolve_contract_id(self):
        """
        Resolve the GC front-month contract_id on NYMEX. Cached 6 hours.
        Requires a live IBKR connection — see module docstring for why that
        connection does not exist from this server-side process yet.
        Returns None (honest no-data) until one does.
        """
        cached = await cache_get(CONTRACT_CACHE_KEY)
        if cached:
            self._contract_id = cached
            return cached
        return None

    # ── Raw data fetchers (require a live IBKR connection) ─────────────────

    async def _get_1min_bars(self, contract_id, num_bars: int = 60) -> list:
        """1-minute OHLCV bars for the contract. [] — no fabricated candles — until IBKR is reachable."""
        return []

    async def _get_snapshot(self, contract_id) -> dict:
        """Live bid/ask/last/volume/open-interest snapshot. {} until IBKR is reachable."""
        return {}

    # ── Pure calculation helpers (real math, ready for real bars) ──────────

    @staticmethod
    def _calculate_vwap(bars: list):
        """Exact VWAP: Σ(((h+l+c)/3) × v) / Σ(v)."""
        if not bars:
            return None
        num = sum(((b["high"] + b["low"] + b["close"]) / 3.0) * b["volume"] for b in bars)
        den = sum(b["volume"] for b in bars)
        return round(num / den, 2) if den else None

    @staticmethod
    def _calculate_delta(bars: list, lookback: int = 15):
        """
        Kaufman-style approximation of buy/sell pressure from OHLCV alone:
          delta_per_bar = volume × ((close − low) − (high − close)) / (high − low)
        Summed over the most recent `lookback` 1-minute bars (default 15).
        Negative = selling pressure dominant; positive = buying pressure dominant.
        """
        if not bars:
            return None
        recent = bars[-lookback:]
        total = 0.0
        for b in recent:
            rng = b["high"] - b["low"]
            if rng <= 0:
                continue
            total += b["volume"] * (((b["close"] - b["low"]) - (b["high"] - b["close"])) / rng)
        return round(total, 1)

    @staticmethod
    def _calculate_volume_profile(bars: list, buckets: int = 20):
        """
        Distributes traded volume across `buckets` evenly-spaced price levels
        spanning the bars' [low, high] range, then derives:
          POC (Point of Control)  — price level with the most traded volume
          VAH (Value Area High)   — upper bound of the ~70%-of-volume value area
          VAL (Value Area Low)    — lower bound of the ~70%-of-volume value area
        """
        if not bars:
            return None
        lo = min(b["low"] for b in bars)
        hi = max(b["high"] for b in bars)
        if hi <= lo:
            return None
        width = (hi - lo) / buckets
        vol_by_bucket = [0.0] * buckets

        for b in bars:
            b_lo, b_hi, vol = b["low"], b["high"], b["volume"]
            first = max(0, min(buckets - 1, int((b_lo - lo) / width)))
            last  = max(0, min(buckets - 1, int((b_hi - lo) / width)))
            span  = max(1, last - first + 1)
            for i in range(first, last + 1):
                vol_by_bucket[i] += vol / span

        total_vol = sum(vol_by_bucket)
        if total_vol <= 0:
            return None

        poc_idx = max(range(buckets), key=lambda i: vol_by_bucket[i])
        poc_price = round(lo + (poc_idx + 0.5) * width, 2)

        # Expand outward from POC until ~70% of volume is captured (value area).
        target = total_vol * 0.70
        captured = vol_by_bucket[poc_idx]
        lo_idx = hi_idx = poc_idx
        while captured < target and (lo_idx > 0 or hi_idx < buckets - 1):
            expand_lo = vol_by_bucket[lo_idx - 1] if lo_idx > 0 else -1.0
            expand_hi = vol_by_bucket[hi_idx + 1] if hi_idx < buckets - 1 else -1.0
            if expand_hi >= expand_lo:
                hi_idx += 1
                captured += vol_by_bucket[hi_idx]
            else:
                lo_idx -= 1
                captured += vol_by_bucket[lo_idx]

        return {
            "poc_price": poc_price,
            "vah":       round(lo + (hi_idx + 1) * width, 2),
            "val":       round(lo + lo_idx * width, 2),
        }

    # ── Master method ───────────────────────────────────────────────────────

    async def get_order_flow(self) -> dict:
        """
        Complete order-flow snapshot for GC front month. Cached 60 seconds.

        Returns status='live' with real VWAP / cumulative-delta / volume-profile
        numbers once a reachable IBKR feed is wired up server-side. Until then,
        returns status='disconnected' with an honest rationale and every
        data field explicitly None — never a fabricated price, delta, or level.
        """
        cached = await cache_get(CACHE_KEY)
        if cached:
            return cached

        contract_id = await self._resolve_contract_id()
        if not contract_id:
            result = {
                "status":           "disconnected",
                "current_price":    None,
                "session_vwap":     None,
                "vwap_signal":      "unavailable",
                "cumulative_delta": None,
                "delta_direction":  "unavailable",
                "poc_price":        None,
                "vah":              None,
                "val":              None,
                "spread_ok":        True,  # fail-open — absence of IBKR data must not itself BLOCK a signal
                "rationale": (
                    "No reachable IBKR connection from the deployed backend. The "
                    "'IBKR MCP connector' is wired into the interactive Claude Code "
                    "agent session, not this standalone Railway process; config.py's "
                    "ibkr_host/ibkr_port (127.0.0.1:7497) point at a local TWS/Gateway "
                    "socket also unreachable from the cloud. Real order-flow data "
                    "requires deploying an IBeam Client Portal Gateway (or equivalent) "
                    "reachable from Railway — tracked as a separate integration task."
                ),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            await cache_set(CACHE_KEY, result, ttl_seconds=60)
            return result

        # ── Live path (runs once a real IBKR connection exists) ────────────
        bars     = await self._get_1min_bars(contract_id, num_bars=60)
        snapshot = await self._get_snapshot(contract_id)

        vwap    = self._calculate_vwap(bars)
        delta   = self._calculate_delta(bars)
        profile = self._calculate_volume_profile(bars) or {}
        price   = (snapshot.get("last") or {}).get("price")

        vwap_signal = "unavailable"
        if price is not None and vwap is not None:
            vwap_signal = "bearish" if price < vwap else "bullish"

        delta_direction = "unavailable"
        if delta is not None:
            delta_direction = "negative" if delta < 0 else "positive"

        bid = (snapshot.get("bid-ask") or {}).get("bid")
        ask = (snapshot.get("bid-ask") or {}).get("ask")
        spread_ok = True
        if bid is not None and ask is not None:
            spread_ok = (ask - bid) < 0.50

        result = {
            "status":           "live",
            "current_price":    price,
            "session_vwap":     vwap,
            "vwap_signal":      vwap_signal,
            "cumulative_delta": delta,
            "delta_direction":  delta_direction,
            "poc_price":        profile.get("poc_price"),
            "vah":              profile.get("vah"),
            "val":              profile.get("val"),
            "spread_ok":        spread_ok,
            "fetched_at":       datetime.now(timezone.utc).isoformat(),
        }
        await cache_set(CACHE_KEY, result, ttl_seconds=60)
        logger.info(
            f"IBKR order flow (live): price={price} vwap={vwap} "
            f"delta={delta} ({delta_direction}) poc={profile.get('poc_price')}"
        )
        return result
