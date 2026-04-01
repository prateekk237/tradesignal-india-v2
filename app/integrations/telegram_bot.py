"""
Telegram Bot Integration — Alert sender + bot commands.
Sends BUY signals, partial profit alerts, emergency exits, weekly summaries.
"""

import asyncio
import httpx
import structlog
from datetime import datetime
from typing import Optional

from app.config import get_settings

log = structlog.get_logger()
settings = get_settings()

# Rate limiting: max 1 alert per stock per hour
_alert_cooldown: dict[str, datetime] = {}
COOLDOWN_SECONDS = 3600


def _can_send_alert(stock_ticker: str) -> bool:
    """Check if we're within rate limit for this stock."""
    now = datetime.utcnow()
    last_sent = _alert_cooldown.get(stock_ticker)
    if last_sent and (now - last_sent).total_seconds() < COOLDOWN_SECONDS:
        return False
    _alert_cooldown[stock_ticker] = now
    return True


async def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram Bot API."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        log.warning("telegram_not_configured")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                log.info("telegram_sent", length=len(text))
                return True
            else:
                log.warning("telegram_send_failed", status=resp.status_code, body=resp.text[:200])
                return False
    except Exception as e:
        log.error("telegram_error", error=str(e))
        return False


def send_telegram_sync(text: str, parse_mode: str = "HTML") -> bool:
    """Synchronous wrapper for send_telegram_message."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, send_telegram_message(text, parse_mode))
                return future.result(timeout=20)
        else:
            return asyncio.run(send_telegram_message(text, parse_mode))
    except Exception as e:
        log.error("telegram_sync_error", error=str(e))
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  ALERT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════

def alert_buy_signal(signal: dict) -> bool:
    """Send BUY signal alert."""
    ticker = signal.get("ticker", "?").replace(".NS", "")
    if not _can_send_alert(ticker):
        return False

    entry = signal.get("entry_exit", {})
    news = signal.get("news_sentiment", {})
    ai = signal.get("ai_data", {})

    text = (
        f"🎯 <b>NEW BUY SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker}</b> — {signal.get('name', '')}\n"
        f"   {signal.get('cap', '')} Cap | {signal.get('sector', '')}\n\n"
        f"💰 Price: <code>₹{(signal.get('current_price') or 0):,.2f}</code>\n"
        f"📥 Entry: <code>₹{(entry.get('entry_price') or 0):,.2f}</code>\n"
        f"🎯 Target: <code>₹{(entry.get('target_price') or 0):,.2f}</code>"
        f" (+{(entry.get('potential_profit_pct') or 0):.1f}%)\n"
        f"🛑 Stop Loss: <code>₹{(entry.get('stop_loss') or 0):,.2f}</code>"
        f" (-{(entry.get('potential_loss_pct') or 0):.1f}%)\n"
        f"⚖️ R:R = {(entry.get('risk_reward') or 0):.1f}\n\n"
        f"🔥 Confidence: <b>{(signal.get('final_confidence') or 0):.0f}%</b>\n"
        f"   Base: {signal.get('base_confidence', 0)}% "
        f"| News: {(signal.get('news_modifier') or 0):+.0f} "
        f"| AI: {(signal.get('ai_modifier') or 0):+.0f}\n"
        f"📰 News: {news.get('overall_sentiment', 'N/A')} "
        f"({news.get('article_count', 0)} articles)\n"
        f"🤖 Sentiment: {news.get('source', 'N/A').upper()}\n"
    )

    if ai.get("ai_analysis"):
        text += f"\n💡 AI: {ai['ai_analysis'][:200]}\n"

    text += f"\n⏱ Mode: {signal.get('holding_mode', 'weekly')}"

    return send_telegram_sync(text)


def alert_partial_profit(ticker: str, name: str, entry_price: float,
                         current_price: float, reason: str,
                         pct_to_sell: int = 50) -> bool:
    """Send partial profit booking alert."""
    ticker_clean = ticker.replace(".NS", "")
    if not _can_send_alert(f"{ticker_clean}_partial"):
        return False

    pnl_pct = (current_price - entry_price) / entry_price * 100

    text = (
        f"💰 <b>PARTIAL PROFIT ALERT</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker_clean}</b> — {name}\n\n"
        f"Entry: <code>₹{entry_price:,.2f}</code> → "
        f"Now: <code>₹{current_price:,.2f}</code> "
        f"(<b>{pnl_pct:+.1f}%</b>)\n\n"
        f"📋 Action: Sell <b>{pct_to_sell}%</b> of position\n"
        f"📝 Reason: {reason}\n"
    )

    return send_telegram_sync(text)


def alert_emergency_exit(ticker: str, name: str, entry_price: float,
                         current_price: float, reason: str) -> bool:
    """Send emergency exit alert (HIGH impact negative news)."""
    ticker_clean = ticker.replace(".NS", "")
    pnl_pct = (current_price - entry_price) / entry_price * 100

    # Bypass cooldown for emergencies
    _alert_cooldown.pop(ticker_clean, None)

    text = (
        f"🚨🚨 <b>EMERGENCY EXIT</b> 🚨🚨\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker_clean}</b> — {name}\n\n"
        f"⚠️ <b>EXIT ALL IMMEDIATELY</b>\n\n"
        f"Entry: <code>₹{entry_price:,.2f}</code> → "
        f"Now: <code>₹{current_price:,.2f}</code> "
        f"(<b>{pnl_pct:+.1f}%</b>)\n\n"
        f"🔴 Reason: {reason}\n"
        f"📋 Action: Market sell ALL shares NOW\n"
    )

    return send_telegram_sync(text)


def alert_stop_loss_hit(ticker: str, name: str, entry_price: float,
                        stop_loss: float, current_price: float) -> bool:
    """Send stop-loss trigger alert."""
    ticker_clean = ticker.replace(".NS", "")
    pnl_pct = (current_price - entry_price) / entry_price * 100

    text = (
        f"🛑 <b>STOP LOSS TRIGGERED</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker_clean}</b> — {name}\n\n"
        f"Entry: <code>₹{entry_price:,.2f}</code>\n"
        f"Stop Loss: <code>₹{stop_loss:,.2f}</code>\n"
        f"Current: <code>₹{current_price:,.2f}</code>\n"
        f"Loss: <b>{pnl_pct:.1f}%</b>\n\n"
        f"📋 Action: Exit position\n"
    )

    return send_telegram_sync(text)


def alert_target_hit(ticker: str, name: str, entry_price: float,
                     target_price: float, current_price: float) -> bool:
    """Send target hit alert."""
    ticker_clean = ticker.replace(".NS", "")
    pnl_pct = (current_price - entry_price) / entry_price * 100

    text = (
        f"🎯 <b>TARGET REACHED!</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker_clean}</b> — {name}\n\n"
        f"Entry: <code>₹{entry_price:,.2f}</code>\n"
        f"Target: <code>₹{target_price:,.2f}</code>\n"
        f"Current: <code>₹{current_price:,.2f}</code>\n"
        f"Profit: <b>+{pnl_pct:.1f}%</b> 🎉\n\n"
        f"📋 Action: Book full profit\n"
    )

    return send_telegram_sync(text)


def alert_trailing_stop(ticker: str, name: str, entry_price: float,
                        trailing_stop: float, current_price: float) -> bool:
    """Send trailing stop trigger alert."""
    ticker_clean = ticker.replace(".NS", "")
    pnl_pct = (current_price - entry_price) / entry_price * 100

    text = (
        f"🔒 <b>TRAILING STOP TRIGGERED</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker_clean}</b> — {name}\n\n"
        f"Entry: <code>₹{entry_price:,.2f}</code>\n"
        f"Trail Stop: <code>₹{trailing_stop:,.2f}</code>\n"
        f"Current: <code>₹{current_price:,.2f}</code>\n"
        f"Locked: <b>+{pnl_pct:.1f}%</b>\n\n"
        f"📋 Action: Exit — profit locked in\n"
    )

    return send_telegram_sync(text)


def alert_weekly_summary(scan_data: dict) -> bool:
    """Send weekly scan summary."""
    results = scan_data.get("results", [])
    buy_signals = scan_data.get("buy_signals", [])
    mode = scan_data.get("mode", "weekly")

    top5 = buy_signals[:5]
    top5_text = "\n".join([
        f"  {i+1}. {r['ticker'].replace('.NS','')} — {r['final_confidence']:.0f}% ({r['final_signal']})"
        for i, r in enumerate(top5)
    ]) if top5 else "  No BUY signals this week"

    # Sector distribution
    sector_counts: dict[str, int] = {}
    for r in buy_signals:
        s = r.get("sector", "Unknown")
        sector_counts[s] = sector_counts.get(s, 0) + 1
    top_sectors = sorted(sector_counts.items(), key=lambda x: -x[1])[:3]
    sectors_text = ", ".join([f"{s} ({c})" for s, c in top_sectors]) if top_sectors else "None"

    text = (
        f"📊 <b>WEEKLY SCAN SUMMARY</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🗓 {datetime.utcnow().strftime('%d %b %Y')}\n"
        f"⚙️ Mode: {mode}\n\n"
        f"📈 Stocks Scanned: {scan_data.get('total_stocks', 0)}\n"
        f"✅ Analyzed: {scan_data.get('analyzed', 0)}\n"
        f"🎯 BUY Signals: <b>{len(buy_signals)}</b>\n"
        f"📰 News Articles: {scan_data.get('news_articles_fetched', 0)}\n\n"
        f"<b>Top Picks:</b>\n{top5_text}\n\n"
        f"<b>Hot Sectors:</b> {sectors_text}\n"
    )

    return send_telegram_sync(text)


def alert_period_end(ticker: str, name: str, entry_price: float,
                     current_price: float, holding_mode: str) -> bool:
    """Alert when holding period ends."""
    ticker_clean = ticker.replace(".NS", "")
    pnl_pct = (current_price - entry_price) / entry_price * 100

    text = (
        f"⏰ <b>HOLDING PERIOD END</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker_clean}</b> — {name}\n\n"
        f"Period: {holding_mode}\n"
        f"Entry: <code>₹{entry_price:,.2f}</code>\n"
        f"Now: <code>₹{current_price:,.2f}</code>\n"
        f"P&L: <b>{pnl_pct:+.1f}%</b>\n\n"
        f"📋 Action: Exit position (time-based)\n"
    )

    return send_telegram_sync(text)


def alert_supertrend_flip(ticker: str, name: str, entry_price: float,
                          current_price: float, direction: str) -> bool:
    """Alert on SuperTrend direction flip."""
    ticker_clean = ticker.replace(".NS", "")
    pnl_pct = (current_price - entry_price) / entry_price * 100

    text = (
        f"⚠️ <b>TREND REVERSAL</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>{ticker_clean}</b> — {name}\n\n"
        f"SuperTrend flipped → <b>{direction}</b>\n"
        f"Entry: <code>₹{entry_price:,.2f}</code>\n"
        f"Now: <code>₹{current_price:,.2f}</code> ({pnl_pct:+.1f}%)\n\n"
        f"📋 Action: Book 50% profit, trail stop on rest\n"
    )

    return send_telegram_sync(text)
