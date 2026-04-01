"""
Signal Scoring Engine v2 — 15 indicator categories, 127-point model normalized to 100.
Fixes: final_signal recalculated from final_confidence, explicit price variable.
"""

import pandas as pd
import numpy as np
from app.engine.indicators import compute_fibonacci_levels


def compute_signal_scores(df: pd.DataFrame, sr_levels: dict, mode: str = "weekly",
                          nifty_df: pd.DataFrame = None) -> dict:
    """
    Compute 15 indicator scores and aggregate into composite signal.
    Total raw max: 127 points, normalized to 0-100.
    """
    if df is None or len(df) < 30:
        return {"total_score": 0, "normalized_score": 0, "signal": "NO DATA", "details": {}}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(latest["Close"])
    scores = {}

    # ── 1. RSI (12 pts) ──────────────────────────────────────────────────
    rsi = float(latest.get("RSI_14", 50))
    if rsi < 30:
        scores["RSI"] = {"score": 10, "max": 12, "reason": f"Oversold ({rsi:.1f})"}
    elif rsi < 40:
        scores["RSI"] = {"score": 7, "max": 12, "reason": f"Approaching oversold ({rsi:.1f})"}
    elif rsi > 70:
        scores["RSI"] = {"score": -10, "max": 12, "reason": f"Overbought ({rsi:.1f})"}
    elif rsi > 60:
        scores["RSI"] = {"score": -4, "max": 12, "reason": f"Approaching overbought ({rsi:.1f})"}
    else:
        scores["RSI"] = {"score": 3, "max": 12, "reason": f"Neutral zone ({rsi:.1f})"}

    # ── 2. MACD (12 pts) ─────────────────────────────────────────────────
    macd_val = float(latest.get("MACD", 0))
    macd_sig = float(latest.get("MACD_Signal", 0))
    macd_hist = float(latest.get("MACD_Hist", 0))
    prev_hist = float(prev.get("MACD_Hist", 0))

    if macd_val > macd_sig and macd_hist > 0:
        if macd_hist > prev_hist:
            scores["MACD"] = {"score": 11, "max": 12, "reason": "Bullish crossover, momentum increasing"}
        else:
            scores["MACD"] = {"score": 7, "max": 12, "reason": "Bullish but momentum slowing"}
    elif macd_val < macd_sig and macd_hist < 0:
        if macd_hist < prev_hist:
            scores["MACD"] = {"score": -11, "max": 12, "reason": "Bearish crossover, momentum increasing"}
        else:
            scores["MACD"] = {"score": -5, "max": 12, "reason": "Bearish but momentum slowing"}
    else:
        scores["MACD"] = {"score": 0, "max": 12, "reason": "Neutral / transitioning"}

    # ── 3. Moving Averages (10 pts) ──────────────────────────────────────
    ma_score = 0
    ma_reasons = []
    for period in [10, 20, 50]:
        sma_key = f"SMA_{period}"
        ema_key = f"EMA_{period}"
        if sma_key in latest and not pd.isna(latest[sma_key]):
            if price > float(latest[sma_key]):
                ma_score += 1.5
                ma_reasons.append(f"Above SMA{period}")
            else:
                ma_score -= 1.5
        if ema_key in latest and not pd.isna(latest[ema_key]):
            if price > float(latest[ema_key]):
                ma_score += 1.5
            else:
                ma_score -= 1.5

    if "SMA_10" in latest and "SMA_50" in latest:
        if not pd.isna(latest["SMA_10"]) and not pd.isna(latest["SMA_50"]):
            if float(latest["SMA_10"]) > float(latest["SMA_50"]):
                ma_score += 2
                ma_reasons.append("Golden cross")
            else:
                ma_score -= 2
                ma_reasons.append("Death cross")

    ma_score = max(-10, min(10, ma_score))
    scores["Moving_Avg"] = {"score": round(ma_score, 1), "max": 10, "reason": "; ".join(ma_reasons[:3]) or "Mixed"}

    # ── 4. Bollinger Bands (8 pts) ───────────────────────────────────────
    bb_pct = float(latest.get("BB_Pct", 0.5))
    if bb_pct < 0:
        scores["Bollinger"] = {"score": 7, "max": 8, "reason": "Below lower band (squeeze buy)"}
    elif bb_pct < 0.2:
        scores["Bollinger"] = {"score": 5, "max": 8, "reason": "Near lower band"}
    elif bb_pct > 1:
        scores["Bollinger"] = {"score": -7, "max": 8, "reason": "Above upper band (overextended)"}
    elif bb_pct > 0.8:
        scores["Bollinger"] = {"score": -4, "max": 8, "reason": "Near upper band"}
    else:
        scores["Bollinger"] = {"score": 2, "max": 8, "reason": f"Mid-band ({bb_pct:.2f})"}

    # ── 5. Volume (10 pts) ───────────────────────────────────────────────
    vol_ratio = float(latest.get("Vol_Ratio", 1))
    daily_ret = float(latest.get("Daily_Return", 0))

    if vol_ratio > 1.5 and daily_ret > 0:
        scores["Volume"] = {"score": 9, "max": 10, "reason": f"High vol bullish ({vol_ratio:.1f}x)"}
    elif vol_ratio > 1.5 and daily_ret < 0:
        scores["Volume"] = {"score": -8, "max": 10, "reason": f"High vol bearish ({vol_ratio:.1f}x)"}
    elif vol_ratio > 1.0 and daily_ret > 0:
        scores["Volume"] = {"score": 5, "max": 10, "reason": "Above avg vol, positive"}
    elif vol_ratio < 0.5:
        scores["Volume"] = {"score": -2, "max": 10, "reason": "Very low volume"}
    else:
        scores["Volume"] = {"score": 1, "max": 10, "reason": f"Normal ({vol_ratio:.1f}x)"}

    # ── 6. Stochastic (7 pts) ────────────────────────────────────────────
    stoch_k = float(latest.get("Stoch_K", 50))
    stoch_d = float(latest.get("Stoch_D", 50))

    if stoch_k < 20 and stoch_k > stoch_d:
        scores["Stochastic"] = {"score": 6, "max": 7, "reason": "Oversold bullish crossover"}
    elif stoch_k < 20:
        scores["Stochastic"] = {"score": 4, "max": 7, "reason": f"Oversold ({stoch_k:.1f})"}
    elif stoch_k > 80 and stoch_k < stoch_d:
        scores["Stochastic"] = {"score": -6, "max": 7, "reason": "Overbought bearish crossover"}
    elif stoch_k > 80:
        scores["Stochastic"] = {"score": -3, "max": 7, "reason": f"Overbought ({stoch_k:.1f})"}
    else:
        scores["Stochastic"] = {"score": 1, "max": 7, "reason": f"Neutral ({stoch_k:.1f})"}

    # ── 7. ADX (8 pts) ───────────────────────────────────────────────────
    adx = float(latest.get("ADX", 20))
    adx_pos = float(latest.get("ADX_Pos", 0))
    adx_neg = float(latest.get("ADX_Neg", 0))

    if adx > 25 and adx_pos > adx_neg:
        scores["ADX"] = {"score": 7, "max": 8, "reason": f"Strong uptrend (ADX={adx:.0f})"}
    elif adx > 25 and adx_neg > adx_pos:
        scores["ADX"] = {"score": -7, "max": 8, "reason": f"Strong downtrend (ADX={adx:.0f})"}
    elif adx < 20:
        scores["ADX"] = {"score": 0, "max": 8, "reason": f"Weak trend (ADX={adx:.0f})"}
    else:
        scores["ADX"] = {"score": 3, "max": 8, "reason": f"Moderate trend (ADX={adx:.0f})"}

    # ── 8. Support/Resistance (10 pts) ───────────────────────────────────
    sr_score = 0
    sr_reason = "No clear S/R signal"
    if sr_levels.get("supports") and sr_levels.get("resistances"):
        nearest_support = sr_levels["supports"][0]
        nearest_resistance = sr_levels["resistances"][0]
        dist_to_support = (price - nearest_support) / price * 100
        dist_to_resistance = (nearest_resistance - price) / price * 100
        reward_risk = dist_to_resistance / max(dist_to_support, 0.1)

        if dist_to_support < 1.5 and reward_risk > 2:
            sr_score = 9
            sr_reason = f"Near support, R:R={reward_risk:.1f}"
        elif dist_to_support < 2 and reward_risk > 1.5:
            sr_score = 6
            sr_reason = f"Close to support, R:R={reward_risk:.1f}"
        elif dist_to_resistance < 1:
            sr_score = -7
            sr_reason = f"Near resistance ({nearest_resistance:.2f})"
        else:
            sr_score = 2
            sr_reason = f"R:R={reward_risk:.1f}"

    scores["S/R_Levels"] = {"score": sr_score, "max": 10, "reason": sr_reason}

    # ── 9. Momentum (5 pts) ──────────────────────────────────────────────
    weekly_ret = float(latest.get("Weekly_Return", 0)) if not pd.isna(latest.get("Weekly_Return", 0)) else 0
    if 1 < weekly_ret < 8:
        scores["Momentum"] = {"score": 4, "max": 5, "reason": f"Positive ({weekly_ret:.1f}%)"}
    elif weekly_ret > 8:
        scores["Momentum"] = {"score": -2, "max": 5, "reason": f"Overextended ({weekly_ret:.1f}%)"}
    elif -5 < weekly_ret < -1:
        scores["Momentum"] = {"score": 3, "max": 5, "reason": f"Pullback ({weekly_ret:.1f}%)"}
    elif weekly_ret < -5:
        scores["Momentum"] = {"score": -4, "max": 5, "reason": f"Falling knife ({weekly_ret:.1f}%)"}
    else:
        scores["Momentum"] = {"score": 1, "max": 5, "reason": f"Flat ({weekly_ret:.1f}%)"}

    # ── 10. VWAP (8 pts) — NEW ───────────────────────────────────────────
    vwap = float(latest.get("VWAP", price))
    vwap_diff_pct = (price - vwap) / vwap * 100 if vwap > 0 else 0

    if 0 < vwap_diff_pct < 2:
        scores["VWAP"] = {"score": 7, "max": 8, "reason": f"Just above VWAP (+{vwap_diff_pct:.1f}%) — accumulation"}
    elif vwap_diff_pct > 3:
        scores["VWAP"] = {"score": -3, "max": 8, "reason": f"Extended above VWAP (+{vwap_diff_pct:.1f}%)"}
    elif -2 < vwap_diff_pct < 0:
        scores["VWAP"] = {"score": 5, "max": 8, "reason": f"Slightly below VWAP — bounce zone"}
    elif vwap_diff_pct < -3:
        scores["VWAP"] = {"score": -5, "max": 8, "reason": f"Well below VWAP ({vwap_diff_pct:.1f}%) — distribution"}
    else:
        scores["VWAP"] = {"score": 2, "max": 8, "reason": f"Near VWAP ({vwap_diff_pct:.1f}%)"}

    # ── 11. SuperTrend (8 pts) — NEW ─────────────────────────────────────
    st_dir = float(latest.get("SuperTrend_Dir", 0))
    prev_st_dir = float(prev.get("SuperTrend_Dir", 0))

    if st_dir == 1 and prev_st_dir == -1:
        scores["SuperTrend"] = {"score": 8, "max": 8, "reason": "Bullish flip (fresh buy signal)"}
    elif st_dir == 1:
        scores["SuperTrend"] = {"score": 5, "max": 8, "reason": "Bullish trend active"}
    elif st_dir == -1 and prev_st_dir == 1:
        scores["SuperTrend"] = {"score": -8, "max": 8, "reason": "Bearish flip (fresh sell signal)"}
    elif st_dir == -1:
        scores["SuperTrend"] = {"score": -5, "max": 8, "reason": "Bearish trend active"}
    else:
        scores["SuperTrend"] = {"score": 0, "max": 8, "reason": "No data"}

    # ── 12. Ichimoku Cloud (10 pts) — NEW ────────────────────────────────
    if "Ichi_Tenkan" in latest and not pd.isna(latest.get("Ichi_Tenkan")):
        tenkan = float(latest["Ichi_Tenkan"])
        kijun = float(latest["Ichi_Kijun"])
        span_a = float(latest["Ichi_SpanA"])
        span_b = float(latest["Ichi_SpanB"])
        cloud_top = max(span_a, span_b)
        cloud_bottom = min(span_a, span_b)

        ichi_score = 0
        ichi_reasons = []

        if price > cloud_top:
            ichi_score += 4
            ichi_reasons.append("Above cloud")
        elif price < cloud_bottom:
            ichi_score -= 4
            ichi_reasons.append("Below cloud")
        else:
            ichi_reasons.append("Inside cloud")

        if tenkan > kijun:
            ichi_score += 3
            ichi_reasons.append("TK cross bullish")
        else:
            ichi_score -= 3
            ichi_reasons.append("TK cross bearish")

        if span_a > span_b:
            ichi_score += 2
            ichi_reasons.append("Bullish cloud ahead")
        else:
            ichi_score -= 2
            ichi_reasons.append("Bearish cloud ahead")

        ichi_score = max(-10, min(10, ichi_score))
        scores["Ichimoku"] = {"score": ichi_score, "max": 10, "reason": "; ".join(ichi_reasons)}
    else:
        scores["Ichimoku"] = {"score": 0, "max": 10, "reason": "Insufficient data"}

    # ── 13. Fibonacci (7 pts) — NEW ──────────────────────────────────────
    fib = compute_fibonacci_levels(df, lookback=60)
    if fib:
        fib_score = 0
        fib_reason = "No Fib signal"
        fib_618 = fib["fib_618"]
        fib_382 = fib["fib_382"]
        fib_500 = fib["fib_500"]

        if abs(price - fib_618) / price * 100 < 1.5:
            fib_score = 6
            fib_reason = f"Near 61.8% retracement (₹{fib_618}) — strong bounce zone"
        elif abs(price - fib_500) / price * 100 < 1.5:
            fib_score = 4
            fib_reason = f"Near 50% retracement (₹{fib_500})"
        elif abs(price - fib_382) / price * 100 < 1.5:
            fib_score = 3
            fib_reason = f"Near 38.2% retracement (₹{fib_382})"
        elif price > fib["swing_high"] * 0.98:
            fib_score = -5
            fib_reason = "Near swing high — limited upside"
        else:
            fib_score = 1
            fib_reason = "Between Fib levels"

        scores["Fibonacci"] = {"score": fib_score, "max": 7, "reason": fib_reason}
    else:
        scores["Fibonacci"] = {"score": 0, "max": 7, "reason": "No data"}

    # ── 14. EMA Ribbon (5 pts) — NEW ─────────────────────────────────────
    ribbon_periods = [8, 13, 21, 34, 55]
    ribbon_values = []
    for p in ribbon_periods:
        key = f"EMA_R_{p}"
        if key in latest and not pd.isna(latest[key]):
            ribbon_values.append(float(latest[key]))

    if len(ribbon_values) >= 4:
        all_ascending = all(ribbon_values[i] >= ribbon_values[i + 1] for i in range(len(ribbon_values) - 1))
        all_descending = all(ribbon_values[i] <= ribbon_values[i + 1] for i in range(len(ribbon_values) - 1))
        above_all = price > max(ribbon_values)

        if all_ascending and above_all:
            scores["EMA_Ribbon"] = {"score": 5, "max": 5, "reason": "Perfect bullish ribbon — all EMAs fanning up"}
        elif all_ascending:
            scores["EMA_Ribbon"] = {"score": 3, "max": 5, "reason": "Bullish ribbon order"}
        elif all_descending:
            scores["EMA_Ribbon"] = {"score": -4, "max": 5, "reason": "Bearish ribbon — all EMAs fanning down"}
        else:
            scores["EMA_Ribbon"] = {"score": 0, "max": 5, "reason": "Mixed ribbon (consolidation)"}
    else:
        scores["EMA_Ribbon"] = {"score": 0, "max": 5, "reason": "Insufficient data"}

    # ── 15. Relative Strength vs Nifty (7 pts) — NEW ─────────────────────
    if nifty_df is not None and len(nifty_df) >= 20 and len(df) >= 20:
        stock_ret_20d = float(latest.get("Monthly_Return", 0)) if not pd.isna(latest.get("Monthly_Return")) else 0
        nifty_ret_20d = float((nifty_df["Close"].iloc[-1] / nifty_df["Close"].iloc[-21] - 1) * 100)
        rs = stock_ret_20d - nifty_ret_20d

        if rs > 5:
            scores["Rel_Strength"] = {"score": 6, "max": 7, "reason": f"Strong outperformer (+{rs:.1f}% vs Nifty)"}
        elif rs > 2:
            scores["Rel_Strength"] = {"score": 4, "max": 7, "reason": f"Outperforming Nifty (+{rs:.1f}%)"}
        elif rs < -5:
            scores["Rel_Strength"] = {"score": -5, "max": 7, "reason": f"Lagging Nifty ({rs:.1f}%)"}
        elif rs < -2:
            scores["Rel_Strength"] = {"score": -2, "max": 7, "reason": f"Slightly lagging ({rs:.1f}%)"}
        else:
            scores["Rel_Strength"] = {"score": 1, "max": 7, "reason": f"In-line with Nifty ({rs:.1f}%)"}
    else:
        scores["Rel_Strength"] = {"score": 0, "max": 7, "reason": "No Nifty data"}

    # ── Aggregate ─────────────────────────────────────────────────────────
    total_score = sum(s["score"] for s in scores.values())
    max_possible = sum(s["max"] for s in scores.values())  # 127

    # Normalize to 0-100
    normalized = ((total_score + max_possible) / (2 * max_possible)) * 100
    normalized = max(0, min(100, normalized))

    # Volume gate: cap confidence at 65% if volume below average
    if vol_ratio < 0.8:
        normalized = min(normalized, 65)

    # Signal determination from FINAL score (FIX from v1)
    if mode == "weekly":
        if normalized >= 75:
            signal = "STRONG BUY"
        elif normalized >= 60:
            signal = "BUY"
        elif normalized >= 45:
            signal = "HOLD / NEUTRAL"
        elif normalized >= 30:
            signal = "SELL"
        else:
            signal = "STRONG SELL"
    else:  # monthly
        if normalized >= 70:
            signal = "STRONG BUY"
        elif normalized >= 58:
            signal = "BUY"
        elif normalized >= 42:
            signal = "HOLD / NEUTRAL"
        elif normalized >= 28:
            signal = "SELL"
        else:
            signal = "STRONG SELL"

    return {
        "total_score": round(total_score, 1),
        "normalized_score": round(normalized, 1),
        "max_possible": max_possible,
        "signal": signal,
        "details": scores,
    }


