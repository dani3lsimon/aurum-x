# backend/main.py
import logging
import sys
import io
from contextlib import asynccontextmanager

# Force UTF-8 stdout on Windows to avoid cp1252 encoding errors in log output
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aurum-x")

# ── Routers ────────────────────────────────────────────────────────────────
from routers.forecast  import router as forecast_router
from routers.agents    import router as agents_router
from routers.scenarios import router as scenarios_router
from routers.alerts    import router as alerts_router
from routers.calendar  import router as calendar_router

# ── Agents ─────────────────────────────────────────────────────────────────
from agents.macro_agent        import MacroAgent
from agents.fed_agent          import FedAgent
from agents.yield_agent        import YieldAgent
from agents.dollar_agent       import DollarAgent
from agents.positioning_agent  import PositioningAgent
from agents.news_agent         import NewsAgent
from agents.geopolitical_agent import GeopoliticalAgent
from agents.liquidity_agent    import LiquidityAgent
from agents.historical_agent   import HistoricalAgent
from agents.regime_agent       import RegimeAgent

# ── Collectors ─────────────────────────────────────────────────────────────
from collectors.market_collector      import MarketCollector
from collectors.positioning_collector import PositioningCollector
from collectors.news_collector        import NewsCollector
from collectors.fmp_collector         import FMPCollector
from collectors.release_detector      import ReleaseDetector

# ── Engines ────────────────────────────────────────────────────────────────
from engines.bayesian_engine  import BayesianEngine
from engines.scenario_engine  import ScenarioEngine

# ── Scheduler ──────────────────────────────────────────────────────────────
from scheduler.task_scheduler import AurumScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("         AURUM-X  STARTING UP")
    logger.info("      Powered by Claude (Anthropic)")
    logger.info("      Market Data: FMP + IBKR + FRED")
    logger.info("=" * 50)

    agents = {
        "macro_agent":        MacroAgent(),
        "fed_agent":          FedAgent(),
        "yield_agent":        YieldAgent(),
        "dollar_agent":       DollarAgent(),
        "positioning_agent":  PositioningAgent(),
        "news_agent":         NewsAgent(),
        "geopolitical_agent": GeopoliticalAgent(),
        "liquidity_agent":    LiquidityAgent(),
        "historical_agent":   HistoricalAgent(),
        "regime_agent":       RegimeAgent(),
    }

    collectors = {
        "market":      MarketCollector(),
        "positioning": PositioningCollector(),
        "news":        NewsCollector(),
        "fmp":         FMPCollector(),
    }

    engines = {
        "bayesian": BayesianEngine(),
        "scenario": ScenarioEngine(),
    }

    release_detector = ReleaseDetector()

    scheduler = AurumScheduler()
    scheduler.register(agents, collectors, engines, release_detector)
    scheduler.start()

    app.state.scheduler        = scheduler
    app.state.agents           = agents
    app.state.collectors       = collectors
    app.state.engines          = engines
    app.state.release_detector = release_detector

    logger.info("AURUM-X operational — all agents, engines, and release detector active.")
    yield

    scheduler.scheduler.shutdown()
    logger.info("AURUM-X shutdown complete.")


app = FastAPI(
    title="AURUM-X API",
    description="Institutional Gold Macro Intelligence Platform — Powered by Claude",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://aurum-x.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(forecast_router)
app.include_router(agents_router)
app.include_router(scenarios_router)
app.include_router(alerts_router)
app.include_router(calendar_router)


@app.get("/health")
async def health():
    return {
        "status": "operational",
        "system": "AURUM-X",
        "version": "2.0.0",
        "ai": "Anthropic Claude",
        "model": "claude-opus-4-5",
        "data_sources": ["FMP MCP", "IBKR MCP", "FRED", "Finnhub"],
    }


@app.get("/")
async def root():
    return {
        "system": "AURUM-X",
        "version": "2.0.0",
        "ai_provider": "Anthropic Claude (claude-opus-4-5)",
        "endpoints": [
            "/forecast/latest",
            "/forecast/history",
            "/agents/scores",
            "/scenarios/latest",
            "/alerts/recent",
            "/calendar/upcoming",
            "/calendar/today",
            "/calendar/high-impact",
            "/health",
        ],
    }
