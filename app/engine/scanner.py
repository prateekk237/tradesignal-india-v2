"""
Market Scanner — Orchestrates the full analysis pipeline for all stocks.
Fetches data, computes indicators, scores signals, analyzes sentiment.
"""

import asyncio
import uuid
from datetime import datetime
import yfinance as yf
import pandas as pd
import structlog

from app.config import get_settings
from app.engine.stock_universe import STOCK_UNIVERSE
from app.engine.indicators import compute_all_indicators, find_support_resistance
from app.engine.scoring import compute_signal_scores, compute_entry_exit, recalculate_signal_from_confidence
from app.sentiment.analyzer import (
    fetch_news_from_rss, get_stock_sentiment, llm_analyze_stock
)

log = structlog.get_logger()
settings = get_settings()

# Cache for stock data
_data_cache = {}
_cache_timestamps = {}


def _safe_float(val, default=0.0) -> float:
    """Convert any value to a safe float — never NaN, never None."""
    if val is None:
        return default
    try:
        f = float(val)
        if pd.isna(f) or f != f:  # NaN check
            return default
        return round(f, 4)
    except (ValueError, TypeError):
        return default


def fetch_stock_data(ticker: str, period: str = "3mo") -> pd.DataFrame:
    """Fetch OHLCV data from Yahoo Finance with caching.
    Always returns clean data — no NaN, no incomplete rows.
    Works 24/7 including when market is closed."""
    import time
    cache_key = f"{ticker}_{period}"
    now = time.time()

    if cache_key in _data_cache and (now - _cache_timestamps.get(cache_key, 0)) < settings.YFINANCE_CACHE_TTL:
        return _data_cache[cache_key]

    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval="1d")
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # ── Professional data cleaning ──
        # Drop rows where Close is NaN (incomplete candles — market not open yet)
        df = df.dropna(subset=["Close"])
        # Drop rows where Close is 0 (bad data)
        df = df[df["Close"] > 0]
        # Forward-fill any remaining NaN in other columns (High, Low, Open, Volume)
        df = df.ffill()
        # Drop any rows still having NaN
        df = df.dropna()

        if df.empty or len(df) < 5:
            log.warning("insufficient_clean_data", ticker=ticker, rows=len(df))
            return None

        _data_cache[cache_key] = df
        _cache_timestamps[cache_key] = now
        return df
    except Exception as e:
        log.warning("fetch_stock_failed", ticker=ticker, error=str(e)[:150])
        return None


def fetch_nifty_data() -> pd.DataFrame:
    """Fetch Nifty 50 index data for relative strength calculation."""
    return fetch_stock_data("^NSEI", period="6mo")


