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
MAX_TOKENS_HAIKU    = 300   # all regular haiku runs
MAX_TOKENS_SONNET   = 500   # daily deep analysis
MAX_TOKENS_SCENARIO = 600   # scenario engine (haiku)

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

    # IBKR (via MCP)
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1

    # Infrastructure
    redis_url: str = "redis://localhost:6379"

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
