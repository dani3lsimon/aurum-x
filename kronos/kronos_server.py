# ~/aurum-x/kronos/kronos_server.py
import os
import logging
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import pandas as pd
from model import Kronos, KronosTokenizer, KronosPredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('kronos')

TOKEN = os.environ.get('KRONOS_AUTH_TOKEN', 'change-me')

# Load once at startup — Kronos-mini (4.1M params) + Tokenizer-2k (context 2048)
logger.info('Loading Kronos-mini...')
tokenizer = KronosTokenizer.from_pretrained('NeoQuasar/Kronos-Tokenizer-2k')
model     = Kronos.from_pretrained('NeoQuasar/Kronos-mini')
predictor = KronosPredictor(model, tokenizer, device='cpu', max_context=2048)
logger.info('Kronos-mini loaded — ready')

app = FastAPI(title='Kronos Forecast Service')

FREQ_MAP = {'15min': '15min', '1h': '1H', '4h': '4H'}


class ForecastRequest(BaseModel):
    candles:  list   # [{open,high,low,close,volume,time}]
    freq:     str    # '15min' | '1h' | '4h'
    pred_len: int = 12


def _check_auth(authorization: str | None):
    if (authorization or '').replace('Bearer ', '').strip() != TOKEN:
        raise HTTPException(status_code=401, detail='Unauthorized')


@app.post('/forecast')
def forecast(req: ForecastRequest, authorization: str = Header(None)):
    _check_auth(authorization)
    if req.freq not in FREQ_MAP:
        raise HTTPException(400, f'freq must be one of {list(FREQ_MAP)}')

    df = pd.DataFrame(req.candles)
    required = {'open', 'high', 'low', 'close'}
    if not required.issubset(df.columns):
        raise HTTPException(400, f'candles must contain {required}')

    xts    = pd.to_datetime(df['time'])
    future = pd.date_range(
        start=xts.iloc[-1],
        periods=req.pred_len + 1,
        freq=FREQ_MAP[req.freq]
    )[1:]

    try:
        # sample_count=5 generates 5 stochastic paths and averages them
        pred = predictor.predict(
            df=df[['open', 'high', 'low', 'close']],
            x_timestamp=xts,
            y_timestamp=pd.Series(future),
            pred_len=req.pred_len,
            T=1.0, top_p=0.9, sample_count=5,
        )
    except Exception as e:
        logger.error(f'Kronos forecast error: {e}')
        raise HTTPException(500, f'Forecast failed: {str(e)}')

    cur    = float(df['close'].iloc[-1])
    fc     = float(pred['close'].iloc[-1])

    # Full per-bar forecast candles for chart rendering
    pred_candles = [
        {
            'time':  str(future[i]),
            'open':  round(float(pred['open'].iloc[i]),  2),
            'high':  round(float(pred['high'].iloc[i]),  2),
            'low':   round(float(pred['low'].iloc[i]),   2),
            'close': round(float(pred['close'].iloc[i]), 2),
        }
        for i in range(len(future))
    ]

    result = {
        'current_price':     round(cur, 2),
        'predicted_close':   round(fc, 2),
        'predicted_high':    round(float(pred['high'].max()), 2),
        'predicted_low':     round(float(pred['low'].min()), 2),
        'direction':         'bullish' if fc > cur else 'bearish',
        'expected_move_pts': round(fc - cur, 2),
        'expected_move_pct': round((fc - cur) / cur * 100, 3),
        'pred_len':          req.pred_len,
        'freq':              req.freq,
        'target_time':       str(future[-1]),
        'pred_candles':      pred_candles,
    }
    logger.info(f"Forecast: {req.freq} {result['direction']} {result['expected_move_pts']:+.2f} pts")
    return result


@app.get('/health')
def health():
    return {'status': 'ok', 'model': 'Kronos-mini', 'context': 2048}
