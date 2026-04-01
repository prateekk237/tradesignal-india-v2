"""
Telegram Bot Command Handler — Runs as an async long-polling bot.
Commands: /start, /help, /news, /signals, /status, /portfolio, /scan, /stock, /alerts
"""

import asyncio
import structlog
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import get_settings
from app.sentiment.analyzer import fetch_news_from_rss, analyze_sentiment, classify_news_impact
from app.engine.stock_universe import STOCK_UNIVERSE

log = structlog.get_logger()
settings = get_settings()


def create_bot_application() -> Application | None:
    """Create the Telegram bot application."""
    if not settings.TELEGRAM_BOT_TOKEN:
        log.warning("telegram_bot_token_not_set")
        return None

    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("hindinews", cmd_hindinews))
    app.add_handler(CommandHandler("sentiment", cmd_sentiment))
    app.add_handler(CommandHandler("signals", cmd_signals))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("scanstock", cmd_scanstock))
    app.add_handler(CommandHandler("sectors", cmd_sectors))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("autoscan", cmd_autoscan))
    app.add_handler(CommandHandler("budgetpicks", cmd_budgetpicks))

    return app


# ═══════════════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📊 <b>TradeSignal India v2.0</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "AI-Powered Equity Signal System for NSE\n"
        "15 indicators · LLM sentiment · 130 stocks\n\n"
        "Use /help to see all commands."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 <b>Available Commands</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "📰 /news — Latest market headlines\n"
        "🇮🇳 /hindinews — बाज़ार समाचार हिंदी में\n"
        "🧠 /sentiment — AI market sentiment analysis\n"
        "🎯 /signals — Latest BUY signals from scan\n"
        "📊 /status — Open positions & P&L\n"
        "💼 /portfolio — Current allocation\n"
        "🔍 /stock RELIANCE — Quick stock lookup\n"
        "🎯 /scanstock RELIANCE — Scan single stock (with target)\n"
        "💰 /budgetpicks 15000 — Best picks for your budget\n"
        "🚀 /scan — Trigger full market scan\n"
        "⏰ /autoscan — Auto-scan schedule & status\n"
        "📈 /sectors — Sector breakdown\n"
        "🔔 /alerts on|off — Toggle notifications\n"
        "❓ /help — This message\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch and show latest market news with sentiment and stock impact."""
    await update.message.reply_text("📰 Fetching latest news with analysis...", parse_mode="HTML")

    try:
        articles = fetch_news_from_rss(max_articles=30)
        if not articles:
            await update.message.reply_text("No news available right now.")
            return

        from app.sentiment.analyzer import vader_sentiment, classify_news_impact

        lines = ["📰 <b>Market Headlines + Impact</b>\n━━━━━━━━━━━━━━━━\n"]
        for a in articles[:10]:
            source = a.get("source", "")
            title = a.get("title", "")[:120]
            link = a.get("link", "")
            summary = a.get("summary", "")[:200]

            # Sentiment analysis per headline
            sent = vader_sentiment(title + " " + summary)
            impact = classify_news_impact(title, summary)

            if "BULL" in sent["overall_sentiment"]:
                arrow = "📈"
            elif "BEAR" in sent["overall_sentiment"]:
                arrow = "📉"
            else:
                arrow = "➡️"

            impact_badge = "🔴" if impact == "HIGH" else "🟡" if impact == "MEDIUM" else ""

            lines.append(
                f"{arrow}{impact_badge} <a href='{link}'>{title}</a>\n"
                f"   <i>{source} | {sent['overall_sentiment']}</i>\n"
            )

        lines.append("\n🇮🇳 /hindinews — हिंदी + विश्लेषण में देखें")

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")


