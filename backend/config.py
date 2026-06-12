# backend/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

# ── Anthropic model tiers ──────────────────────────────────────────────────
MODEL_SONNET = "claude-sonnet-4-5"   # premium daily deep analysis (once/day)
MODEL_HAIKU  = "claude-haiku-4-5"    # all regular agent runs

# ── DeepSeek fallback models ───────────────────────────────────────────────
DEEPSEEK_BASE_URL    = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL_HEAVY = "deepseek-reasoner"
DEEPSEEK_MODEL_LIGHT = "deepseek-reasoner"

# ── Anthropic cost per 1K tokens ──────────────────────────────────────────
COST_PER_1K_INPUT_SONNET  = 0.003
COST_PER_1K_OUTPUT_SONNET = 0.015
COST_PER_1K_INPUT_HAIKU   = 0.001
COST_PER_1K_OUTPUT_HAIKU  = 0.005

# ── DeepSeek cost per 1K tokens ───────────────────────────────────────────
COST_PER_1K_INPUT_DS_CHAT      = 0.00014
COST_PER_1K_OUTPUT_DS_CHAT     = 0.00028
COST_PER_1K_INPUT_DS_REASONER  = 0.00055
COST_PER_1K_OUTPUT_DS_REASONER = 0.00219

# ── Max tokens per tier ────────────────────────────────────────────────────
# deepseek-reasoner uses reasoning_content (chain-of-thought) + content (final answer).
# Both count toward max_tokens. Reasoning alone can consume 500-1500 tokens, so the
# old Haiku values (650/800) left zero budget for the final JSON content field.
MAX_TOKENS_HAIKU    = 3000  # all regular agent runs — reasoning (~1500) + JSON output (~500)
MAX_TOKENS_SONNET   = 6000  # daily deep analysis — more complex prompts need more reasoning
MAX_TOKENS_SCENARIO = 6000  # scenario engine — 3 scenarios with narrative need extra room
MAX_TOKENS_SENTIMENT = 3000  # sentiment_agent — aligned with MAX_TOKENS_HAIKU

# ── Redis TTL for prompt-hash skip cache (= agent cycle time) ─────────────
CACHE_TTL_FAST     = 30 * 60    # 30 min  — news/geo cycle
CACHE_TTL_STANDARD = 2  * 3600  # 2 hr    — market agents
CACHE_TTL_HEAVY    = 6  * 3600  # 6 hr    — historical
CACHE_TTL_REGIME   = 30 * 60    # 30 min  — regime minimum gap
CACHE_TTL_SCENARIO = 4  * 3600  # 4 hr    — scenario engine
CACHE_TTL_SONNET   = 24 * 3600  # 24 hr   — daily sonnet run


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = ""

    # DeepSeek fallback
    deepseek_api_key: str = ""

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Data APIs
    fred_api_key: str
    finnhub_api_key: str

    # cTrader
    ctrader_client_id: str = ""
    ctrader_client_secret: str = ""
    ctrader_account_id: str = ""

    # cTrader VPS tick bridge — direct broker WebSocket/REST relay (no agent)
    ctrader_bridge_url:   str = "https://70-156-8-139.sslip.io"
    ctrader_bridge_ws:    str = "wss://70-156-8-139.sslip.io/ws"
    ctrader_bridge_token: str = ""

    # OANDA v20 REST API — primary XAU_USD/FX/order-flow source
    oanda_api_token:   str = ""
    oanda_account_id:  str = ""
    oanda_environment: str = "practice"
    # Practice-account XAU_USD spreads run ~1.0-2.0; live-account spreads run
    # ~0.30-0.60. Set generously for practice so spread_acceptable isn't
    # permanently false — tighten to ~0.5 when switching to a live account.
    oanda_spread_threshold: float = 2.0

    # Used only for the engine's display-only VIX-based position-size suggestion
    # (AURUM-X never executes trades — this is informational sizing guidance).
    account_size_usd: float = 10000.0

    @property
    def oanda_base_url(self) -> str:
        if self.oanda_environment == "practice":
            return "https://api-fxpractice.oanda.com"
        return "https://api-fxtrade.oanda.com"

    # Kronos probabilistic forecast microservice (separate VM — no torch on Railway)
    kronos_service_url:  str = ""   # e.g. https://1.2.3.4.sslip.io/kronos
    kronos_auth_token:   str = ""

    # Cache via Supabase cache table — Redis not required
    redis_url: str = ""

    # Alert thresholds
    probability_alert_threshold: float = 10.0
    confidence_alert_threshold: float  = 15.0

    # Agent weights (must sum to 1.0)
    agent_weights: dict = {
        "macro":        0.20,
        "fed":          0.18,
        "yield":        0.15,
        "dollar":       0.12,
        "positioning":  0.10,
        "news":         0.08,
        "geopolitical": 0.07,
        "liquidity":    0.05,
        "historical":   0.03,
        "regime":       0.02,
    }

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings():
    return Settings()


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if "sonnet" in model:
        return (input_tokens  / 1000 * COST_PER_1K_INPUT_SONNET +
                output_tokens / 1000 * COST_PER_1K_OUTPUT_SONNET)
    else:  # haiku
        return (input_tokens  / 1000 * COST_PER_1K_INPUT_HAIKU +
                output_tokens / 1000 * COST_PER_1K_OUTPUT_HAIKU)


def estimate_deepseek_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if "reasoner" in model:
        return (input_tokens  / 1000 * COST_PER_1K_INPUT_DS_REASONER +
                output_tokens / 1000 * COST_PER_1K_OUTPUT_DS_REASONER)
    else:
        return (input_tokens  / 1000 * COST_PER_1K_INPUT_DS_CHAT +
                output_tokens / 1000 * COST_PER_1K_OUTPUT_DS_CHAT)
