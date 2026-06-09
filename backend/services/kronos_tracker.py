# backend/services/kronos_tracker.py
"""
Logs every Kronos forecast and checks actual outcomes.
Provides directional hit rate per timeframe — the metric that
determines whether Kronos earns real weight in the fusion agent.
"""
import logging
from datetime import datetime, timezone
from services.supabase_service import get_supabase

logger = logging.getLogger(__name__)


async def log_forecast(forecast: dict, timeframe: str, entry_price: float):
    if not forecast.get('available'):
        return
    try:
        get_supabase().table('kronos_predictions').insert({
            'timeframe':           timeframe,
            'entry_price':         entry_price,
            'predicted_close':     forecast.get('predicted_close'),
            'predicted_high':      forecast.get('predicted_high'),
            'predicted_low':       forecast.get('predicted_low'),
            'predicted_direction': forecast.get('direction'),
            'expected_move_pts':   forecast.get('expected_move_pts'),
            'target_time':         forecast.get('target_time'),
        }).execute()
    except Exception as e:
        logger.warning(f'Kronos log error: {e}')


async def check_pending_predictions():
    """
    Called by scheduler every 15 min.
    For each prediction whose target_time has passed,
    fetch actual close from OANDA and record was_correct.
    """
    from collectors.oanda_collector import OandaCollector
    sb  = get_supabase()
    now = datetime.now(timezone.utc)

    try:
        pending = sb.table('kronos_predictions')\
            .select('*')\
            .is_('was_correct', 'null')\
            .lt('target_time', now.isoformat())\
            .limit(50)\
            .execute()
    except Exception as e:
        logger.warning(f'Kronos pending fetch error: {e}')
        return

    for row in (pending.data or []):
        try:
            candles = await OandaCollector().get_candles('XAU_USD', 'H1', 2)
            if not candles:
                continue
            actual     = float(candles[-1]['close'])
            entry      = float(row['entry_price'])
            actual_dir = 'bullish' if actual > entry else 'bearish'
            correct    = actual_dir == row['predicted_direction']
            sb.table('kronos_predictions').update({
                'actual_close':     actual,
                'actual_direction': actual_dir,
                'was_correct':      correct,
                'checked_at':       now.isoformat(),
            }).eq('id', row['id']).execute()
        except Exception as e:
            logger.warning(f'Kronos check error for row {row.get("id")}: {e}')


async def get_accuracy_stats() -> dict:
    """Returns hit rate per timeframe. Fusion agent reads this."""
    try:
        sb   = get_supabase()
        rows = sb.table('kronos_predictions')\
            .select('timeframe, was_correct')\
            .not_.is_('was_correct', 'null')\
            .execute().data or []
    except Exception as e:
        logger.warning(f'Kronos accuracy fetch error: {e}')
        rows = []

    stats = {}
    for tf in ['15min', '1h', '4h']:
        tf_rows = [r for r in rows if r['timeframe'] == tf]
        n    = len(tf_rows)
        hits = sum(1 for r in tf_rows if r['was_correct'])
        stats[tf] = {
            'n':        n,
            'hit_rate': round(hits / n * 100, 1) if n else None,
            'trusted':  n >= 20 and (hits / n) > 0.55 if n else False,
            'note':     f'{hits}/{n} correct' if n else 'insufficient data',
        }
    return stats
