"""
Actionable Signal Filter — synthesizes the Technical Fusion thesis,
the Multi-Timeframe confluence read, the Short-Score pre-conditions,
and the Macro Bias Score into a single "trade card" the dashboard can
render as one decision. Returns None when there is nothing actionable.
"""
from datetime import datetime, timezone


def build_trade_card(fusion: dict, multi_tf: dict, short_score: dict,
                      mbs: float, config: dict) -> dict | None:
    fusion      = fusion or {}
    multi_tf    = multi_tf or {}
    short_score = short_score or {}

    # ── Determine primary direction source ───────────────────────────
    # Prefer fusion when it has a directional signal.  Fall back to
    # multi-TF when fusion is absent, neutral, or NO_TRADE so the card
    # always reflects the best available signal.
    fusion_dir = (fusion.get("direction") or "").upper()
    mtf_dir_raw = (multi_tf.get("best_direction") or "").lower()
    mtf_dir     = "LONG" if mtf_dir_raw == "long" else ("SHORT" if mtf_dir_raw == "short" else "")

    fusion_quality = (fusion.get("setup_quality") or "NO_TRADE").upper()
    fusion_prob    = fusion.get("probability", 0) or 0

    # Choose source
    using_fusion = bool(fusion_dir and fusion_dir not in ("NEUTRAL", "") and
                        fusion_quality != "NO_TRADE" and fusion_prob >= 40)

    if using_fusion:
        direction = fusion_dir
        quality   = fusion_quality
        prob      = fusion_prob
    elif mtf_dir:
        # Multi-TF fallback — signal exists even though fusion is absent/neutral
        direction = mtf_dir
        quality   = "SCALP"
        prob      = int(multi_tf.get("edge_strength", 0) or 0)  # use edge as proxy
    else:
        return None

    # FILTER: pre-conditions (news / spread / daily limits)
    pre_conditions_pass = short_score.get("pre_conditions_pass", True)
    if not pre_conditions_pass:
        return None

    # ── Pull conviction / timeframe / edge / stop / TPs from multi-TF,
    #    but ONLY if multi-TF agrees with fusion's direction. If they
    #    disagree, multi-TF's levels were computed for the OTHER side
    #    and must not be borrowed. ────────────────────────────────────
    mtf_direction = (multi_tf.get("best_direction") or "").upper()
    agree = mtf_direction == direction

    if agree:
        conviction   = multi_tf.get("conviction") or "SCALP"
        timeframe    = multi_tf.get("best_timeframe") or "15min"
        edge         = multi_tf.get("edge_strength", 0) or 0
        stop_loss    = multi_tf.get("stop_loss") or fusion.get("invalidation")
        tps          = multi_tf.get("take_profits") or {}
        target_1     = (tps.get("tp1") or {}).get("price") or fusion.get("first_target")
        target_2     = (tps.get("tp2") or {}).get("price") or fusion.get("second_target")
        base_risk    = config.get("base_risk_pct", multi_tf.get("risk_pct", 0.5))
    else:
        # Fall back to fusion-only data — do NOT use multi-TF's
        # direction-specific stop/TP levels.
        conviction   = "HIGH CONVICTION" if quality == "HIGH_CONVICTION" else "SCALP"
        timeframe    = fusion.get("timeframe_alignment") or "—"
        edge         = 0
        stop_loss    = fusion.get("invalidation")
        target_1     = fusion.get("first_target")
        target_2     = fusion.get("second_target")
        base_risk    = config.get("base_risk_pct", 0.5)

    # ── Size adjustment from Macro Bias Score (-100..+100) ──────────
    size_mult = 1.0
    if (direction == "LONG" and mbs < -20) or (direction == "SHORT" and mbs > 20):
        size_mult = 0.5    # macro headwind
    elif (direction == "LONG" and mbs > 20) or (direction == "SHORT" and mbs < -20):
        size_mult = 1.25   # macro tailwind
    if quality == "WEAK":
        size_mult *= 0.5

    adjusted_risk = round(base_risk * size_mult, 3)

    if size_mult > 1:
        macro_note = "Macro tailwind – size increased"
    elif size_mult < 1:
        macro_note = "Macro headwind – size reduced"
    else:
        macro_note = "Macro neutral"

    return {
        "direction":           direction,
        "conviction":          conviction,
        "timeframe":           timeframe,
        "probability":         prob,
        "edge":                edge,
        "entry_zone":          fusion.get("entry_zone"),
        "invalidation":        fusion.get("invalidation"),
        "stop_loss":           stop_loss,
        "target_1":            target_1,
        "target_2":            target_2,
        "risk_pct":            adjusted_risk,
        "mbs":                 mbs,
        "macro_note":          macro_note,
        "reasoning":           fusion.get("reasoning", ""),
        "timeframe_alignment": fusion.get("timeframe_alignment", ""),
        "direction_agreement": agree,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }
