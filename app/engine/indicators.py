"""
Technical Indicators Engine v2 — 15 indicator categories.
New additions: VWAP, SuperTrend, Ichimoku Cloud, Fibonacci, EMA Ribbon, Relative Strength.
"""

import pandas as pd
import numpy as np
from ta.trend import MACD, EMAIndicator, SMAIndicator, ADXIndicator, IchimokuIndicator
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator, VolumeWeightedAveragePrice
import structlog

log = structlog.get_logger()


def compute_all_indicators(df: pd.DataFrame, mode: str = "weekly") -> pd.DataFrame:
    """Compute all technical indicators. Mode: 'weekly' or 'monthly'."""
    if df is None or len(df) < 20:
        return df

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    open_ = df["Open"]

    # ── Moving Averages ───────────────────────────────────────────────────
    for period in [5, 10, 20, 50]:
        if len(df) >= period:
            df[f"SMA_{period}"] = SMAIndicator(close, window=period).sma_indicator()
            df[f"EMA_{period}"] = EMAIndicator(close, window=period).ema_indicator()

    # ── EMA Ribbon (NEW) ──────────────────────────────────────────────────
    for period in [8, 13, 21, 34, 55]:
        if len(df) >= period:
            df[f"EMA_R_{period}"] = EMAIndicator(close, window=period).ema_indicator()

    # ── MACD ──────────────────────────────────────────────────────────────
    macd = MACD(close, window_slow=26, window_fast=12, window_sign=9)
    df["MACD"] = macd.macd()
    df["MACD_Signal"] = macd.macd_signal()
    df["MACD_Hist"] = macd.macd_diff()

    # ── RSI ────────────────────────────────────────────────────────────────
    rsi_period = 14
    df["RSI_14"] = RSIIndicator(close, window=14).rsi()
    df["RSI_7"] = RSIIndicator(close, window=7).rsi()
    if mode == "monthly" and len(df) >= 21:
        df["RSI_21"] = RSIIndicator(close, window=21).rsi()

    # ── Bollinger Bands ───────────────────────────────────────────────────
    bb_dev = 2.0 if mode == "weekly" else 2.5
    bb = BollingerBands(close, window=20, window_dev=bb_dev)
    df["BB_Upper"] = bb.bollinger_hband()
    df["BB_Middle"] = bb.bollinger_mavg()
    df["BB_Lower"] = bb.bollinger_lband()
    df["BB_Width"] = bb.bollinger_wband()
    df["BB_Pct"] = bb.bollinger_pband()

    # ── Stochastic ────────────────────────────────────────────────────────
    stoch = StochasticOscillator(high, low, close, window=14, smooth_window=3)
    df["Stoch_K"] = stoch.stoch()
    df["Stoch_D"] = stoch.stoch_signal()

    # ── ADX ────────────────────────────────────────────────────────────────
    if len(df) >= 20:
        adx = ADXIndicator(high, low, close, window=14)
        df["ADX"] = adx.adx()
        df["ADX_Pos"] = adx.adx_pos()
        df["ADX_Neg"] = adx.adx_neg()

    # ── ATR ────────────────────────────────────────────────────────────────
    atr = AverageTrueRange(high, low, close, window=14)
    df["ATR"] = atr.average_true_range()

    # ── Williams %R ───────────────────────────────────────────────────────
    df["Williams_R"] = WilliamsRIndicator(high, low, close, lbp=14).williams_r()

    # ── OBV ────────────────────────────────────────────────────────────────
    df["OBV"] = OnBalanceVolumeIndicator(close, volume).on_balance_volume()

    # ── Volume Analysis ───────────────────────────────────────────────────
    df["Vol_SMA_10"] = volume.rolling(window=10).mean()
    df["Vol_SMA_20"] = volume.rolling(window=20).mean()
    df["Vol_Ratio"] = volume / df["Vol_SMA_20"]
    df["Vol_Pct_Change"] = volume.pct_change() * 100

    # ── VWAP (NEW) ────────────────────────────────────────────────────────
    try:
        vwap = VolumeWeightedAveragePrice(high, low, close, volume, window=14)
        df["VWAP"] = vwap.volume_weighted_average_price()
    except Exception:
        df["VWAP"] = ((high + low + close) / 3 * volume).cumsum() / volume.cumsum()

    # ── SuperTrend (NEW) ──────────────────────────────────────────────────
    factor = 3.0 if mode == "weekly" else 4.0
    atr_period = 10
    _compute_supertrend(df, atr_period, factor)

    # ── Ichimoku Cloud (NEW) ──────────────────────────────────────────────
    if len(df) >= 52:
        ichi = IchimokuIndicator(high, low, window1=9, window2=26, window3=52)
        df["Ichi_Tenkan"] = ichi.ichimoku_conversion_line()
        df["Ichi_Kijun"] = ichi.ichimoku_base_line()
        df["Ichi_SpanA"] = ichi.ichimoku_a()
        df["Ichi_SpanB"] = ichi.ichimoku_b()

    # ── Price Action ──────────────────────────────────────────────────────
    df["Daily_Return"] = close.pct_change() * 100
    df["Weekly_Return"] = close.pct_change(periods=5) * 100
    df["Monthly_Return"] = close.pct_change(periods=20) * 100
    df["Body_Size"] = abs(close - open_) / (high - low + 0.001)
    df["Upper_Shadow"] = (high - pd.concat([close, open_], axis=1).max(axis=1)) / (high - low + 0.001)
    df["Lower_Shadow"] = (pd.concat([close, open_], axis=1).min(axis=1) - low) / (high - low + 0.001)

    return df


