# backend/collectors/release_detector.py
# Polls FRED for actual release values + FMP calendar for upcoming events.
# Detects surprise beats/misses and triggers agent re-runs.
import httpx
import logging
from datetime import datetime, timedelta
from config import get_settings
from services.supabase_service import insert_economic_releases, get_todays_releases
from services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)
settings = get_settings()

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# High-impact FRED series with gold sensitivity ratings
RELEASE_SERIES = {
    "CPI_YOY":        {"series": "CPIAUCSL",   "gold_sensitivity": "critical", "impact": "high"},
    "CORE_CPI":       {"series": "CPILFESL",   "gold_sensitivity": "critical", "impact": "high"},
    "CORE_PCE":       {"series": "PCEPILFE",   "gold_sensitivity": "critical", "impact": "high"},
    "NFP":            {"series": "PAYEMS",     "gold_sensitivity": "high",     "impact": "high"},
    "UNEMPLOYMENT":   {"series": "UNRATE",     "gold_sensitivity": "high",     "impact": "high"},
    "GDP":            {"series": "GDP",        "gold_sensitivity": "high",     "impact": "high"},
    "FED_FUNDS":      {"series": "FEDFUNDS",   "gold_sensitivity": "critical", "impact": "high"},
    "JOLTS":          {"series": "JTSJOL",     "gold_sensitivity": "medium",   "impact": "medium"},
    "RETAIL_SALES":   {"series": "RSAFS",      "gold_sensitivity": "medium",   "impact": "medium"},
    "PPI":            {"series": "PPIACO",     "gold_sensitivity": "high",     "impact": "high"},
}


class ReleaseDetector:
    """
    Polls FRED every 60 seconds for new actual values.
    When a new release is detected, persists it and fires a WebSocket alert.
    """

    def __init__(self):
        self._last_seen: dict[str, str] = {}  # series -> last known date

    async def poll_and_detect(self) -> list:
        """Main poll loop — returns list of new releases detected."""
        new_releases = []

        for name, config in RELEASE_SERIES.items():
            try:
                data = await self._fetch_fred(config["series"])
                if not data:
                    continue

                latest_date = data.get("date", "")
                latest_value_str = data.get("value", ".")

                # Skip missing values (FRED uses "." for unreleased)
                if latest_value_str == "." or not latest_value_str:
                    continue

                latest_value = float(latest_value_str)
                last_known = self._last_seen.get(name)

                if last_known is None:
                    # First run — seed the tracker, don't fire alert
                    self._last_seen[name] = latest_date
                    continue

                if latest_date != last_known:
                    # New release detected!
                    self._last_seen[name] = latest_date
                    release = await self._build_release(
                        name, config, latest_date, latest_value
                    )
                    new_releases.append(release)
                    logger.info(
                        f"NEW RELEASE [{name}]: {latest_value} on {latest_date}"
                    )
                    await self._persist_and_alert(release)

            except Exception as e:
                logger.warning(f"Release detector error [{name}]: {e}")

        return new_releases

    async def _fetch_fred(self, series_id: str) -> dict | None:
        params = {
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "limit": 2,
            "sort_order": "desc",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(FRED_BASE, params=params)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            return obs[0] if obs else None

    async def _build_release(
        self, name: str, config: dict, date: str, actual: float
    ) -> dict:
        """Build a release record with surprise calculation."""
        # Try to get previous value for surprise calc
        try:
            params = {
                "series_id": config["series"],
                "api_key": settings.fred_api_key,
                "file_type": "json",
                "limit": 3,
                "sort_order": "desc",
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(FRED_BASE, params=params)
                obs = resp.json().get("observations", [])
                previous = float(obs[1]["value"]) if len(obs) > 1 and obs[1]["value"] != "." else None
        except Exception:
            previous = None

        surprise = round(actual - previous, 4) if previous is not None else None
        surprise_pct = round((surprise / abs(previous)) * 100, 4) if (surprise and previous) else None

        return {
            "event": name,
            "country": "US",
            "release_date": datetime.utcnow().isoformat(),
            "actual": actual,
            "previous": previous,
            "surprise": surprise,
            "surprise_pct": surprise_pct,
            "impact": config["impact"],
            "gold_sensitivity": config["gold_sensitivity"],
            "direction_actual": self._classify_direction(name, surprise),
            "gold_impact_score": self._estimate_gold_impact(name, surprise, config),
            "processed": False,
            "source": "fred",
        }

    def _classify_direction(self, name: str, surprise: float | None) -> str:
        if surprise is None:
            return "unknown"
        if abs(surprise) < 0.01:
            return "inline"
        # For NFP, GDP, Retail Sales: beat = "better"
        # For CPI, PPI, PCE: beat = "worse" for gold (higher inflation = bullish)
        return "better" if surprise > 0 else "worse"

    def _estimate_gold_impact(self, name: str, surprise: float | None, config: dict) -> float:
        """Rough gold impact score from -100 to +100."""
        if surprise is None:
            return 0.0
        sensitivity_mult = {"critical": 3.0, "high": 2.0, "medium": 1.0}.get(
            config["gold_sensitivity"], 1.0
        )
        # Inflation surprises = bullish gold
        inflation_indicators = {"CPI_YOY", "CORE_CPI", "CORE_PCE", "PPI"}
        # Labour/growth surprises = bearish gold (hawkish Fed)
        bearish_indicators = {"NFP", "GDP", "RETAIL_SALES", "JOLTS"}

        raw = min(abs(surprise) * sensitivity_mult * 10, 100)
        if name in inflation_indicators:
            return round(raw if surprise > 0 else -raw, 2)
        elif name in bearish_indicators:
            return round(-raw if surprise > 0 else raw, 2)
        return 0.0

    async def _persist_and_alert(self, release: dict):
        try:
            await insert_economic_releases([release])
        except Exception as e:
            logger.error(f"Failed to persist release: {e}")

        try:
            await ws_manager.send_release_alert(release)
        except Exception as e:
            logger.error(f"Failed to broadcast release alert: {e}")