async def cmd_hindinews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch news and translate to Hindi with stock impact analysis using LLM."""
    await update.message.reply_text("🇮🇳 बाज़ार समाचार और विश्लेषण लोड हो रहा है...", parse_mode="HTML")

    try:
        articles = fetch_news_from_rss(max_articles=30)
        if not articles:
            await update.message.reply_text("अभी कोई समाचार उपलब्ध नहीं है।")
            return

        headlines = [a.get("title", "")[:120] for a in articles[:6] if a.get("title")]
        sources = [a.get("source", "") for a in articles[:6]]
        links = [a.get("link", "") for a in articles[:6]]

        if not headlines:
            await update.message.reply_text("समाचार फीड से कोई हेडलाइन नहीं मिली।")
            return

        from app.config import get_settings
        from openai import OpenAI

        settings = get_settings()
        if not settings.NIM_API_KEY:
            # No LLM — show English with Hindi header
            lines = ["📰 <b>ताज़ा बाज़ार समाचार</b>\n(LLM API नहीं है — अंग्रेज़ी में)\n━━━━━━━━━━━━━━━━\n"]
            from app.sentiment.analyzer import vader_sentiment
            for i, h in enumerate(headlines[:8]):
                sent = vader_sentiment(h)
                arrow = "📈" if "BULL" in sent["overall_sentiment"] else "📉" if "BEAR" in sent["overall_sentiment"] else "➡️"
                lines.append(f"{arrow} <a href='{links[i]}'>{h}</a>\n   <i>{sources[i]}</i>\n")
            await update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
            return

        headlines_text = "\n".join([f"{i+1}. {h} [{sources[i]}]" for i, h in enumerate(headlines[:8])])

        client = OpenAI(base_url=settings.NIM_BASE_URL, api_key=settings.NIM_API_KEY, timeout=30)

        try:
            completion = client.chat.completions.create(
                model=settings.NIM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "भारतीय बाज़ार हेडलाइन्स का हिंदी अनुवाद + असर बताओ। "
                            "फॉर्मेट: 📈/📉/➡️ [हिंदी] | असर: [शेयर/सेक्टर]. "
                            "Nifty, Sensex, FII, कंपनी नाम अंग्रेज़ी में रखो। छोटा लिखो।"
                        )
                    },
                    {
                        "role": "user",
                        "content": f"इन हेडलाइन्स का हिंदी अनुवाद + शेयर असर बताओ:\n\n{headlines_text}"
                    }
                ],
                temperature=0.3,
                max_tokens=1200,
            )

            hindi_text = completion.choices[0].message.content.strip()

            msg = (
                "🇮🇳 <b>ताज़ा बाज़ार समाचार — हिंदी + विश्लेषण</b>\n"
                "━━━━━━━━━━━━━━━━\n\n"
                f"{hindi_text}\n\n"
                "━━━━━━━━━━━━━━━━\n"
            )

            for i, link in enumerate(links[:8]):
                if link:
                    msg += f"🔗 <a href='{link}'>{sources[i]}</a>\n"

            msg += "\n📰 /news — English में देखें"

            # Telegram has 4096 char limit
            if len(msg) > 4000:
                msg = msg[:3950] + "\n\n... (और समाचार /news में देखें)"

            await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)

        except Exception as e:
            error_str = str(e)
            log.warning("hindi_translation_error", error=error_str[:200])

            # Fallback: English with VADER sentiment arrows + stock impact
            from app.sentiment.analyzer import vader_sentiment
            lines = [
                "📰 <b>ताज़ा बाज़ार समाचार</b>\n"
                "(अनुवाद में समस्या — अंग्रेज़ी + विश्लेषण)\n"
                "━━━━━━━━━━━━━━━━\n"
            ]
            for i, h in enumerate(headlines[:8]):
                sent = vader_sentiment(h)
                arrow = "📈" if "BULL" in sent["overall_sentiment"] else "📉" if "BEAR" in sent["overall_sentiment"] else "➡️"
                lines.append(f"{arrow} <a href='{links[i]}'>{h}</a>\n   <i>{sources[i]} | {sent['overall_sentiment']}</i>\n")
            await update.message.reply_text(
                "\n".join(lines), parse_mode="HTML", disable_web_page_preview=True
            )

    except Exception as e:
        await update.message.reply_text(f"❌ त्रुटि: {str(e)[:200]}")


async def cmd_sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run full LLM → VADER → TextBlob sentiment pipeline."""
    await update.message.reply_text("🧠 Analyzing market sentiment (LLM first)...", parse_mode="HTML")

    try:
        articles = fetch_news_from_rss(max_articles=50)
        headlines = [a["title"] for a in articles if a.get("title")]
        result = analyze_sentiment(headlines)

        score = result.get("sentiment_score", 0)
        sentiment = result.get("overall_sentiment", "NEUTRAL")
        source = result.get("source", "?")
        modifier = result.get("score_modifier", 0)

        emoji = "🟢" if score > 0.1 else "🔴" if score < -0.1 else "🟡"

        text = (
            f"🧠 <b>Market Sentiment Analysis</b>\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"{emoji} <b>{sentiment.replace('_', ' ')}</b>\n"
            f"Score: <code>{score:+.3f}</code>\n"
            f"Engine: <b>{source.upper()}</b>"
            f"{' (LLaMA 3.3 70B)' if source == 'llm' else ''}\n"
            f"Modifier: <code>{modifier:+d} pts</code>\n"
            f"Articles: {len(headlines)}\n"
        )

        if result.get("key_themes"):
            text += f"\nThemes: {', '.join(result['key_themes'][:3])}\n"

        if result.get("reasoning"):
            text += f"\n💡 {result['reasoning'][:300]}\n"

        if result.get("trading_action"):
            text += f"\n📋 Action: <b>{result['trading_action']}</b>\n"

        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")