def _compute_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    """Compute SuperTrend indicator."""
    hl2 = (df["High"] + df["Low"]) / 2
    atr = AverageTrueRange(df["High"], df["Low"], df["Close"], window=period).average_true_range()

    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=float)

    supertrend.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = -1

    for i in range(1, len(df)):
        if df["Close"].iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["Close"].iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        if direction.iloc[i] == 1:
            supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i - 1]) if direction.iloc[i - 1] == 1 else lower_band.iloc[i]
        else:
            supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i - 1]) if direction.iloc[i - 1] == -1 else upper_band.iloc[i]

    df["SuperTrend"] = supertrend
    df["SuperTrend_Dir"] = direction  # 1 = bullish, -1 = bearish


def compute_fibonacci_levels(df: pd.DataFrame, lookback: int = 60) -> dict:
    """Compute Fibonacci retracement levels from recent swing high/low."""
    if df is None or len(df) < lookback:
        return {}

    window = df.tail(lookback)
    swing_high = window["High"].max()
    swing_low = window["Low"].min()
    diff = swing_high - swing_low

    if diff < 0.01:
        return {}

    return {
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "fib_236": round(swing_high - 0.236 * diff, 2),
        "fib_382": round(swing_high - 0.382 * diff, 2),
        "fib_500": round(swing_high - 0.500 * diff, 2),
        "fib_618": round(swing_high - 0.618 * diff, 2),
        "fib_786": round(swing_high - 0.786 * diff, 2),
    }


def find_support_resistance(df: pd.DataFrame, window: int = 20) -> dict:
    """Find key support and resistance levels using pivot points and price clustering."""
    if df is None or len(df) < window:
        return {"supports": [], "resistances": [], "pivot": 0}

    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values

    last_high, last_low, last_close = high[-1], low[-1], close[-1]
    pivot = (last_high + last_low + last_close) / 3
    r1 = 2 * pivot - last_low
    r2 = pivot + (last_high - last_low)
    r3 = last_high + 2 * (pivot - last_low)
    s1 = 2 * pivot - last_high
    s2 = pivot - (last_high - last_low)
    s3 = last_low - 2 * (last_high - pivot)

    # Swing highs/lows
    swing_highs, swing_lows = [], []
    lookback = 3
    for i in range(lookback, len(high) - lookback):
        if high[i] == max(high[i - lookback: i + lookback + 1]):
            swing_highs.append(high[i])
        if low[i] == min(low[i - lookback: i + lookback + 1]):
            swing_lows.append(low[i])

    def cluster_levels(levels, threshold_pct=0.5):
        if not levels:
            return []
        levels = sorted(levels)
        clusters = [[levels[0]]]
        for lvl in levels[1:]:
            if (lvl - clusters[-1][-1]) / clusters[-1][-1] * 100 < threshold_pct:
                clusters[-1].append(lvl)
            else:
                clusters.append([lvl])
        return [round(np.mean(c), 2) for c in clusters]

    supports = cluster_levels(swing_lows[-10:]) + [round(s1, 2), round(s2, 2), round(s3, 2)]
    resistances = cluster_levels(swing_highs[-10:]) + [round(r1, 2), round(r2, 2), round(r3, 2)]

    current_price = close[-1]
    supports = sorted(set(s for s in supports if s < current_price), reverse=True)[:5]
    resistances = sorted(set(r for r in resistances if r > current_price))[:5]

    return {
        "supports": supports,
        "resistances": resistances,
        "pivot": round(pivot, 2),
        "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
        "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
    }
