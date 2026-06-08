# backend/engines/patterns_engine.py
"""
Deterministic Smart Money Concepts + price-action structure detection.
Detects: swing structure, BOS/ChoCH, liquidity grabs, fair value gaps,
order blocks, breaker blocks, head & shoulders, double tops/bottoms.
Computes a multi-timeframe confluence score. NO LLM, NO indicators.
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
import logging
from collectors.oanda_collector import OandaCollector
from services.redis_service import cache_get, cache_set

logger = logging.getLogger(__name__)

TF_MAP    = {"15min": ("M15", 250), "1h": ("H1", 250), "4h": ("H4", 250)}
TF_WEIGHT = {"15min": 1.0, "1h": 2.0, "4h": 3.0}   # higher TF = more weight


# ──────────────────────────────────────────────────────────────
# SWING DETECTION (fractals) — the foundation of all SMC logic
# ──────────────────────────────────────────────────────────────
def find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> Dict[str, List[int]]:
    highs, lows = df["high"].values, df["low"].values
    sh, sl = [], []
    for i in range(left, len(df) - right):
        if all(highs[i] >= highs[i-j] for j in range(1, left+1)) and \
           all(highs[i] >  highs[i+j] for j in range(1, right+1)):
            sh.append(i)
        if all(lows[i] <= lows[i-j] for j in range(1, left+1)) and \
           all(lows[i] <  lows[i+j] for j in range(1, right+1)):
            sl.append(i)
    return {"highs": sh, "lows": sl}


# ──────────────────────────────────────────────────────────────
# MARKET STRUCTURE: HH/HL/LH/LL → trend, plus BOS and ChoCH
# ──────────────────────────────────────────────────────────────
def analyze_structure(df: pd.DataFrame, swings: Dict) -> Dict:
    sh, sl = swings["highs"], swings["lows"]
    if len(sh) < 2 or len(sl) < 2:
        return {"trend": "undefined", "bos": None, "choch": None,
                "last_swing_high": None, "last_swing_low": None}

    last_highs = [df["high"].iloc[i] for i in sh[-2:]]
    last_lows  = [df["low"].iloc[i]  for i in sl[-2:]]
    hh = last_highs[-1] > last_highs[-2]
    hl = last_lows[-1]  > last_lows[-2]
    lh = last_highs[-1] < last_highs[-2]
    ll = last_lows[-1]  < last_lows[-2]

    if hh and hl:   trend = "bullish"
    elif lh and ll: trend = "bearish"
    else:           trend = "ranging"

    price          = df["close"].iloc[-1]
    last_sh_price  = df["high"].iloc[sh[-1]]
    last_sl_price  = df["low"].iloc[sl[-1]]

    bos = choch = None
    # BOS = continuation break; ChoCH = reversal break of the protected swing
    if price > last_sh_price:
        bos = "bullish" if trend == "bullish" else None
        choch = "bullish" if trend == "bearish" else None
    elif price < last_sl_price:
        bos = "bearish" if trend == "bearish" else None
        choch = "bearish" if trend == "bullish" else None

    return {
        "trend": trend, "bos": bos, "choch": choch,
        "last_swing_high": round(float(last_sh_price), 2),
        "last_swing_low":  round(float(last_sl_price), 2),
    }


# ──────────────────────────────────────────────────────────────
# LIQUIDITY GRAB: sweep beyond a prior swing then close back inside
# ──────────────────────────────────────────────────────────────
def detect_liquidity_grabs(df: pd.DataFrame, swings: Dict) -> List[Dict]:
    grabs = []
    n = len(df)
    for sh in swings["highs"][-8:]:
        level = df["high"].iloc[sh]
        for j in range(sh+1, min(sh+5, n)):
            if df["high"].iloc[j] > level and df["close"].iloc[j] < level:
                grabs.append({"type": "liquidity_grab", "direction": "bearish",
                              "level": round(float(level), 2), "age_bars": n-j-1})
                break
    for sl in swings["lows"][-8:]:
        level = df["low"].iloc[sl]
        for j in range(sl+1, min(sl+5, n)):
            if df["low"].iloc[j] < level and df["close"].iloc[j] > level:
                grabs.append({"type": "liquidity_grab", "direction": "bullish",
                              "level": round(float(level), 2), "age_bars": n-j-1})
                break
    # freshest first
    return sorted(grabs, key=lambda g: g["age_bars"])[:5]


# ──────────────────────────────────────────────────────────────
# FAIR VALUE GAP: 3-candle imbalance, with fill-state check
# bullish FVG: candle[i+1].low > candle[i-1].high
# ──────────────────────────────────────────────────────────────
def detect_fvg(df: pd.DataFrame) -> List[Dict]:
    fvgs = []
    n = len(df)
    cur_price = df["close"].iloc[-1]
    for i in range(1, n-1):
        c1_high, c1_low = df["high"].iloc[i-1], df["low"].iloc[i-1]
        c3_high, c3_low = df["high"].iloc[i+1], df["low"].iloc[i+1]

        if c3_low > c1_high:           # bullish gap
            top, bottom = c3_low, c1_high
            filled = cur_price <= bottom
            fvgs.append({"type": "fvg", "direction": "bullish",
                         "top": round(float(top), 2), "bottom": round(float(bottom), 2),
                         "age_bars": n-(i+1)-1, "state": "filled" if filled else "unfilled"})
        elif c3_high < c1_low:         # bearish gap
            top, bottom = c1_low, c3_high
            filled = cur_price >= top
            fvgs.append({"type": "fvg", "direction": "bearish",
                         "top": round(float(top), 2), "bottom": round(float(bottom), 2),
                         "age_bars": n-(i+1)-1, "state": "filled" if filled else "unfilled"})
    # keep unfilled, freshest first
    unfilled = [f for f in fvgs if f["state"] == "unfilled"]
    return sorted(unfilled, key=lambda f: f["age_bars"])[:6]


# ──────────────────────────────────────────────────────────────
# ORDER BLOCKS: last opposite-colour candle before an impulsive
# move that breaks the prior swing. Demand OB (bullish) / Supply OB.
# ──────────────────────────────────────────────────────────────
def detect_order_blocks(df: pd.DataFrame, swings: Dict) -> List[Dict]:
    obs = []
    n = len(df)
    atr = (df["high"] - df["low"]).tail(14).mean()
    cur_price = df["close"].iloc[-1]

    for i in range(2, n-1):
        body = abs(df["close"].iloc[i] - df["open"].iloc[i])
        # impulsive up candle → demand OB is the last down candle before it
        if df["close"].iloc[i] > df["open"].iloc[i] and body > atr * 1.2:
            for k in range(i-1, max(i-4, 0), -1):
                if df["close"].iloc[k] < df["open"].iloc[k]:   # last bearish candle
                    ob_high, ob_low = df["high"].iloc[k], df["low"].iloc[k]
                    mitigated = cur_price <= ob_low
                    obs.append({"type": "order_block", "direction": "bullish",
                                "top": round(float(ob_high), 2), "bottom": round(float(ob_low), 2),
                                "age_bars": n-k-1, "state": "mitigated" if mitigated else "active"})
                    break
        elif df["close"].iloc[i] < df["open"].iloc[i] and body > atr * 1.2:
            for k in range(i-1, max(i-4, 0), -1):
                if df["close"].iloc[k] > df["open"].iloc[k]:   # last bullish candle
                    ob_high, ob_low = df["high"].iloc[k], df["low"].iloc[k]
                    mitigated = cur_price >= ob_high
                    obs.append({"type": "order_block", "direction": "bearish",
                                "top": round(float(ob_high), 2), "bottom": round(float(ob_low), 2),
                                "age_bars": n-k-1, "state": "mitigated" if mitigated else "active"})
                    break
    active = [o for o in obs if o["state"] == "active"]
    return sorted(active, key=lambda o: o["age_bars"])[:5]


# ──────────────────────────────────────────────────────────────
# BREAKER BLOCK: an order block that price broke through, then
# returns to from the other side → role reversal.
# ──────────────────────────────────────────────────────────────
def detect_breaker_blocks(df: pd.DataFrame, order_blocks: List[Dict]) -> List[Dict]:
    breakers = []
    cur_price = df["close"].iloc[-1]
    # An order block flagged mitigated that price has since crossed is a breaker.
    # We approximate: a bullish OB whose bottom was broken becomes bearish breaker.
    for ob in order_blocks:
        if ob["direction"] == "bullish" and cur_price < ob["bottom"]:
            breakers.append({"type": "breaker_block", "direction": "bearish",
                             "top": ob["top"], "bottom": ob["bottom"], "age_bars": ob["age_bars"]})
        elif ob["direction"] == "bearish" and cur_price > ob["top"]:
            breakers.append({"type": "breaker_block", "direction": "bullish",
                             "top": ob["top"], "bottom": ob["bottom"], "age_bars": ob["age_bars"]})
    return breakers[:3]


# ──────────────────────────────────────────────────────────────
# HEAD & SHOULDERS (top & inverse) using three swing extremes
# ──────────────────────────────────────────────────────────────
def detect_head_shoulders(df: pd.DataFrame, swings: Dict, tol: float = 0.01) -> List[Dict]:
    out = []
    sh = swings["highs"]
    if len(sh) >= 3:
        l, h, r = sh[-3], sh[-2], sh[-1]
        lv, hv, rv = df["high"].iloc[l], df["high"].iloc[h], df["high"].iloc[r]
        if hv > lv and hv > rv and abs(lv - rv) / hv < tol:
            neck = float(df["low"].iloc[l:r+1].min())
            out.append({"type": "head_shoulders_top", "direction": "bearish",
                        "neckline": round(neck, 2), "target": round(neck - (hv - neck), 2),
                        "status": "confirmed" if df["close"].iloc[-1] < neck else "forming"})
    sl = swings["lows"]
    if len(sl) >= 3:
        l, h, r = sl[-3], sl[-2], sl[-1]
        lv, hv, rv = df["low"].iloc[l], df["low"].iloc[h], df["low"].iloc[r]
        if hv < lv and hv < rv and abs(lv - rv) / abs(hv) < tol:
            neck = float(df["high"].iloc[l:r+1].max())
            out.append({"type": "inverse_head_shoulders", "direction": "bullish",
                        "neckline": round(neck, 2), "target": round(neck + (neck - hv), 2),
                        "status": "confirmed" if df["close"].iloc[-1] > neck else "forming"})
    return out


# ──────────────────────────────────────────────────────────────
# DOUBLE TOP / BOTTOM with trough/peak confirmation
# ──────────────────────────────────────────────────────────────
def detect_double_patterns(df: pd.DataFrame, swings: Dict, tol: float = 0.008) -> List[Dict]:
    out = []
    sh = swings["highs"]
    if len(sh) >= 2:
        a, b = sh[-2], sh[-1]
        av, bv = df["high"].iloc[a], df["high"].iloc[b]
        if abs(av - bv) / max(av, bv) < tol:
            trough = float(df["low"].iloc[a:b+1].min())
            out.append({"type": "double_top", "direction": "bearish",
                        "level": round(float(max(av, bv)), 2), "neckline": round(trough, 2),
                        "status": "confirmed" if df["close"].iloc[-1] < trough else "forming"})
    sl = swings["lows"]
    if len(sl) >= 2:
        a, b = sl[-2], sl[-1]
        av, bv = df["low"].iloc[a], df["low"].iloc[b]
        if abs(av - bv) / max(abs(av), abs(bv)) < tol:
            peak = float(df["high"].iloc[a:b+1].max())
            out.append({"type": "double_bottom", "direction": "bullish",
                        "level": round(float(min(av, bv)), 2), "neckline": round(peak, 2),
                        "status": "confirmed" if df["close"].iloc[-1] > peak else "forming"})
    return out


# ──────────────────────────────────────────────────────────────
# CONFLUENCE SCORE per timeframe (-5 strong bearish .. +5 strong bullish)
# ──────────────────────────────────────────────────────────────
def score_timeframe(patterns: List[Dict], structure: Dict) -> float:
    score = 0.0

    def freshness(age):  # newer patterns weigh more
        return max(0.3, 1.0 - (age or 0) / 50.0)

    for p in patterns:
        d = 1 if p.get("direction") == "bullish" else -1 if p.get("direction") == "bearish" else 0
        w = {"liquidity_grab": 1.2, "fvg": 0.8, "order_block": 1.0,
             "breaker_block": 1.0, "head_shoulders_top": 1.5,
             "inverse_head_shoulders": 1.5, "double_top": 1.2,
             "double_bottom": 1.2}.get(p.get("type"), 0.5)
        if p.get("status") == "confirmed":
            w *= 1.5
        score += d * w * freshness(p.get("age_bars"))

    if structure.get("trend") == "bullish": score += 1.0
    elif structure.get("trend") == "bearish": score -= 1.0
    if structure.get("choch") == "bullish": score += 1.5
    elif structure.get("choch") == "bearish": score -= 1.5
    if structure.get("bos") == "bullish": score += 0.8
    elif structure.get("bos") == "bearish": score -= 0.8

    return round(max(-5.0, min(5.0, score)), 2)


async def _candles_to_df(granularity: str, count: int) -> Tuple[pd.DataFrame, list]:
    oanda   = OandaCollector()
    candles = await oanda.get_candles("XAU_USD", granularity, count)
    completed = [c for c in candles if c.get("complete", True)]
    if len(completed) < 60:
        return pd.DataFrame(), []
    df = pd.DataFrame([{"open": float(c["open"]), "high": float(c["high"]),
                        "low": float(c["low"]), "close": float(c["close"]),
                        "volume": int(c["volume"])} for c in completed])
    return df, completed


async def analyze_timeframe(tf: str) -> Dict:
    cfg = TF_MAP.get(tf)
    if not cfg:
        return {"error": "invalid timeframe"}
    df, _ = await _candles_to_df(*cfg)
    if df.empty:
        return {"error": "insufficient data", "timeframe": tf}

    swings    = find_swings(df)
    structure = analyze_structure(df, swings)
    patterns  = []
    patterns += detect_liquidity_grabs(df, swings)
    patterns += detect_fvg(df)
    obs       = detect_order_blocks(df, swings)
    patterns += obs
    patterns += detect_breaker_blocks(df, obs)
    patterns += detect_head_shoulders(df, swings)
    patterns += detect_double_patterns(df, swings)

    score = score_timeframe(patterns, structure)

    return {
        "timeframe":         tf,
        "current_price":     round(float(df["close"].iloc[-1]), 2),
        "structure":         structure,
        "patterns":          patterns,
        "confluence_score":  score,
        "bias": "bullish" if score > 1 else "bearish" if score < -1 else "neutral",
    }


async def analyze_all() -> Dict:
    cache_key = "smc_patterns_all_tf"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = {}
    weighted_total = 0.0
    for tf in ["15min", "1h", "4h"]:
        try:
            tf_result = await analyze_timeframe(tf)
            result[tf] = tf_result
            if "confluence_score" in tf_result:
                weighted_total += tf_result["confluence_score"] * TF_WEIGHT[tf]
        except Exception as e:
            logger.error(f"SMC {tf} error: {e}")
            result[tf] = {"error": str(e)}

    # Normalise weighted score to -5..+5
    max_w = sum(TF_WEIGHT.values()) * 5
    net   = round((weighted_total / max_w) * 5, 2) if max_w else 0

    biases = [result[tf].get("bias") for tf in ["15min", "1h", "4h"] if "bias" in result.get(tf, {})]
    bulls  = biases.count("bullish"); bears = biases.count("bearish")
    if   bulls >= 2 and bears == 0: alignment = "aligned_bullish"
    elif bears >= 2 and bulls == 0: alignment = "aligned_bearish"
    elif bulls and bears:           alignment = "conflicting"
    else:                            alignment = "neutral"

    result["net_confluence"] = net
    result["alignment"]      = alignment
    await cache_set(cache_key, result, ttl_seconds=120)
    return result