async def cmd_signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show latest scan BUY signals (from in-memory cache)."""
    try:
        from app.main import _active_scans
        from app.tasks.auto_scheduler import auto_scan_results
        all_scans = {**_active_scans, **auto_scan_results}

        if not all_scans:
            await update.message.reply_text(
                "🎯 No scan data available.\nRun /scan to trigger a market scan.",
                parse_mode="HTML",
            )
            return

        latest_id = max(all_scans.keys(), key=lambda k: all_scans[k].get("scan_date", ""))
        scan = all_scans[latest_id]
        buy_signals = [r for r in scan.get("results", []) if "BUY" in r.get("final_signal", "")]

        if not buy_signals:
            await update.message.reply_text("No BUY signals in latest scan.")
            return

        lines = [
            f"🎯 <b>BUY Signals</b> ({len(buy_signals)} stocks)\n"
            f"Scan: {scan.get('scan_date', 'N/A')[:16]} | Mode: {scan.get('mode', 'N/A')}\n"
            f"━━━━━━━━━━━━━━━━\n"
        ]

        for i, sig in enumerate(buy_signals[:10]):
            ticker = sig["ticker"].replace(".NS", "")
            conf = sig["final_confidence"]
            price = sig["current_price"]
            entry = sig.get("entry_exit", {})
            target = entry.get("target_price")
            sl = entry.get("stop_loss")
            profit_pct = entry.get("potential_profit_pct", 0) or 0

            target_str = f"₹{target:,.2f}" if target else "N/A"
            sl_str = f"₹{sl:,.2f}" if sl else "N/A"

            lines.append(
                f"{i+1}. <b>{ticker}</b> — {conf:.0f}%\n"
                f"   ₹{price:,.2f} → 🎯{target_str} (+{profit_pct:.1f}%) | 🛑{sl_str}\n"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show open positions (placeholder — full in Sprint 6 with DB)."""
    text = (
        "📊 <b>Position Status</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🔄 Open Positions: 0\n"
        "💰 Total Invested: ₹0\n"
        "📈 Unrealized P&L: ₹0\n\n"
        "<i>Trade tracking active after entering trades via the web app.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current portfolio allocation."""
    try:
        from app.main import _active_scans
        from app.tasks.auto_scheduler import auto_scan_results
        all_scans = {**_active_scans, **auto_scan_results}

        if not all_scans:
            await update.message.reply_text("No scan data. Run /scan first.")
            return

        latest_id = max(all_scans.keys(), key=lambda k: all_scans[k].get("scan_date", ""))
        scan = all_scans[latest_id]
        buy = [r for r in scan.get("results", [])
               if "BUY" in r.get("final_signal", "") and r.get("final_confidence", 0) >= 60][:5]

        if not buy:
            await update.message.reply_text("No stocks qualify for portfolio allocation.")
            return

        total_conf = sum(r["final_confidence"] for r in buy)
        lines = ["💼 <b>Portfolio Allocation</b> (₹20,000 capital)\n━━━━━━━━━━━━━━━━\n"]
        capital = 20000

        for r in buy:
            pct = r["final_confidence"] / total_conf * 100
            pct = min(pct, 40)  # Cap at 40% per stock
            amount = capital * pct / 100
            price = r.get("current_price", 1)
            shares = int(amount / price) if price > 0 else 0
            ticker = r["ticker"].replace(".NS", "")
            entry = r.get("entry_exit", {})
            target = entry.get("target_price")
            target_str = f"🎯₹{target:,.0f}" if target else ""

            lines.append(
                f"  <b>{ticker}</b> — {pct:.0f}% (₹{amount:,.0f}, {shares} shares)\n"
                f"    {r['final_signal']} {r['final_confidence']:.0f}% | ₹{price:,.2f} {target_str}\n"
            )

        lines.append(f"\n💡 Use /signals for full signal details")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")


async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick lookup for a specific stock. Usage: /stock RELIANCE"""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /stock RELIANCE\nExample: /stock TCS, /stock INFY, /stock RTN")
        return

    query = args[0].upper()

    from app.engine.stock_universe import resolve_ticker
    ticker = resolve_ticker(query)

    if not ticker:
        await update.message.reply_text(
            f"❌ Stock '{query}' not found in universe.\n\n"
            f"💡 Try full name: /stock RELIANCE\n"
            f"Or short: /stock SBI, /stock NALCO\n"
            f"Use /sectors to see all available stocks.",
            parse_mode="HTML",
        )
        return

    info = STOCK_UNIVERSE[ticker]

    # Try to get latest scan data for this stock
    scan_info = ""
    try:
        from app.main import _active_scans
        from app.tasks.auto_scheduler import auto_scan_results
        all_scans = {**_active_scans, **auto_scan_results}
        if all_scans:
            latest_id = max(all_scans.keys(), key=lambda k: all_scans[k].get("scan_date", ""))
            scan = all_scans[latest_id]
            for r in scan.get("results", []):
                if r["ticker"] == ticker:
                    entry = r.get("entry_exit", {})
                    target = entry.get("target_price")
                    sl = entry.get("stop_loss")
                    target_str = f"₹{target:,.2f}" if target else "N/A"
                    sl_str = f"₹{sl:,.2f}" if sl else "N/A"
                    profit_pct = entry.get("potential_profit_pct", 0) or 0
                    scan_info = (
                        f"\n📊 <b>Latest Scan Data:</b>\n"
                        f"Signal: <b>{r['final_signal']}</b> ({r['final_confidence']:.0f}%)\n"
                        f"Price: ₹{r['current_price']:,.2f}\n"
                        f"🎯 Target: {target_str} (+{profit_pct:.1f}%)\n"
                        f"🛑 Stop Loss: {sl_str}\n"
                        f"R:R: {entry.get('risk_reward', 0):.1f}x\n"
                        f"News: {r.get('news_sentiment', {}).get('overall_sentiment', 'N/A')}\n"
                    )
                    break
    except Exception:
        pass

    await update.message.reply_text(
        f"🔍 <b>{ticker.replace('.NS','')}</b> — {info['name']}\n"
        f"Sector: {info['sector']} | Cap: {info['cap']}"
        f"{scan_info}\n"
        f"<i>Use /scanstock {query} for a fresh analysis.</i>",
        parse_mode="HTML",
    )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trigger a market scan in background thread."""
    await update.message.reply_text(
        "🚀 <b>Scan triggered!</b>\n\n"
        "Scanning stocks with 15 indicators + LLM sentiment.\n"
        "This takes 3-10 minutes. You'll receive signals when done.\n\n"
        "<i>Use the web app for real-time progress tracking.</i>",
        parse_mode="HTML",
    )

    # Run scan in background thread and send results back
    import threading

    def _run_and_notify():
        try:
            from app.engine.scanner import run_full_scan
            from app.tasks.auto_scheduler import auto_scan_results, _format_scan_telegram, _send_telegram_alert
            result = run_full_scan(scope="all", mode="weekly", use_ai=True)
            scan_id = result["scan_id"]
            auto_scan_results[scan_id] = result
            telegram_msg = _format_scan_telegram(result)
            _send_telegram_alert(telegram_msg)
            log.info("telegram_manual_scan_complete", scan_id=scan_id, buy_signals=len(result["buy_signals"]))
        except Exception as e:
            log.warning("telegram_scan_failed", error=str(e)[:200])
            try:
                from app.tasks.auto_scheduler import _send_telegram_alert
                _send_telegram_alert(f"❌ <b>Scan Failed</b>\nError: {str(e)[:200]}")
            except Exception:
                pass

    thread = threading.Thread(target=_run_and_notify, daemon=True)
    thread.start()


async def cmd_sectors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show sector breakdown with stock names and latest signals."""
    from app.engine.stock_universe import SECTORS, STOCK_UNIVERSE

    sector_stocks = {}
    for ticker, v in STOCK_UNIVERSE.items():
        s = v["sector"]
        if s not in sector_stocks:
            sector_stocks[s] = []
        sector_stocks[s].append(ticker.replace(".NS", ""))

    # Check for BUY signals per sector from latest scan
    buy_by_sector = {}
    try:
        from app.main import _active_scans
        from app.tasks.auto_scheduler import auto_scan_results
        all_scans = {**_active_scans, **auto_scan_results}
        if all_scans:
            latest_id = max(all_scans.keys(), key=lambda k: all_scans[k].get("scan_date", ""))
            for r in all_scans[latest_id].get("results", []):
                if "BUY" in r.get("final_signal", ""):
                    s = r.get("sector", "")
                    buy_by_sector[s] = buy_by_sector.get(s, 0) + 1
    except Exception:
        pass

    sorted_sectors = sorted(sector_stocks.items(), key=lambda x: -len(x[1]))

    lines = [f"📊 <b>Sector Breakdown</b> ({len(STOCK_UNIVERSE)} stocks)\n━━━━━━━━━━━━━━━━\n"]

    for sector, tickers in sorted_sectors:
        buy_count = buy_by_sector.get(sector, 0)
        buy_badge = f" 🟢{buy_count} BUY" if buy_count > 0 else ""
        stock_list = ", ".join(tickers[:8])
        if len(tickers) > 8:
            stock_list += f" +{len(tickers)-8} more"
        lines.append(f"<b>{sector}</b> ({len(tickers)}){buy_badge}\n  <code>{stock_list}</code>\n")

    lines.append(f"━━━━━━━━━━━━━━━━\n💡 /stock TICKER — quick lookup\n💡 /scanstock TICKER — full analysis")

    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:3950] + "\n..."

    await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle alert notifications."""
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.message.reply_text(
            "🔔 <b>Alert Settings</b>\n\n"
            "Usage: /alerts on or /alerts off\n\n"
            "Current: <b>ON</b> (all alerts enabled)",
            parse_mode="HTML",
        )
        return

    state = args[0].lower()
    emoji = "🔔" if state == "on" else "🔕"
    await update.message.reply_text(
        f"{emoji} Alerts turned <b>{state.upper()}</b>",
        parse_mode="HTML",
    )


async def cmd_scanstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Smart scan — auto-analyzes all timeframes, recommends hold duration.
    Usage: /scanstock RELIANCE"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔍 <b>Smart Stock Scanner</b>\n\n"
            "Usage: /scanstock RELIANCE\n"
            "       /scanstock SBI\n"
            "       /scanstock SUZLON\n\n"
            "Auto-analyzes weekly + monthly + trend\n"
            "and tells you the best holding duration.",
            parse_mode="HTML",
        )
        return

    query = args[0].upper()

    from app.engine.stock_universe import resolve_ticker
    ticker = resolve_ticker(query)
    if not ticker:
        await update.message.reply_text(f"❌ Stock '{query}' not found. Try /stock {query}")
        return

    info = STOCK_UNIVERSE[ticker]
    await update.message.reply_text(
        f"🔍 Smart scanning <b>{ticker.replace('.NS','')}</b> ({info['name']})...\n"
        f"Analyzing weekly + monthly + long-term trend...\nThis takes 30-90 seconds.",
        parse_mode="HTML",
    )

    import threading

    def _scan_and_reply():
        try:
            from app.engine.scanner import analyze_single_stock, fetch_stock_data, fetch_nifty_data, _safe_float
            from app.sentiment.analyzer import fetch_news_from_rss
            from app.tasks.auto_scheduler import _send_telegram_alert

            news = fetch_news_from_rss(max_articles=30)
            nifty = fetch_nifty_data()

            # Analyze BOTH timeframes
            weekly = analyze_single_stock(ticker, info, news, nifty_df=nifty, mode="weekly", use_ai=True)
            monthly = analyze_single_stock(ticker, info, news, nifty_df=nifty, mode="monthly", use_ai=False)

            if not weekly and not monthly:
                _send_telegram_alert(f"❌ Could not analyze {ticker.replace('.NS','')}. No data.")
                return

            best = weekly or monthly
            w_conf = _safe_float(weekly["final_confidence"]) if weekly else 0
            m_conf = _safe_float(monthly["final_confidence"]) if monthly else 0
            price = _safe_float(best["current_price"])

            # Check long-term trend
            df_6m = fetch_stock_data(ticker, period="6mo")
            trend_score = 0
            if df_6m is not None and len(df_6m) >= 50:
                import pandas as pd
                sma20 = _safe_float(df_6m["Close"].rolling(20).mean().iloc[-1], price)
                sma50 = _safe_float(df_6m["Close"].rolling(50).mean().iloc[-1], price)
                if price > sma20: trend_score += 1
                if price > sma50: trend_score += 1
                if sma20 > sma50: trend_score += 1
                if len(df_6m) >= 100:
                    sma100 = _safe_float(df_6m["Close"].rolling(100).mean().iloc[-1], price)
                    if price > sma100: trend_score += 1

            # Smart hold recommendation
            if w_conf >= 70 and m_conf >= 65 and trend_score >= 3:
                hold = "📅 2-4 weeks"
                reason = "Strong short + long-term momentum"
            elif m_conf >= 65 and trend_score >= 3:
                hold = "📅 1-2 months"
                reason = "Monthly signal strong, uptrend intact"
            elif trend_score >= 4 and m_conf >= 55:
                hold = "📅 3-6 months"
                reason = "Strong long-term uptrend"
            elif w_conf >= 65:
                hold = "📅 1-2 weeks"
                reason = "Short-term setup only"
            elif m_conf >= 60:
                hold = "📅 2-4 weeks"
                reason = "Moderate monthly signal"
            else:
                hold = "⏳ WAIT — no clear entry"
                reason = "Weak signals, avoid for now"

            use_r = monthly if m_conf > w_conf else weekly
            if not use_r:
                use_r = best
            entry = use_r.get("entry_exit", {})
            target = entry.get("target_price")
            sl = entry.get("stop_loss")
            target_str = f"₹{target:,.2f}" if target else "N/A"
            sl_str = f"₹{sl:,.2f}" if sl else "N/A"
            profit_pct = entry.get("potential_profit_pct", 0) or 0
            rr = entry.get("risk_reward", 0) or 0
            news_sent = best.get("news_sentiment", {}).get("overall_sentiment", "N/A")

            emoji = "🟢" if "STRONG" in use_r["final_signal"] else "🔵" if "BUY" in use_r["final_signal"] else "🟡" if "HOLD" in use_r["final_signal"] else "🔴"
            trend_label = "Strong ↑" if trend_score >= 3 else "Moderate →" if trend_score >= 2 else "Weak ↓"

            msg = (
                f"📊 <b>Smart Scan: {ticker.replace('.NS','')}</b> — {info['name']}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💰 Price: ₹{price:,.2f} | {info['sector']} | {info['cap']}\n\n"
                f"{emoji} Signal: <b>{use_r['final_signal']}</b> ({use_r['final_confidence']:.0f}%)\n"
                f"🎯 Target: {target_str} (+{profit_pct:.1f}%)\n"
                f"🛑 Stop Loss: {sl_str}\n"
                f"⚖️ R:R = 1:{rr:.1f}\n\n"
                f"🕐 <b>Recommended Hold: {hold}</b>\n"
                f"   {reason}\n\n"
                f"📈 Weekly: {weekly['final_signal'] if weekly else 'N/A'} ({w_conf:.0f}%)\n"
                f"📈 Monthly: {monthly['final_signal'] if monthly else 'N/A'} ({m_conf:.0f}%)\n"
                f"📈 Trend: {trend_label} ({trend_score}/4)\n"
                f"📰 News: {news_sent}\n"
            )
            _send_telegram_alert(msg)
        except Exception as e:
            try:
                from app.tasks.auto_scheduler import _send_telegram_alert
                _send_telegram_alert(f"❌ Scan failed for {query}: {str(e)[:150]}")
            except Exception:
                pass

    thread = threading.Thread(target=_scan_and_reply, daemon=True)
    thread.start()