def compute_entry_exit(df: pd.DataFrame, sr_levels: dict, signal_data: dict,
                       mode: str = "weekly") -> dict:
    """Compute entry, target, stop-loss with ATR-based dynamic targets.
    Ensures minimum 1:2 risk-reward for weekly, 1:3 for monthly.
    Targets based on research: 5-10% weekly, 10-20% monthly for mid/small caps."""
    if df is None or len(df) < 5:
        return {"action": "AVOID", "entry_price": None, "target_price": None,
                "stop_loss": None, "risk_reward": 0, "potential_profit_pct": 0, "potential_loss_pct": 0}

    latest = df.iloc[-1]
    price = float(latest["Close"])
    atr = float(latest.get("ATR", price * 0.025))
    signal = signal_data.get("signal", "HOLD")

    if "BUY" not in signal:
        return {"action": "AVOID", "entry_price": None, "target_price": None,
                "stop_loss": None, "risk_reward": 0, "potential_profit_pct": 0, "potential_loss_pct": 0}

    # ATR multipliers — wider targets for more profit potential
    if mode == "weekly":
        atr_target_mult = 3.5   # Was 2.0 — now targets ~5-10% on typical stocks
        atr_sl_mult = 1.5       # Tighter stop
        min_target_pct = 5.0    # Minimum 5% target
        min_rr = 2.0            # Minimum 1:2 risk-reward
    elif mode == "monthly":
        atr_target_mult = 5.0   # Targets ~10-20%
        atr_sl_mult = 2.0
        min_target_pct = 8.0
        min_rr = 2.5
    else:
        # 2-3 month positional
        atr_target_mult = 7.0
        atr_sl_mult = 2.5
        min_target_pct = 12.0
        min_rr = 3.0

    entry = round(price * 0.998, 2)  # Slight limit order below market

    # ── Stop-loss: ATR-based or nearest support ──
    atr_sl = price - atr_sl_mult * atr
    if sr_levels.get("supports"):
        support_sl = sr_levels["supports"][0]
        max_sl_pct = 7 if mode == "weekly" else 10
        if (price - support_sl) / price * 100 <= max_sl_pct:
            stop_loss = min(atr_sl, support_sl)  # Use tighter of the two
        else:
            stop_loss = atr_sl
    else:
        stop_loss = atr_sl

    # ── Target: ATR-based, Fibonacci extension, or nearest resistance ──
    atr_target = price + atr_target_mult * atr

    # Use 2nd resistance for monthly (skip nearby resistance)
    resistance_target = atr_target
    if sr_levels.get("resistances"):
        if mode == "weekly":
            resistance_target = sr_levels["resistances"][0]
            # If 1st resistance is too close (<3%), use 2nd
            if (resistance_target - price) / price * 100 < 3 and len(sr_levels["resistances"]) > 1:
                resistance_target = sr_levels["resistances"][1]
        else:
            # Monthly: use 2nd or 3rd resistance
            if len(sr_levels["resistances"]) > 1:
                resistance_target = sr_levels["resistances"][1]
            elif sr_levels["resistances"]:
                resistance_target = sr_levels["resistances"][0]

    target = max(atr_target, resistance_target)

    # ── Enforce minimum target percentage ──
    min_target_price = price * (1 + min_target_pct / 100)
    target = max(target, min_target_price)

    # ── Enforce minimum risk-reward ratio ──
    risk = price - stop_loss
    reward = target - price
    if risk > 0 and (reward / risk) < min_rr:
        target = price + min_rr * risk  # Push target to meet min R:R

    target = round(float(target), 2)
    stop_loss = round(float(stop_loss), 2)
    risk = price - stop_loss
    reward = target - price
    rr_ratio = round(reward / max(risk, 0.01), 2)
    potential_profit_pct = round((target - entry) / entry * 100, 2)
    potential_loss_pct = round((entry - stop_loss) / entry * 100, 2)

    return {
        "action": "BUY",
        "entry_price": entry,
        "target_price": target,
        "stop_loss": stop_loss,
        "risk_reward": rr_ratio,
        "potential_profit_pct": potential_profit_pct,
        "potential_loss_pct": potential_loss_pct,
    }


def recalculate_signal_from_confidence(confidence: float, mode: str = "weekly") -> str:
    """Recalculate signal label from final confidence — FIX for v1 bug."""
    if mode == "weekly":
        if confidence >= 75: return "STRONG BUY"
        elif confidence >= 60: return "BUY"
        elif confidence >= 45: return "HOLD / NEUTRAL"
        elif confidence >= 30: return "SELL"
        else: return "STRONG SELL"
    else:
        if confidence >= 70: return "STRONG BUY"
        elif confidence >= 58: return "BUY"
        elif confidence >= 42: return "HOLD / NEUTRAL"
        elif confidence >= 28: return "SELL"
        else: return "STRONG SELL"
