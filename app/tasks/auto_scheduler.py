"""
Auto Scheduler — Runs market scans on schedule without Celery/Redis.
Uses a background thread with sleep-based scheduling.

Schedule (IST):
  - Monday-Friday 9:20 AM  → Full scan (market open)
  - Monday-Friday 1:00 PM  → Mid-day re-scan
  - Sunday 6:00 PM         → Weekly preview scan
"""

import threading
import time
from datetime import datetime, timedelta
import structlog

from app.config import get_settings
from app.engine.scanner import run_full_scan
from app.engine.stock_universe import STOCK_UNIVERSE

log = structlog.get_logger()
settings = get_settings()

# Shared state — main.py reads from this
auto_scan_results = {}
auto_scan_status = {"last_scan": None, "next_scan": None, "status": "idle"}


def _get_ist_now():
    """Get current time in IST (UTC+5:30)."""
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


def _send_telegram_alert(message: str):
    """Send a message to Telegram."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
    except Exception as e:
        log.warning("telegram_send_failed", error=str(e)[:100])


def _format_scan_telegram(scan_result: dict) -> str:
    """Format scan results for Telegram message."""
    buy_signals = scan_result.get("buy_signals", [])
    analyzed = scan_result.get("analyzed", 0)
    mode = scan_result.get("mode", "weekly")
    ist_now = _get_ist_now()

    header = (
        f"🚀 <b>TradeSignal Auto-Scan Complete</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📅 {ist_now.strftime('%a, %d %b %Y %I:%M %p')} IST\n"
        f"📊 Analyzed: {analyzed} stocks | Mode: {mode}\n"
        f"🎯 BUY Signals: {len(buy_signals)}\n\n"
    )

    if not buy_signals:
        return header + "No stocks meet the confidence threshold.\nMarket may be in wait-and-watch mode."

    lines = []
    for i, sig in enumerate(buy_signals[:8]):
        ticker = sig["ticker"].replace(".NS", "")
        conf = sig["final_confidence"]
        price = sig["current_price"]
        signal = sig["final_signal"]
        entry = sig.get("entry_exit", {})
        target = entry.get("target_price") or 0
        sl = entry.get("stop_loss") or 0
        news = sig.get("news_sentiment", {}).get("overall_sentiment", "—")
        profit_pct = entry.get("potential_profit_pct", 0) or 0

        target_str = f"₹{target:,.2f}" if target else "N/A"
        sl_str = f"₹{sl:,.2f}" if sl else "N/A"
        profit_str = f"+{profit_pct:.1f}%" if profit_pct else ""

        lines.append(
            f"{'🟢' if 'STRONG' in signal else '🔵'} <b>{ticker}</b> — {conf:.0f}%\n"
            f"   ₹{price:,.2f} → 🎯{target_str} | 🛑{sl_str} {profit_str}\n"
            f"   {signal} | News: {news}\n"
        )

    footer = (
        f"\n📱 View full details on dashboard\n"
        f"💡 Tip: Set alerts with /alerts on"
    )

    return header + "\n".join(lines) + footer


def _run_scheduled_scan(scope: str = "all", mode: str = "weekly", use_ai: bool = True):
    """Execute a scan and store results + send Telegram."""
    global auto_scan_results, auto_scan_status
    ist_now = _get_ist_now()

    log.info("auto_scan_starting", time=ist_now.isoformat(), scope=scope, mode=mode)
    auto_scan_status["status"] = "scanning"

    # Send "scan starting" alert
    _send_telegram_alert(
        f"🔍 <b>Auto-Scan Starting</b>\n"
        f"📅 {ist_now.strftime('%a %I:%M %p')} IST\n"
        f"📊 {len(STOCK_UNIVERSE)} stocks | Mode: {mode}\n"
        f"🧠 AI: {'ON' if use_ai else 'OFF'}"
    )

    try:
        result = run_full_scan(scope=scope, mode=mode, use_ai=use_ai)

        # Store for dashboard
        scan_id = result["scan_id"]
        auto_scan_results[scan_id] = result

        auto_scan_status = {
            "last_scan": ist_now.isoformat(),
            "last_scan_id": scan_id,
            "next_scan": None,  # Will be set by scheduler
            "status": "complete",
            "buy_signals": len(result["buy_signals"]),
            "analyzed": result["analyzed"],
        }

        log.info("auto_scan_complete", scan_id=scan_id,
                 analyzed=result["analyzed"], buy_signals=len(result["buy_signals"]))

        # Send results to Telegram
        telegram_msg = _format_scan_telegram(result)
        _send_telegram_alert(telegram_msg)

        return result

    except Exception as e:
        log.warning("auto_scan_failed", error=str(e)[:200])
        auto_scan_status["status"] = "error"
        _send_telegram_alert(f"❌ <b>Auto-Scan Failed</b>\nError: {str(e)[:200]}")
        return None


def _scheduler_loop():
    """Main scheduler loop — runs forever in background thread."""
    log.info("auto_scheduler_started")

    # Wait 30 seconds for app to fully initialize
    time.sleep(30)

    while True:
        try:
            ist_now = _get_ist_now()
            weekday = ist_now.weekday()  # 0=Monday, 6=Sunday
            hour = ist_now.hour
            minute = ist_now.minute

            # ── Schedule (Improved — avoid 9:20 AM opening volatility) ──
            # Monday-Friday 10:30 AM IST → Morning scan (after opening noise settles)
            if weekday < 5 and hour == 10 and minute == 30:
                log.info("auto_scan_trigger", reason="morning_post_open")
                _run_scheduled_scan(scope="all", mode="weekly", use_ai=True)
                time.sleep(3600)  # Sleep 1 hour to avoid re-trigger
                continue

            # Wednesday 1:00 PM IST → Mid-week fresh setups
            if weekday == 2 and hour == 13 and minute == 0:
                log.info("auto_scan_trigger", reason="midweek_rescan")
                _run_scheduled_scan(scope="all", mode="weekly", use_ai=True)
                time.sleep(3600)
                continue

            # Friday 3:00 PM IST → Weekend watchlist (scan but conservative)
            if weekday == 4 and hour == 15 and minute == 0:
                log.info("auto_scan_trigger", reason="friday_watchlist")
                _run_scheduled_scan(scope="large", mode="weekly", use_ai=False)
                time.sleep(3600)
                continue

            # Sunday 6:00 PM IST → Weekly preview scan
            if weekday == 6 and hour == 18 and minute == 0:
                log.info("auto_scan_trigger", reason="weekly_preview")
                _run_scheduled_scan(scope="all", mode="weekly", use_ai=True)
                time.sleep(3600)
                continue

            # Calculate next scan time for status
            next_scan = _calculate_next_scan(ist_now)
            auto_scan_status["next_scan"] = next_scan

        except Exception as e:
            log.warning("scheduler_error", error=str(e)[:200])

        # Check every 30 seconds
        time.sleep(30)


def _run_position_monitor():
    """Run position monitoring without Celery — checks exit conditions."""
    try:
        from app.tasks.monitor_tasks import monitor_open_positions
        result = monitor_open_positions()
        if result.get("alerts_sent", 0) > 0:
            log.info("monitor_alerts_sent", alerts=result["alerts_sent"])
    except Exception as e:
        log.warning("monitor_run_error", error=str(e)[:200])


def _run_news_monitor():
    """Run breaking news scanner without Celery."""
    try:
        from app.tasks.news_tasks import scan_breaking_news
        result = scan_breaking_news()
        if result.get("alerts_sent", 0) > 0:
            log.info("news_alerts_sent", alerts=result["alerts_sent"])
    except Exception as e:
        log.warning("news_monitor_error", error=str(e)[:200])


def _monitor_loop():
    """Monitor open positions + breaking news every 15 min during market hours.
    Runs as a separate background thread — no Celery/Redis needed."""
    log.info("position_monitor_thread_started")
    time.sleep(120)  # Wait 2 min for app to fully initialize

    last_monitor_run = 0
    last_news_run = 0

    while True:
        try:
            ist_now = _get_ist_now()
            weekday = ist_now.weekday()
            hour = ist_now.hour
            now = time.time()

            # Only run during IST market hours: Mon-Fri 9:15 AM - 3:45 PM
            is_market_hours = (weekday < 5 and 9 <= hour < 16)

            if is_market_hours:
                # Monitor positions every 15 minutes
                if now - last_monitor_run > 900:  # 15 min
                    log.info("running_position_monitor", time=ist_now.strftime("%H:%M"))
                    _run_position_monitor()
                    last_monitor_run = now

                # Scan breaking news every 10 minutes
                if now - last_news_run > 600:  # 10 min
                    _run_news_monitor()
                    last_news_run = now

        except Exception as e:
            log.warning("monitor_loop_error", error=str(e)[:200])

        time.sleep(60)  # Check every minute


def start_auto_scheduler():
    """Start the auto-scheduler + position monitor in background threads."""
    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="auto-scheduler")
    thread.start()
    log.info("auto_scheduler_thread_started")

    # Start position monitor thread (exit alerts + breaking news)
    monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="position-monitor")
    monitor_thread.start()
    log.info("position_monitor_thread_started")


def _calculate_next_scan(ist_now: datetime) -> str:
    """Calculate when the next auto-scan will run."""
    weekday = ist_now.weekday()
    hour = ist_now.hour

    if weekday < 5 and (hour < 10 or (hour == 10 and ist_now.minute < 30)):
        return "Today 10:30 AM IST"
    if weekday == 2 and hour < 13:
        return "Today 1:00 PM IST (mid-week)"
    if weekday == 4 and hour < 15:
        return "Today 3:00 PM IST (watchlist)"
    if weekday == 6 and hour < 18:
        return "Today 6:00 PM IST"

    days_ahead = 1
    if weekday == 4:
        days_ahead = 3
    elif weekday == 5:
        days_ahead = 2
    elif weekday == 6:
        days_ahead = 1

    next_day = ist_now + timedelta(days=days_ahead)
    return f"{next_day.strftime('%a, %d %b')} 10:30 AM IST"