def analyze_single_stock(ticker: str, stock_info: dict, news_articles: list,
                         nifty_df: pd.DataFrame = None,
                         mode: str = "weekly",
                         use_ai: bool = True) -> dict:
    """Run the complete 9-step analysis pipeline on a single stock."""
    name = stock_info.get("name", ticker)
    sector = stock_info.get("sector", "Unknown")
    cap = stock_info.get("cap", "Unknown")

    # 1. Fetch price data
    period = "3mo" if mode == "weekly" else "6mo"
    df = fetch_stock_data(ticker, period)
    if df is None or len(df) < 20:
        return None

    # 2. Compute all technical indicators (15 categories)
    df = compute_all_indicators(df, mode=mode)

    # 3. Support/Resistance levels
    sr_levels = find_support_resistance(df)

    # 4. Signal scoring (15 categories, 127-point model)
    signal_data = compute_signal_scores(df, sr_levels, mode=mode, nifty_df=nifty_df)

    # 5. Entry/Exit computation
    entry_exit = compute_entry_exit(df, sr_levels, signal_data, mode=mode)

    # 6. News sentiment (LLM-first → VADER → TextBlob)
    news_sentiment = get_stock_sentiment(ticker, name, sector, news_articles)

    # 7. News modifier
    news_modifier = news_sentiment.get("score_modifier", 0)

    # 8. Build stock data for AI analysis
    latest = df.iloc[-1]
    current_price = _safe_float(latest["Close"])

    # Safety: if price is still 0 after cleaning, use second-to-last row
    if current_price <= 0 and len(df) > 1:
        current_price = _safe_float(df.iloc[-2]["Close"])
    if current_price <= 0:
        log.warning("zero_price_after_cleaning", ticker=ticker)
        return None

    stock_data_for_ai = {
        "ticker": ticker, "name": name, "sector": sector, "cap": cap,
        "current_price": current_price,
        "rsi": _safe_float(latest.get("RSI_14", 50), 50),
        "macd_hist": _safe_float(latest.get("MACD_Hist", 0)),
        "bb_pct": _safe_float(latest.get("BB_Pct", 0.5), 0.5),
        "adx": _safe_float(latest.get("ADX", 20), 20),
        "vol_ratio": _safe_float(latest.get("Vol_Ratio", 1), 1),
        "supertrend_dir": int(_safe_float(latest.get("SuperTrend_Dir", 0))),
        "vs_sma10": "Above" if current_price > _safe_float(latest.get("SMA_10", current_price), current_price) else "Below",
        "vs_sma20": "Above" if current_price > _safe_float(latest.get("SMA_20", current_price), current_price) else "Below",
        "vs_sma50": "Above" if current_price > _safe_float(latest.get("SMA_50", current_price), current_price) else "Below",
        "daily_return": _safe_float(latest.get("Daily_Return", 0)),
        "weekly_return": _safe_float(latest.get("Weekly_Return", 0)),
        "monthly_return": _safe_float(latest.get("Monthly_Return", 0)),
        "supports": sr_levels["supports"][:3],
        "resistances": sr_levels["resistances"][:3],
        "signal_score": _safe_float(signal_data["normalized_score"]),
        "news_sentiment": news_sentiment.get("overall_sentiment", "N/A"),
    }

    # 9. AI Analysis (optional)
    ai_data = {"ai_analysis": "", "ai_confidence_modifier": 0}
    if use_ai and settings.NIM_API_KEY:
        ai_data = llm_analyze_stock(stock_data_for_ai)

    # 10. Final confidence with ALL modifiers
    base_confidence = _safe_float(signal_data["normalized_score"])
    news_mod = _safe_float(news_modifier)
    ai_mod = _safe_float(ai_data.get("ai_confidence_modifier", 0))
    final_confidence = max(0, min(100, base_confidence + news_mod + ai_mod))

    # 11. RECALCULATE signal from final confidence
    final_signal = recalculate_signal_from_confidence(final_confidence, mode)

    # 12. Sanitize entry_exit values
    if entry_exit:
        entry_exit = {
            k: (_safe_float(v, 0) if isinstance(v, (int, float)) else v)
            for k, v in entry_exit.items()
        }
        # Ensure prices are never 0 when we have a BUY signal
        if entry_exit.get("action") == "BUY":
            if not entry_exit.get("entry_price"):
                entry_exit["entry_price"] = round(current_price * 0.998, 2)
            if not entry_exit.get("target_price"):
                atr = _safe_float(latest.get("ATR", current_price * 0.03), current_price * 0.03)
                entry_exit["target_price"] = round(current_price + 3.5 * atr, 2)
            if not entry_exit.get("stop_loss"):
                atr = _safe_float(latest.get("ATR", current_price * 0.03), current_price * 0.03)
                entry_exit["stop_loss"] = round(current_price - 1.5 * atr, 2)

    return {
        "ticker": ticker,
        "name": name,
        "sector": sector,
        "cap": cap,
        "current_price": round(current_price, 2),
        "signal_data": signal_data,
        "sr_levels": sr_levels,
        "entry_exit": entry_exit,
        "news_sentiment": news_sentiment,
        "ai_data": ai_data,
        "base_confidence": round(base_confidence, 1),
        "news_modifier": round(news_mod, 1),
        "ai_modifier": round(ai_mod, 1),
        "final_confidence": round(final_confidence, 1),
        "final_signal": final_signal,
        "technical_details": stock_data_for_ai,
        "holding_mode": mode,
    }


def run_full_scan(scope: str = "all", sectors: list = None,
                  mode: str = "weekly", use_ai: bool = True,
                  progress_callback=None) -> dict:
    """
    Run full market scan across stock universe.
    Returns scan_id and list of results.
    """
    scan_id = str(uuid.uuid4())
    log.info("scan_started", scan_id=scan_id, scope=scope, mode=mode)

    # Filter universe
    universe = STOCK_UNIVERSE.copy()
    if scope == "large":
        universe = {k: v for k, v in universe.items() if v["cap"] == "Large"}
    elif scope == "mid":
        universe = {k: v for k, v in universe.items() if v["cap"] == "Mid"}
    elif scope == "small":
        universe = {k: v for k, v in universe.items() if v["cap"] == "Small"}
    elif scope == "sector" and sectors:
        universe = {k: v for k, v in universe.items() if v["sector"] in sectors}

    total = len(universe)

    # Fetch news once for all stocks
    log.info("fetching_news")
    news_articles = fetch_news_from_rss(max_articles=80)

    # Fetch Nifty data for relative strength
    nifty_df = fetch_nifty_data()

    # Scan all stocks
    results = []
    errors = 0

    for idx, (ticker, info) in enumerate(universe.items()):
        if progress_callback:
            progress_callback(idx + 1, total, f"Analyzing {info['name']}")

        try:
            result = analyze_single_stock(
                ticker, info, news_articles,
                nifty_df=nifty_df,
                mode=mode,
                use_ai=use_ai
            )
            if result:
                results.append(result)
        except Exception as e:
            errors += 1
            log.warning("stock_analysis_error", ticker=ticker, error=str(e))

        # Rate limiting
        if idx % settings.SCAN_BATCH_SIZE == 0 and idx > 0:
            import time
            time.sleep(settings.SCAN_RATE_LIMIT_PAUSE)

    # Sort by confidence descending
    results.sort(key=lambda x: x["final_confidence"], reverse=True)

    log.info("scan_complete", scan_id=scan_id, total=total,
             analyzed=len(results), errors=errors)

    return {
        "scan_id": scan_id,
        "scan_date": datetime.utcnow().isoformat(),
        "mode": mode,
        "scope": scope,
        "total_stocks": total,
        "analyzed": len(results),
        "errors": errors,
        "results": results,
        "buy_signals": [r for r in results if "BUY" in r["final_signal"]],
        "news_articles_fetched": len(news_articles),
    }
