"""Celery scan tasks — scheduled and on-demand market scanning."""

import structlog
from app.tasks.celery_app import celery_app
from app.engine.scanner import run_full_scan
from app.integrations.telegram_bot import alert_buy_signal, alert_weekly_summary

log = structlog.get_logger()


@celery_app.task(name="app.tasks.scan_tasks.weekly_scan", bind=True, max_retries=2)
def weekly_scan(self):
    """Run full weekly scan every Sunday 6 PM IST and send Telegram summary."""
    log.info("weekly_scan_started")

    try:
        result = run_full_scan(scope="all", mode="weekly", use_ai=True)

        # Send weekly summary via Telegram
        alert_weekly_summary(result)

        # Send individual alerts for top 5 BUY signals
        buy_signals = result.get("buy_signals", [])
        for sig in buy_signals[:5]:
            if sig.get("final_confidence", 0) >= 70:
                alert_buy_signal(sig)

        log.info("weekly_scan_complete",
                 analyzed=result.get("analyzed", 0),
                 buy_signals=len(buy_signals))

        return {
            "scan_id": result["scan_id"],
            "analyzed": result["analyzed"],
            "buy_signals": len(buy_signals),
        }

    except Exception as e:
        log.error("weekly_scan_error", error=str(e))
        raise self.retry(exc=e, countdown=120)


@celery_app.task(name="app.tasks.scan_tasks.on_demand_scan")
def on_demand_scan(scope: str = "all", mode: str = "weekly",
                   use_ai: bool = True, sectors: list = None):
    """On-demand scan triggered via API or Telegram command."""
    log.info("on_demand_scan_started", scope=scope, mode=mode)

    result = run_full_scan(scope=scope, sectors=sectors, mode=mode, use_ai=use_ai)

    buy_signals = result.get("buy_signals", [])
    for sig in buy_signals[:3]:
        if sig.get("final_confidence", 0) >= 65:
            alert_buy_signal(sig)

    return {
        "scan_id": result["scan_id"],
        "analyzed": result["analyzed"],
        "buy_signals": len(buy_signals),
    }
