# backend/scheduler/task_scheduler.py
# Cost-optimised schedule — target $1/day
#
# Fast   (30 min):  news + geo          [haiku]
# Std    (2 hr):    yield+dollar+pos+liq+macro+fed [haiku]
# Heavy  (6 hr):    historical           [haiku]
# Deep   (08:00 UTC daily): macro+fed   [sonnet — premium]
# Regime: after std + heavy only        [haiku, 30-min skip]
# Scenario: every 4 hours               [haiku]
# Trigger: manual POST /forecast/trigger [all agents, haiku]
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class AurumScheduler:

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._agents           = {}
        self._collectors       = {}
        self._engines          = {}
        self._release_detector = None

    def register(self, agents: dict, collectors: dict, engines: dict, release_detector=None):
        self._agents           = agents
        self._collectors       = collectors
        self._engines          = engines
        self._release_detector = release_detector

    def start(self):
        # Fast: news + geo every 30 min
        self.scheduler.add_job(self._fast_cycle, IntervalTrigger(minutes=30),
                               id="fast_cycle", replace_existing=True)
        # Standard: market + macro agents every 2 hours (all haiku)
        self.scheduler.add_job(self._standard_cycle, IntervalTrigger(hours=2),
                               id="standard_cycle", replace_existing=True)
        # Heavy: historical every 6 hours
        self.scheduler.add_job(self._heavy_cycle, IntervalTrigger(hours=6),
                               id="heavy_cycle", replace_existing=True)
        # Deep daily: macro + fed with Sonnet at 08:00 UTC (London open)
        self.scheduler.add_job(self._daily_deep_cycle,
                               CronTrigger(hour=8, minute=0),
                               id="daily_deep", replace_existing=True)
        # Scenario engine every 4 hours
        self.scheduler.add_job(self._run_scenario_engine, IntervalTrigger(hours=4),
                               id="scenario_engine", replace_existing=True)
        # Release detector every 60 seconds
        self.scheduler.add_job(self._run_release_detector, IntervalTrigger(seconds=60),
                               id="release_detector", replace_existing=True)
        # COT positioning — Friday 22:00 UTC
        self.scheduler.add_job(self._run_cot_update,
                               CronTrigger(day_of_week="fri", hour=22),
                               id="cot_update", replace_existing=True)
        # Gold price every 5 min (free via FMP cache)
        self.scheduler.add_job(self._run_gold_price_update, IntervalTrigger(minutes=5),
                               id="gold_price", replace_existing=True)
        # Live XAUUSD price via ctrader_collector (FMP-backed until cTrader OAuth lands) — every 5 min
        self.scheduler.add_job(self._run_ctrader_price_update, IntervalTrigger(minutes=5),
                               id="ctrader_price", replace_existing=True)
        # Market data every 15 min
        self.scheduler.add_job(self._run_market_update, IntervalTrigger(minutes=15),
                               id="market_data", replace_existing=True)
        # FMP calendar every 4 hours
        self.scheduler.add_job(self._run_fmp_calendar_sync, IntervalTrigger(hours=4),
                               id="fmp_calendar", replace_existing=True)
        # Cache cleanup — delete expired Supabase cache rows every hour
        self.scheduler.add_job(self._run_cache_cleanup, IntervalTrigger(hours=1),
                               id="cache_cleanup", replace_existing=True)
        # Short-Setup Score Engine — 10-condition confluence gauge — every 5 min
        self.scheduler.add_job(self._run_short_score, IntervalTrigger(minutes=5),
                               id="short_score", replace_existing=True)
        # Gold price tracker for short_score_engine.gold_price_declining —
        # writes a timestamped snapshot to Supabase 'cache' every 5 min so the
        # engine can honestly compare "price now vs price 30 minutes ago"
        self.scheduler.add_job(self._record_gold_price, IntervalTrigger(minutes=5),
                               id="record_gold_price", replace_existing=True)
        # Daily 30-day rolling volatility calibration — 22:00 UTC (market close)
        self.scheduler.add_job(self._run_calibration,
                               CronTrigger(hour=22, minute=0, timezone="UTC"),
                               id="daily_calibration", replace_existing=True)
        # Multi-timeframe confluence engine (15min/1h/4h blended) — every 5 min
        self.scheduler.add_job(self._run_multi_tf, IntervalTrigger(minutes=5),
                               id="multi_tf", replace_existing=True)

        # Technical Fusion Agent — pre-compute every 5 min so users never wait
        # for the AI call. Cache is 60s; scheduler keeps it warm.
        self.scheduler.add_job(self._run_technical_fusion, IntervalTrigger(minutes=5),
                               id="technical_fusion", replace_existing=True)

        # Trade Card — synthesizes fusion + multi-TF + short-score + MBS into
        # one consolidated "next trade" decision. Runs every 5 min after fusion.
        self.scheduler.add_job(self._run_trade_card, IntervalTrigger(minutes=5),
                               id="trade_card", replace_existing=True)

        # SMC change monitor — every 30 seconds, zero cost (just diffs cached results)
        self.scheduler.add_job(self._run_smc_monitor, IntervalTrigger(seconds=30),
                               id="smc_monitor", replace_existing=True)

        # Kronos accuracy checker — resolves pending predictions every 15 min
        self.scheduler.add_job(self._check_kronos_predictions, IntervalTrigger(minutes=15),
                               id="kronos_accuracy_check", replace_existing=True)

        # Kronos forecast — fetch 2048 candles per TF and run inference every 5 min
        self.scheduler.add_job(self._run_kronos_forecast, IntervalTrigger(minutes=5),
                               id="kronos_forecast", replace_existing=True)

        self.scheduler.start()
        logger.info("AURUM-X Scheduler started — cost-optimised $1/day schedule active.")

    # ── Cycles ────────────────────────────────────────────────────────────

    async def _fast_cycle(self):
        logger.info(f"[FAST 30min] {datetime.utcnow().isoformat()}")
        scores = await self._run_agents(["news_agent", "geopolitical_agent"])
        # No regime after fast cycle — too expensive / data unchanged
        await self._update_gold_and_bayesian(scores, run_regime=False)

    async def _standard_cycle(self):
        logger.info(f"[STANDARD 2hr] {datetime.utcnow().isoformat()}")
        scores = await self._run_agents([
            "yield_agent", "dollar_agent", "positioning_agent",
            "liquidity_agent", "macro_agent", "fed_agent", "sentiment_agent",
        ])
        await self._update_gold_and_bayesian(scores, run_regime=True)

    async def _heavy_cycle(self):
        logger.info(f"[HEAVY 6hr] {datetime.utcnow().isoformat()}")
        scores = await self._run_agents(["historical_agent"])
        await self._update_gold_and_bayesian(scores, run_regime=True)

    async def _daily_deep_cycle(self):
        """08:00 UTC — premium Sonnet analysis for macro + fed."""
        from config import MODEL_SONNET, CACHE_TTL_SONNET, MAX_TOKENS_SONNET
        from agents.macro_agent import MacroAgent
        from agents.fed_agent import FedAgent
        logger.info(f"[DAILY DEEP 08:00 UTC] Running Sonnet macro+fed analysis")
        macro_sonnet = MacroAgent(model=MODEL_SONNET, skip_ttl=CACHE_TTL_SONNET)
        fed_sonnet   = FedAgent(model=MODEL_SONNET, skip_ttl=CACHE_TTL_SONNET)
        scores = []
        for agent in [macro_sonnet, fed_sonnet]:
            try:
                result = await agent.run()
                scores.append(result)
            except Exception as e:
                logger.error(f"Daily deep agent failed: {e}")
        await self._update_gold_and_bayesian(scores, run_regime=True)

    async def _run_agents(self, agent_names: list) -> list:
        scores = []
        for name in agent_names:
            agent = self._agents.get(name)
            if agent:
                try:
                    result = await agent.run()
                    scores.append(result)
                except Exception as e:
                    logger.error(f"Agent {name} failed: {e}")
        return scores

    async def _update_gold_and_bayesian(self, new_scores: list, run_regime: bool):
        from services.supabase_service import get_latest_forecast, get_latest_agent_scores
        from engines.alert_engine import AlertEngine

        old_forecast = await get_latest_forecast()
        regime = "unknown"

        if run_regime:
            regime_agent = self._agents.get("regime_agent")
            if regime_agent:
                try:
                    r = await regime_agent.run()
                    regime = r.get("regime", "unknown")
                except Exception as e:
                    logger.error(f"RegimeAgent failed: {e}")

        market = self._collectors.get("market")
        gold_price = 0.0
        if market:
            try:
                gd = await market.get_gold_price()
                gold_price = gd.get("price", 0) or 0.0
            except Exception:
                pass
        # Last-resort: pull from Supabase gold_prices table
        if gold_price < 500:
            try:
                from services.supabase_service import get_supabase
                sb = get_supabase()
                row = sb.table("gold_prices").select("price").order("timestamp", desc=True).limit(1).execute()
                if row.data:
                    gold_price = float(row.data[0]["price"])
            except Exception:
                pass

        all_scores = await get_latest_agent_scores()
        bayesian   = self._engines.get("bayesian")
        if bayesian and all_scores:
            new_forecast = await bayesian.compute(all_scores, regime, gold_price)
            await AlertEngine().check_and_fire(new_forecast, old_forecast)

    async def _run_all_agents(self, trigger_event: str = "scheduled"):
        """Called by manual /forecast/trigger endpoint and release detector."""
        logger.info(f"[ALL AGENTS] trigger={trigger_event}")
        scores = await self._run_agents(list(self._agents.keys()))
        await self._update_gold_and_bayesian(scores, run_regime=True)

    # ── Individual jobs ────────────────────────────────────────────────────

    async def _run_gold_price_update(self):
        market = self._collectors.get("market")
        if not market:
            return
        try:
            data = await market.get_gold_price()
            from services.redis_service import cache_set
            await cache_set("gold_price", data, ttl_seconds=360)
            price = data.get("price", 0)
            if price and price > 500:
                from services.supabase_service import get_supabase
                sb = get_supabase()
                sb.table("gold_prices").insert({
                    "price": price,
                    "source": data.get("source", "unknown"),
                    "timestamp": datetime.utcnow().isoformat(),
                }).execute()
        except Exception as e:
            logger.error(f"Gold price update failed: {e}")

    async def _record_gold_price(self):
        """Writes a 5-minute gold-price snapshot into Supabase 'cache' as
        gold_price_{YYYYMMDD_HHMM} (rounded to the nearest 5-min bucket so
        short_score_engine._get_price_30min_ago() can look one back reliably).
        TTL is 40 min — comfortably covers the 30-min lookback plus clock drift.
        Honest no-op if no real price is available — never writes a fabricated
        value."""
        market = self._collectors.get("market")
        if not market:
            return
        try:
            data = await market.get_gold_price()
            price = data.get("price")
            if not price or price < 500:
                return
            now = datetime.utcnow()
            rounded = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
            key = f"gold_price_{rounded.strftime('%Y%m%d_%H%M')}"
            from services.redis_service import cache_set
            await cache_set(key, {"price": price, "ts": now.isoformat()}, ttl_seconds=2400)

            # NEW: check open signal outcomes (TP/SL hits) against this price
            try:
                from services.signal_journal import update_open_signals
                await update_open_signals(float(price))
            except Exception as e:
                logger.warning(f"Signal outcome check failed: {e}")
        except Exception as e:
            logger.error(f"Gold price recording failed: {e}")

    async def _run_ctrader_price_update(self):
        ctrader = self._collectors.get("ctrader")
        if not ctrader:
            return
        try:
            from services.redis_service import cache_set
            data = await ctrader.get_gold_price()
            await cache_set("live_xauusd_price", data, ttl_seconds=360)
        except Exception as e:
            logger.error(f"cTrader price update failed: {e}")

    async def _run_market_update(self):
        market = self._collectors.get("market")
        if market:
            try:
                from services.redis_service import cache_set
                yields     = await market.get_yield_data()
                currencies = await market.get_currency_data()
                await cache_set("yields",     yields,     ttl_seconds=900)
                await cache_set("currencies", currencies, ttl_seconds=900)
            except Exception as e:
                logger.error(f"Market update failed: {e}")

    async def _run_release_detector(self):
        if self._release_detector:
            try:
                new_releases = await self._release_detector.poll_and_detect()
                if new_releases:
                    high_impact = [r for r in new_releases
                                   if r.get("gold_sensitivity") in ("critical", "high")]
                    if high_impact:
                        logger.info("High-impact release — triggering standard cycle")
                        await self._standard_cycle()
            except Exception as e:
                logger.error(f"Release detector failed: {e}")

    async def _run_cot_update(self):
        pos = self._collectors.get("positioning")
        if pos:
            try:
                await pos.update_from_fmp()
            except Exception as e:
                logger.error(f"COT update failed: {e}")

    async def _run_scenario_engine(self):
        scenario_engine = self._engines.get("scenario")
        if scenario_engine:
            try:
                from services.supabase_service import get_latest_forecast, get_latest_agent_scores
                forecast = await get_latest_forecast()
                scores   = await get_latest_agent_scores()
                if forecast:
                    await scenario_engine.generate(forecast, scores)
            except Exception as e:
                logger.error(f"Scenario engine failed: {e}")

    async def _run_cache_cleanup(self):
        from services.redis_service import cleanup_expired
        await cleanup_expired()

    async def _run_short_score(self):
        """Short-Setup Score Engine — re-evaluates the 10-condition confluence
        gauge, persists a row to intraday_signals, and broadcasts
        {'type': 'short_score_update'} over the websocket. Every 5 minutes."""
        engine = self._engines.get("short_score")
        if not engine:
            return
        try:
            await engine.evaluate()
        except Exception as e:
            logger.error(f"Short-score engine failed: {e}")

    async def _run_calibration(self):
        """Daily 30-day rolling volatility calibration from real OANDA H1
        candles — feeds the confluence engine's calibrated thresholds."""
        try:
            from services.signal_calibrator import compute_calibration
            result = await compute_calibration()
            logger.info(f"Daily calibration complete: {result.get('status')}")
        except Exception as e:
            logger.error(f"Calibration job error: {e}")

    async def _run_multi_tf(self):
        """Multi-timeframe confluence engine — re-evaluates the bi-directional
        9-condition gauge at 15min/1h/4h on real OANDA candles, persists an
        audit row, and broadcasts {'type': 'multi_tf_update'}. Every 5 minutes."""
        try:
            from engines.multi_tf_engine import evaluate_multi_tf
            result = await evaluate_multi_tf()
            logger.info(f"Multi-TF: {result.get('best_signal')} | TF: {result.get('best_timeframe')}")
        except Exception as e:
            logger.error(f"Multi-TF scheduler error: {e}")

    async def _run_smc_monitor(self):
        """Zero-cost change detector — diffs cached SMC + Fusion results every 30s
        and broadcasts a WebSocket 'smc_change' event when direction/alignment flips."""
        try:
            from services.smc_monitor import check_for_changes
            await check_for_changes()
        except Exception as e:
            logger.error(f"SMC monitor scheduler error: {e}")

    async def _check_kronos_predictions(self):
        """Resolve pending Kronos predictions whose target_time has passed."""
        try:
            from services.kronos_tracker import check_pending_predictions
            await check_pending_predictions()
        except Exception as e:
            logger.error(f"Kronos accuracy check error: {e}")

    async def _run_technical_fusion(self):
        """Pre-compute the Technical Fusion thesis every 5 min so the cache is
        always warm — users never stare at a loading state waiting for AI."""
        try:
            from services.redis_service import cache_delete
            from agents.technical_fusion_agent import TechnicalFusionAgent
            # Force a fresh run by busting the cache first
            await cache_delete("technical_fusion_signal")
            await TechnicalFusionAgent().run()
        except Exception as e:
            logger.error(f"Technical fusion scheduler error: {e}")
        # Always rebuild trade card immediately after fusion completes so
        # the card reads the freshly written technical_fusion_signal cache.
        await self._run_trade_card()

    async def _run_trade_card(self):
        """Builds the consolidated Trade Card from latest cached fusion /
        multi-TF / short-score results + macro bias, caches it, broadcasts
        {'type': 'trade_card'}. Runs every 5 minutes, right after fusion."""
        try:
            from services.redis_service import cache_get, cache_set
            from engines.signal_filter import build_trade_card
            from engines.macro_bias import get_macro_bias
            from services.websocket_manager import ws_manager

            fusion      = await cache_get("technical_fusion_signal")
            multi_tf    = await cache_get("multi_tf_signal")
            short_score = await cache_get("short_score_signal")
            mbs         = await get_macro_bias()

            config = {"base_risk_pct": float(os.getenv("BASE_RISK_PCT", "0.5"))}
            card = build_trade_card(fusion, multi_tf, short_score, mbs, config)

            await cache_set("trade_card", card, ttl_seconds=420)  # 7 min > 5-min interval
            await ws_manager.broadcast({"type": "trade_card", "data": card, "mbs": mbs})
        except Exception as e:
            logger.error(f"Trade card error: {e}")

    async def _run_kronos_forecast(self):
        """Fetch 2048 OANDA candles per timeframe and run Kronos inference.
        Populates kronos_{tf} Redis cache keys read by /forecast/kronos/latest."""
        from collectors.oanda_collector import OandaCollector
        from services.kronos_client import get_kronos_forecast
        from services.redis_service import cache_delete

        oanda = OandaCollector()
        # tf_key → (OANDA granularity, pred_len)
        # 2048 M15 = 21 days of 15-min bars, predict 8 bars = 2h ahead
        # 2048 H1  = 85 days of hourly bars,  predict 12 bars = 12h ahead
        # 2048 H4  = 341 days of 4h bars,     predict 6 bars  = 24h ahead
        TF_MAP = {
            '15min': ('M15', 200, 8),
            '1h':    ('H1',  200, 8),
            '4h':    ('H4',  200, 8),
        }
        for tf_key, (granularity, n_candles, pred_len) in TF_MAP.items():
            try:
                candles = await oanda.get_candles('XAU_USD', granularity, n_candles)
                if len(candles) < 32:
                    logger.warning(f'Kronos {tf_key}: only {len(candles)} candles, skipping')
                    continue
                await cache_delete(f'kronos_{tf_key}')
                result = await get_kronos_forecast(candles, tf_key, pred_len)
                logger.info(
                    f'Kronos {tf_key}: {result.get("direction", "?")} '
                    f'{result.get("expected_move_pts", "?")} pts | '
                    f'{len(candles)} bars in'
                )
            except Exception as e:
                logger.error(f'Kronos forecast {tf_key} failed: {e}')

    async def _run_fmp_calendar_sync(self):
        try:
            fmp = self._collectors.get("fmp")
            if fmp:
                calendar = await fmp.get_economic_calendar(days_ahead=14)
                if calendar:
                    from services.supabase_service import insert_economic_releases
                    await insert_economic_releases(calendar)
        except Exception as e:
            logger.error(f"FMP calendar sync failed: {e}")
