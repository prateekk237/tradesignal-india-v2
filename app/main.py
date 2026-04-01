"""
TradeSignal India v2 — FastAPI Main Application.
Full-stack API for stock scanning, trade tracking, news sentiment, and Telegram alerts.
"""

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional
import structlog

from app.config import get_settings
from app.database import engine, Base, get_db, AsyncSessionLocal
from app.schemas import (
    ScanRequest, ScanSummaryOut, ScanResultOut,
    TradeCreate, TradeOut, PortfolioAllocRequest,
    SettingsUpdate, HealthOut, StockOut,
)
from app.engine.scanner import run_full_scan
from app.engine.stock_universe import STOCK_UNIVERSE, SECTORS
from app.engine.stock_universe import resolve_ticker as _resolve_ticker
from app.sentiment.analyzer import fetch_news_from_rss, analyze_sentiment
from app.models import Stock, ScanResult, Trade, NewsArticle, Alert

from app.routers.trades import router as trades_router

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()
settings = get_settings()

# WebSocket connections for live updates
from fastapi import WebSocket, WebSocketDisconnect
_ws_connections: list[WebSocket] = []

# ═══════════════════════════════════════════════════════════════════════════
#  APP SETUP
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="TradeSignal India v2 API",
    version="2.0.0",
    description="AI-Powered Weekly/Monthly Equity Signal System for NSE",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(trades_router)


@app.on_event("startup")
async def startup():
    """Create database tables on startup. Graceful if DB unavailable."""
    try:
        if engine is None:
            log.warning("database_not_configured", hint="Add PostgreSQL on Railway and set DATABASE_URL")
        else:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("database_tables_created")

            # Seed stock universe if empty
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(func.count(Stock.id)))
                count = result.scalar()
                if count == 0:
                    log.info("seeding_stock_universe", count=len(STOCK_UNIVERSE))
                    for ticker, info in STOCK_UNIVERSE.items():
                        session.add(Stock(
                            ticker=ticker,
                            name=info["name"],
                            sector=info["sector"],
                            cap=info["cap"],
                        ))
                    await session.commit()
                    log.info("stock_universe_seeded")
    except Exception as e:
        log.warning("database_startup_failed", error=str(e),
                    hint="DB features disabled. Start PostgreSQL or set DATABASE_URL.")

    # Start Telegram bot (non-blocking)
    try:
        from app.integrations.telegram_commands import create_bot_application
        bot_app = create_bot_application()
        if bot_app:
            import asyncio
            asyncio.create_task(_run_telegram_bot(bot_app))
            log.info("telegram_bot_started")
    except Exception as e:
        log.warning("telegram_bot_start_failed", error=str(e))

    # Start auto-scheduler (Monday-Friday morning scans + Telegram alerts)
    try:
        from app.tasks.auto_scheduler import start_auto_scheduler
        start_auto_scheduler()
        log.info("auto_scheduler_started")
    except Exception as e:
        log.warning("auto_scheduler_start_failed", error=str(e))


async def _run_telegram_bot(bot_app):
    """Run Telegram bot polling in background."""
    try:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
    except Exception as e:
        log.warning("telegram_polling_error", error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthOut)