async def cmd_budgetpicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show affordable stock picks for small budget. Usage: /budgetpicks or /budgetpicks 15000"""
    args = context.args
    budget = 20000
    if args:
        try:
            budget = int(args[0])
        except ValueError:
            pass

    await update.message.reply_text(
        f"💰 Finding best picks for ₹{budget:,} budget...\n"
        f"Filtering stocks under ₹500...",
        parse_mode="HTML",
    )

    try:
        from app.main import _active_scans
        from app.tasks.auto_scheduler import auto_scan_results
        all_scans = {**_active_scans, **auto_scan_results}

        if not all_scans:
            await update.message.reply_text(
                "❌ No scan data available yet.\n"
                "Run /scan first or wait for the next auto-scan at 10:30 AM.",
                parse_mode="HTML",
            )
            return

        latest_id = max(all_scans.keys(), key=lambda k: all_scans[k].get("scan_date", ""))
        scan = all_scans[latest_id]
        results = scan.get("results", [])

        # Filter affordable BUY signals
        affordable = [
            r for r in results
            if "BUY" in r.get("final_signal", "")
            and r.get("current_price", 99999) <= 500
            and r.get("final_confidence", 0) >= 55
        ]
        affordable.sort(key=lambda x: x["final_confidence"], reverse=True)

        if not affordable:
            await update.message.reply_text(
                f"📊 No BUY signals under ₹500 in the latest scan.\n"
                f"Try running a new /scan or lowering confidence threshold.",
                parse_mode="HTML",
            )
            return

        lines = [
            f"💰 <b>Budget Picks for ₹{budget:,}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Stocks under ₹500 | From scan {scan.get('scan_date', '')[:16]}\n"
        ]

        remaining = budget
        total_invested = 0

        for r in affordable[:4]:
            price = r["current_price"]
            entry = r.get("entry_exit", {})
            target = entry.get("target_price")
            sl = entry.get("stop_loss")
            profit_pct = entry.get("potential_profit_pct", 0) or 0

            alloc = min(remaining, budget * 0.40)
            shares = int(alloc / price) if price > 0 else 0
            if shares < 1:
                continue
            amount = round(shares * price, 2)
            remaining -= amount
            total_invested += amount

            ticker = r["ticker"].replace(".NS", "")
            target_str = f"₹{target:,.2f}" if target else "N/A"
            sl_str = f"₹{sl:,.2f}" if sl else "N/A"

            lines.append(
                f"\n{'🟢' if 'STRONG' in r['final_signal'] else '🔵'} <b>{ticker}</b> — {r['final_confidence']:.0f}%\n"
                f"   ₹{price:,.2f} × {shares} shares = ₹{amount:,.0f}\n"
                f"   🎯 {target_str} (+{profit_pct:.1f}%) | 🛑 {sl_str}\n"
            )

            if remaining < 1000:
                break

        lines.append(
            f"\n━━━━━━━━━━━━━━━━\n"
            f"💵 Invested: ₹{total_invested:,.0f} | Cash: ₹{remaining:,.0f}\n"
            f"💡 Use /scanstock TICKER for detailed analysis"
        )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")


async def cmd_autoscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show auto-scan schedule and status."""
    from app.tasks.auto_scheduler import auto_scan_status

    status = auto_scan_status.get("status", "idle")
    last = auto_scan_status.get("last_scan", "Never")
    next_scan = auto_scan_status.get("next_scan", "Calculating...")
    buy_count = auto_scan_status.get("buy_signals", 0)

    emoji = "🟢" if status == "idle" else "🔄" if status == "scanning" else "✅" if status == "complete" else "❌"

    text = (
        f"⏰ <b>Auto-Scan Schedule</b>\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"{emoji} Status: <b>{status.upper()}</b>\n"
        f"📅 Last scan: {last}\n"
        f"⏭ Next scan: <b>{next_scan}</b>\n"
    )

    if status == "complete" and buy_count > 0:
        text += f"🎯 Last result: {buy_count} BUY signals\n"

    text += (
        f"\n📋 <b>Schedule (IST):</b>\n"
        f"  Mon-Fri 10:30 AM — Full scan (after opening noise)\n"
        f"  Wed     1:00 PM — Mid-week setups (AI ON)\n"
        f"  Friday  3:00 PM — Weekend watchlist\n"
        f"  Sunday  6:00 PM — Weekly preview scan\n"
        f"\n💡 Results auto-sent here + shown on dashboard\n"
        f"🎯 Use /scanstock TICKER for instant single-stock scan"
    )

    await update.message.reply_text(text, parse_mode="HTML")