async def health():
    return HealthOut(
        status="ok",
        version="2.0.0",
        timestamp=datetime.utcnow().isoformat(),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  STOCKS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/stocks", response_model=list[StockOut])
async def list_stocks(
    cap: Optional[str] = None,
    sector: Optional[str] = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """List all stocks with optional filters."""
    query = select(Stock)
    if active_only:
        query = query.where(Stock.is_active == True)
    if cap:
        query = query.where(Stock.cap == cap)
    if sector:
        query = query.where(Stock.sector == sector)
    query = query.order_by(Stock.cap, Stock.sector, Stock.name)

    result = await db.execute(query)
    return result.scalars().all()


@app.get("/api/stocks/sectors")
async def list_sectors():
    """List all available sectors."""
    return {"sectors": SECTORS}


# ═══════════════════════════════════════════════════════════════════════════
#  SCANS
# ═══════════════════════════════════════════════════════════════════════════

# In-memory scan storage
_active_scans = {}
_scan_progress = {}  # {scan_id: {current, total, stock, status, percent}}

import threading


@app.post("/api/scans")
async def trigger_scan(request: ScanRequest):
    """Trigger a new market scan in background. Returns scan_id immediately."""
    import uuid
    scan_id = str(uuid.uuid4())

    _scan_progress[scan_id] = {
        "scan_id": scan_id,
        "status": "running",
        "current": 0,
        "total": 0,
        "stock": "Initializing...",
        "percent": 0,
        "results_so_far": 0,
    }

    def run_in_thread():
        def progress_cb(current, total, stock_name):
            _scan_progress[scan_id] = {
                "scan_id": scan_id,
                "status": "running",
                "current": current,
                "total": total,
                "stock": stock_name,
                "percent": round((current / total) * 100) if total > 0 else 0,
                "results_so_far": len(_active_scans.get(scan_id, {}).get("results", [])),
            }

        try:
            result = run_full_scan(
                scope=request.scope,
                sectors=request.sectors,
                mode=request.mode,
                use_ai=request.use_ai,
                progress_callback=progress_cb,
            )
            _active_scans[scan_id] = result
            _scan_progress[scan_id] = {
                "scan_id": scan_id,
                "status": "complete",
                "current": result["analyzed"],
                "total": result["total_stocks"],
                "stock": "Done",
                "percent": 100,
                "results_so_far": len(result["results"]),
                "buy_signals_count": len(result["buy_signals"]),
            }
        except Exception as e:
            _scan_progress[scan_id] = {
                "scan_id": scan_id,
                "status": "error",
                "error": str(e),
                "current": 0, "total": 0, "stock": "", "percent": 0, "results_so_far": 0,
            }

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    return {"scan_id": scan_id, "status": "started", "message": "Scan running in background"}


@app.get("/api/scans/progress/{scan_id}")
async def get_scan_progress(scan_id: str):
    """Get real-time progress of a running scan."""
    if scan_id in _scan_progress:
        return _scan_progress[scan_id]
    all_scans = _get_all_scans()
    if scan_id in all_scans:
        scan = all_scans[scan_id]
        return {"scan_id": scan_id, "status": "complete", "percent": 100,
                "current": scan.get("analyzed", 0), "total": scan.get("total_stocks", 0),
                "stock": "Done", "results_so_far": len(scan.get("results", []))}
    return {"scan_id": scan_id, "status": "not_found"}


@app.get("/api/auto-scan/status")
async def get_auto_scan_status():
    """Get auto-scheduler status: next scan time, last scan results."""
    from app.tasks.auto_scheduler import auto_scan_status, auto_scan_results
    result = {**auto_scan_status}
    result["scheduled_scans"] = [
        {"time": "10:30 AM IST", "days": "Mon-Fri", "scope": "All stocks", "ai": True},
        {"time": "1:00 PM IST", "days": "Wednesday", "scope": "All stocks (mid-week)", "ai": True},
        {"time": "3:00 PM IST", "days": "Friday", "scope": "Large Cap watchlist", "ai": False},
        {"time": "6:00 PM IST", "days": "Sunday", "scope": "Weekly preview", "ai": True},
    ]
    return result


def _get_all_scans() -> dict:
    """Merge manual scans + auto-scans into one dict."""
    from app.tasks.auto_scheduler import auto_scan_results
    merged = {**_active_scans}
    merged.update(auto_scan_results)
    return merged


@app.get("/api/scans/{scan_id}")
async def get_scan_results(scan_id: str, min_confidence: float = 0):
    """Get full scan results by scan_id."""
    all_scans = _get_all_scans()
    if scan_id not in all_scans:
        raise HTTPException(status_code=404, detail="Scan not found")

    scan = all_scans[scan_id]
    results = scan["results"]

    if min_confidence > 0:
        results = [r for r in results if r["final_confidence"] >= min_confidence]

    return {
        "scan_id": scan_id,
        "scan_date": scan["scan_date"],
        "mode": scan["mode"],
        "total": len(results),
        "results": [
            {
                "ticker": r["ticker"],
                "name": r["name"],
                "sector": r["sector"],
                "cap": r["cap"],
                "current_price": r["current_price"],
                "final_confidence": r["final_confidence"],
                "final_signal": r["final_signal"],
                "base_confidence": r["base_confidence"],
                "news_modifier": r["news_modifier"],
                "ai_modifier": r["ai_modifier"],
                "entry_exit": r["entry_exit"],
                "sr_levels": r["sr_levels"],
                "indicator_scores": r["signal_data"]["details"],
                "news_sentiment": {
                    "sentiment": r["news_sentiment"].get("overall_sentiment"),
                    "score": r["news_sentiment"].get("sentiment_score"),
                    "impact": r["news_sentiment"].get("impact_level"),
                    "source": r["news_sentiment"].get("source"),
                    "article_count": r["news_sentiment"].get("article_count", 0),
                },
                "ai_data": r["ai_data"],
                "holding_mode": r["holding_mode"],
                "technical_details": r["technical_details"],
            }
            for r in results
        ],
    }


@app.get("/api/scans/{scan_id}/signals")
async def get_buy_signals(scan_id: str, min_confidence: float = 65):
    """Get only BUY signals from a scan."""
    all_scans = _get_all_scans()
    if scan_id not in all_scans:
        raise HTTPException(status_code=404, detail="Scan not found")

    scan = all_scans[scan_id]
    signals = [r for r in scan["results"]
               if "BUY" in r["final_signal"] and r["final_confidence"] >= min_confidence]

    return {
        "scan_id": scan_id,
        "count": len(signals),
        "min_confidence": min_confidence,
        "signals": [
            {
                "ticker": r["ticker"],
                "name": r["name"],
                "sector": r["sector"],
                "cap": r["cap"],
                "current_price": r["current_price"],
                "final_confidence": r["final_confidence"],
                "final_signal": r["final_signal"],
                "entry_price": r["entry_exit"].get("entry_price"),
                "target_price": r["entry_exit"].get("target_price"),
                "stop_loss": r["entry_exit"].get("stop_loss"),
                "risk_reward": r["entry_exit"].get("risk_reward"),
                "potential_profit_pct": r["entry_exit"].get("potential_profit_pct"),
                "potential_loss_pct": r["entry_exit"].get("potential_loss_pct"),
                "news_sentiment": r["news_sentiment"].get("overall_sentiment"),
                "ai_analysis": r["ai_data"].get("ai_analysis", ""),
            }
            for r in signals
        ],
    }


@app.get("/api/scans/latest/summary")
async def get_latest_scan_summary():
    """Get the most recent scan summary."""
    all_scans = _get_all_scans()
    if not all_scans:
        return {"message": "No scans available. Trigger a scan first."}

    try:
        latest_id = max(all_scans.keys(), key=lambda k: all_scans[k].get("scan_date", ""))
    except (KeyError, ValueError):
        return {"message": "No valid scans available."}

    scan = all_scans[latest_id]

    buy_signals = [r for r in scan["results"] if "BUY" in r["final_signal"]]
    return {
        "scan_id": latest_id,
        "scan_date": scan["scan_date"],
        "mode": scan["mode"],
        "total_analyzed": scan["analyzed"],
        "buy_signals": len(buy_signals),
        "avg_confidence": round(
            sum(r["final_confidence"] for r in buy_signals) / len(buy_signals), 1
        ) if buy_signals else 0,
        "top_5": [
            {"ticker": r["ticker"], "name": r["name"],
             "confidence": r["final_confidence"], "signal": r["final_signal"]}
            for r in buy_signals[:5]
        ],
        "sector_distribution": _sector_dist(buy_signals),
    }


def _sector_dist(results: list) -> dict:
    dist = {}
    for r in results:
        s = r["sector"]
        dist[s] = dist.get(s, 0) + 1
    return dict(sorted(dist.items(), key=lambda x: -x[1]))


# ═══════════════════════════════════════════════════════════════════════════
#  NEWS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/news")
async def get_news(limit: int = 50):
    """Fetch latest market news with per-article sentiment + stock impact."""
    from app.sentiment.analyzer import vader_sentiment, classify_news_impact
    articles = fetch_news_from_rss(max_articles=limit)

    # Stock name lookup for impact matching
    stock_keywords = {}
    for ticker, info in STOCK_UNIVERSE.items():
        short = ticker.replace(".NS", "").lower()
        stock_keywords[short] = {"ticker": ticker, "name": info["name"], "sector": info["sector"]}
        for word in info["name"].lower().split():
            if len(word) > 4 and word not in {"limited", "india", "industries", "corp", "company", "ltd"}:
                stock_keywords[word] = {"ticker": ticker, "name": info["name"], "sector": info["sector"]}

    for article in articles:
        title = article.get("title", "")
        summary = article.get("summary", "")[:200]
        text = (title + " " + summary).lower()

        # Sentiment
        sent = vader_sentiment(title + " " + summary)
        article["sentiment_score"] = sent["sentiment_score"]
        article["sentiment_label"] = sent["overall_sentiment"]

        # Impact level
        article["impact_level"] = classify_news_impact(title, summary)

        # Match affected stocks
        affected = []
        for kw, stock_info in stock_keywords.items():
            if kw in text and stock_info["ticker"] not in [a.get("ticker") for a in affected]:
                direction = "UP" if sent["sentiment_score"] > 0.05 else "DOWN" if sent["sentiment_score"] < -0.05 else "NEUTRAL"
                affected.append({
                    "ticker": stock_info["ticker"].replace(".NS", ""),
                    "name": stock_info["name"],
                    "direction": direction,
                })
        article["affected_stocks"] = affected[:5]

    return {
        "count": len(articles),
        "articles": articles,
    }


@app.get("/api/news/sentiment")
async def get_market_sentiment():
    """Get overall market sentiment from latest news."""
    articles = fetch_news_from_rss(max_articles=50)
    headlines = [a["title"] for a in articles if a.get("title")]
    sentiment = analyze_sentiment(headlines)
    return {
        "market_sentiment": sentiment,
        "article_count": len(articles),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  PORTFOLIO
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/portfolio/allocate")
async def allocate_portfolio(request: PortfolioAllocRequest):
    """Compute portfolio allocation for given capital and candidates."""
    candidates = request.candidates
    capital = request.capital

    if not candidates:
        return {"allocations": [], "total_invested": 0, "cash_reserve": capital}

    # Filter and sort
    qualified = [c for c in candidates
                 if c.get("final_confidence", 0) >= request.min_confidence
                 and "BUY" in c.get("final_signal", "")]
    qualified.sort(key=lambda x: x.get("final_confidence", 0), reverse=True)
    top = qualified[:request.max_positions]

    if not top:
        return {"allocations": [], "total_invested": 0, "cash_reserve": capital}

    # Confidence-weighted allocation with 40% cap
    total_conf = sum(c["final_confidence"] for c in top)
    allocations = []

    for c in top:
        pct = (c["final_confidence"] / total_conf) * 100 if total_conf > 0 else 100 / len(top)
        pct = min(pct, 40)
        amount = capital * pct / 100
        price = c.get("current_price", 1)
        shares = int(amount / price) if price > 0 else 0

        allocations.append({
            "ticker": c["ticker"],
            "name": c["name"],
            "price": price,
            "confidence": c["final_confidence"],
            "allocation_pct": round(pct, 1),
            "amount": round(amount, 2),
            "shares": shares,
            "target": c.get("entry_exit", {}).get("target_price"),
            "stop_loss": c.get("entry_exit", {}).get("stop_loss"),
        })

    total_invested = sum(a["amount"] for a in allocations)

    return {
        "allocations": allocations,
        "total_invested": round(total_invested, 2),
        "cash_reserve": round(capital - total_invested, 2),
        "positions": len(allocations),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/scan/stock/{ticker_query}")
async def scan_single_stock(ticker_query: str, use_ai: bool = True):
    """Smart single stock scan — auto-analyzes ALL timeframes and recommends best holding period."""
    from app.engine.scanner import analyze_single_stock, fetch_stock_data, fetch_nifty_data, _safe_float
    from app.sentiment.analyzer import fetch_news_from_rss

    ticker = _resolve_ticker(ticker_query)
    if not ticker:
        raise HTTPException(status_code=404, detail=f"Stock '{ticker_query}' not found. Try: RELIANCE, SUZLON, SBI, NALCO, RTN")

    info = STOCK_UNIVERSE[ticker]

    try:
        test_df = fetch_stock_data(ticker, period="1mo")
        if test_df is None or len(test_df) < 10:
            raise HTTPException(status_code=422, detail=f"{ticker.replace('.NS','')} has insufficient data ({len(test_df) if test_df is not None else 0} days).")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot fetch {ticker.replace('.NS','')}: {str(e)[:150]}")

    try:
        news_articles = fetch_news_from_rss(max_articles=30)
        nifty_df = fetch_nifty_data()

        # ── Analyze BOTH timeframes ──
        weekly_result = analyze_single_stock(ticker, info, news_articles, nifty_df=nifty_df, mode="weekly", use_ai=use_ai)
        monthly_result = analyze_single_stock(ticker, info, news_articles, nifty_df=nifty_df, mode="monthly", use_ai=False)

        if not weekly_result and not monthly_result:
            raise HTTPException(status_code=422, detail=f"Analysis returned no results for {ticker.replace('.NS','')}.")

        best = weekly_result or monthly_result
        weekly_conf = _safe_float(weekly_result["final_confidence"]) if weekly_result else 0
        monthly_conf = _safe_float(monthly_result["final_confidence"]) if monthly_result else 0

        # ── Smart holding recommendation ──
        price = _safe_float(best["current_price"])
        df_6m = fetch_stock_data(ticker, period="6mo")
        trend_score = 0
        if df_6m is not None and len(df_6m) >= 50:
            sma50 = df_6m["Close"].rolling(50).mean().iloc[-1]
            sma20 = df_6m["Close"].rolling(20).mean().iloc[-1]
            sma200 = df_6m["Close"].rolling(200).mean().iloc[-1] if len(df_6m) >= 200 else sma50
            if price > _safe_float(sma20): trend_score += 1
            if price > _safe_float(sma50): trend_score += 1
            if _safe_float(sma20) > _safe_float(sma50): trend_score += 1
            if price > _safe_float(sma200): trend_score += 1
            # Monthly return momentum
            monthly_ret = _safe_float((price / _safe_float(df_6m["Close"].iloc[-21], price) - 1) * 100) if len(df_6m) > 21 else 0
            three_month_ret = _safe_float((price / _safe_float(df_6m["Close"].iloc[-63], price) - 1) * 100) if len(df_6m) > 63 else 0

        # Determine best holding period
        if weekly_conf >= 70 and monthly_conf >= 65 and trend_score >= 3:
            recommended_hold = "2-4 weeks"
            hold_reason = "Strong short-term momentum + positive longer trend"
        elif monthly_conf >= 65 and trend_score >= 3:
            recommended_hold = "1-2 months"
            hold_reason = "Monthly signals stronger, uptrend intact"
        elif trend_score >= 4 and monthly_conf >= 55:
            recommended_hold = "3-6 months"
            hold_reason = "Strong long-term uptrend (above all MAs)"
        elif weekly_conf >= 65:
            recommended_hold = "1-2 weeks"
            hold_reason = "Short-term setup only, no long-term trend support"
        elif monthly_conf >= 60:
            recommended_hold = "2-4 weeks"
            hold_reason = "Moderate monthly signal"
        else:
            recommended_hold = "WAIT — no clear entry"
            hold_reason = "Weak signals across all timeframes"

        use_result = monthly_result if monthly_conf > weekly_conf else weekly_result
        if not use_result:
            use_result = best

        return {
            "ticker": best["ticker"],
            "name": best["name"],
            "sector": best["sector"],
            "cap": best["cap"],
            "current_price": best["current_price"],
            # Best timeframe result
            "final_confidence": use_result["final_confidence"],
            "final_signal": use_result["final_signal"],
            "base_confidence": use_result["base_confidence"],
            "news_modifier": use_result["news_modifier"],
            "ai_modifier": use_result["ai_modifier"],
            "entry_exit": use_result["entry_exit"],
            "sr_levels": use_result["sr_levels"],
            "indicator_scores": use_result["signal_data"]["details"],
            "news_sentiment": use_result["news_sentiment"],
            "ai_data": use_result["ai_data"],
            "holding_mode": use_result["holding_mode"],
            "technical_details": use_result["technical_details"],
            # ── Smart recommendation ──
            "recommendation": {
                "hold_duration": recommended_hold,
                "reason": hold_reason,
                "weekly_confidence": round(weekly_conf, 1),
                "weekly_signal": weekly_result["final_signal"] if weekly_result else "N/A",
                "monthly_confidence": round(monthly_conf, 1),
                "monthly_signal": monthly_result["final_signal"] if monthly_result else "N/A",
                "trend_score": trend_score,
                "trend_label": "Strong ↑" if trend_score >= 3 else "Moderate →" if trend_score >= 2 else "Weak ↓",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        log.warning("single_stock_scan_error", ticker=ticker, error=str(e)[:200])
        raise HTTPException(status_code=500, detail=f"Scan failed for {ticker.replace('.NS','')}: {str(e)[:200]}")


@app.get("/api/budget-picks")
async def get_budget_picks(
    budget: float = 20000,
    mode: str = "weekly",
    max_price: float = 500,
):
    """Get stock recommendations for a specific budget (₹15K-₹20K).
    Filters by max stock price and suggests allocation."""
    all_scans = _get_all_scans()
    if not all_scans:
        return {"message": "No scan data. Run a scan first.", "picks": []}

    try:
        latest_id = max(all_scans.keys(), key=lambda k: all_scans[k].get("scan_date", ""))
    except (KeyError, ValueError):
        return {"message": "No valid scans.", "picks": []}

    scan = all_scans[latest_id]
    results = scan.get("results", [])

    # Filter: BUY signals under max_price
    affordable = [
        r for r in results
        if "BUY" in r.get("final_signal", "")
        and r.get("current_price", 99999) <= max_price
        and r.get("final_confidence", 0) >= 55
    ]
    affordable.sort(key=lambda x: x["final_confidence"], reverse=True)

    picks = []
    remaining = budget
    for r in affordable[:5]:
        price = r["current_price"]
        entry = r.get("entry_exit", {})
        target = entry.get("target_price", price * 1.08)
        sl = entry.get("stop_loss", price * 0.95)

        # Max 40% of budget per stock, max 2-3 stocks
        alloc = min(remaining, budget * 0.40)
        shares = int(alloc / price) if price > 0 else 0
        if shares < 1:
            continue
        amount = round(shares * price, 2)
        remaining -= amount

        profit_pct = round((target - price) / price * 100, 1) if target else 0
        loss_pct = round((price - sl) / price * 100, 1) if sl else 0

        picks.append({
            "ticker": r["ticker"].replace(".NS", ""),
            "name": r["name"],
            "sector": r["sector"],
            "price": price,
            "confidence": r["final_confidence"],
            "signal": r["final_signal"],
            "shares": shares,
            "amount": amount,
            "target": round(target, 2) if target else None,
            "stop_loss": round(sl, 2) if sl else None,
            "expected_profit_pct": profit_pct,
            "risk_pct": loss_pct,
            "holding": mode,
        })

        if len(picks) >= 3 or remaining < 1000:
            break

    return {
        "budget": budget,
        "max_price_filter": max_price,
        "mode": mode,
        "total_invested": round(budget - remaining, 2),
        "cash_reserve": round(remaining, 2),
        "picks": picks,
        "scan_date": scan.get("scan_date", ""),
    }


@app.get("/api/settings")
async def get_app_settings():
    return {
        "nim_api_configured": bool(settings.NIM_API_KEY),
        "nim_model": settings.NIM_MODEL,
        "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "default_capital": settings.DEFAULT_CAPITAL,
        "default_min_confidence": settings.DEFAULT_MIN_CONFIDENCE,
        "default_max_positions": settings.DEFAULT_MAX_POSITIONS,
        "sectors": SECTORS,
        "total_stocks": len(STOCK_UNIVERSE),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  WEBSOCKET — Live updates
# ═══════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/updates")
async def websocket_updates(websocket: WebSocket):
    """WebSocket for live scan progress and price updates."""
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming commands from client if needed
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)


async def broadcast_ws(message: dict):
    """Broadcast a message to all connected WebSocket clients."""
    import json
    text = json.dumps(message)
    disconnected = []
    for ws in _ws_connections:
        try:
            await ws.send_text(text)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _ws_connections.remove(ws)


# ═══════════════════════════════════════════════════════════════════════════
#  SERVE REACT FRONTEND (static files from same server)
#  Uses exception handler — does NOT interfere with API routes
# ═══════════════════════════════════════════════════════════════════════════

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

if os.path.exists(STATIC_DIR):
    # Serve JS/CSS/assets at /assets path
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    # Root route → serve index.html
    @app.get("/", response_class=FileResponse)
    async def serve_index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    # Favicon
    @app.get("/vite.svg", response_class=FileResponse)
    async def serve_favicon():
        return FileResponse(os.path.join(STATIC_DIR, "vite.svg"))

    # SPA catch-all: use 404 handler to serve index.html for frontend routes
    # This way API routes (/api/*, /health, /docs) work normally
    # Only unmatched routes (like /scan, /news, /portfolio) get index.html
    @app.exception_handler(404)
    async def spa_fallback(request, exc):
        path = request.url.path
        # Don't serve SPA for API/docs/health routes — return normal 404
        if path.startswith(("/api/", "/docs", "/redoc", "/openapi.json", "/ws/", "/health")):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        # Serve index.html for all other routes (SPA client-side routing)
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

else:
    @app.get("/")
    async def root():
        return {"message": "TradeSignal India v2 API", "docs": "/docs", "health": "/health"}
