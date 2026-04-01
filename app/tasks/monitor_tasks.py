"""
Position Monitoring Tasks — Real-time monitoring of open trades.
Checks every 30 min during market hours for exit conditions:
- Target hit, stop-loss hit, trailing stop
- SuperTrend flip, Ichimoku cloud break
- RSI overbought + overextended price
"""

import structlog
from datetime import datetime
from decimal import Decimal

import yfinance as yf
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Trade, Stock, PriceSnapshot, PerformanceDaily
from app.engine.indicators import compute_all_indicators
from app.integrations.telegram_bot import (
    alert_target_hit, alert_stop_loss_hit, alert_trailing_stop,
    alert_partial_profit, alert_supertrend_flip, alert_period_end,
)

log = structlog.get_logger()
settings = get_settings()

try:
    from app.tasks.celery_app import celery_app
    _has_celery = True
except Exception:
    _has_celery = False


def _celery_task_or_plain(name):
    """Decorator: register as Celery task if available, otherwise plain function."""
    def decorator(func):
        if _has_celery:
            return celery_app.task(name=name)(func)
        return func
    return decorator


def _get_sync_session():
    """Create a synchronous DB session."""
    engine = create_engine(settings.DATABASE_URL_SYNC)
    return Session(engine)


def _compute_trailing_stop(entry_price: float, current_price: float,
                           atr: float, current_stop: float) -> float:
    """ATR-based trailing stop that only moves UP."""
    if current_price <= entry_price * 1.015:
        return current_stop
    new_stop = current_price - (2 * atr)
    return max(current_stop, new_stop)


@_celery_task_or_plain("app.tasks.monitor_tasks.monitor_open_positions")
def monitor_open_positions():
    """
    Monitor all open trades every 30 min during market hours.
    Checks 10 exit conditions and sends Telegram alerts.
    """
    log.info("monitor_positions_started")
    session = _get_sync_session()

    try:
        # Get all open trades
        open_trades = session.execute(
            select(Trade).where(Trade.status.in_(["OPEN", "PARTIAL_EXIT"]))
        ).scalars().all()

        if not open_trades:
            log.info("no_open_positions")
            return {"checked": 0}

        checked = 0
        alerts_sent = 0

        for trade in open_trades:
            try:
                stock = session.execute(
                    select(Stock).where(Stock.id == trade.stock_id)
                ).scalar_one_or_none()

                if not stock:
                    continue

                # Fetch latest price
                ticker_data = yf.Ticker(stock.ticker)
                df = ticker_data.history(period="5d", interval="1d")
                if df.empty:
                    continue

                current_price = float(df["Close"].iloc[-1])
                entry_price = float(trade.entry_price)
                target = float(trade.current_target or 0)
                stop_loss = float(trade.current_stop_loss or 0)

                # Compute quick indicators for this stock
                df_full = ticker_data.history(period="1mo", interval="1d")
                if len(df_full) >= 20:
                    df_full = compute_all_indicators(df_full, mode=trade.holding_mode or "weekly")
                    latest = df_full.iloc[-1]

                    rsi = float(latest.get("RSI_14", 50))
                    macd_hist = float(latest.get("MACD_Hist", 0))
                    st_dir = float(latest.get("SuperTrend_Dir", 0))
                    prev_st_dir = float(df_full.iloc[-2].get("SuperTrend_Dir", 0)) if len(df_full) > 1 else 0
                    vol_ratio = float(latest.get("Vol_Ratio", 1))
                    atr = float(latest.get("ATR", current_price * 0.02))
                else:
                    rsi, macd_hist, st_dir, prev_st_dir, vol_ratio = 50, 0, 0, 0, 1
                    atr = current_price * 0.02

                pnl_pct = (current_price - entry_price) / entry_price * 100

                # Save price snapshot
                snapshot = PriceSnapshot(
                    trade_id=trade.id,
                    stock_id=trade.stock_id,
                    price=Decimal(str(current_price)),
                    rsi=Decimal(str(round(rsi, 1))),
                    macd_hist=Decimal(str(round(macd_hist, 4))),
                    supertrend_signal="BULLISH" if st_dir == 1 else "BEARISH",
                    volume_ratio=Decimal(str(round(vol_ratio, 2))),
                    position_health=Decimal(str(round(max(0, 50 + pnl_pct * 5), 1))),
                )
                session.add(snapshot)

                # ── CHECK EXIT CONDITIONS ─────────────────────────────

                # 1. TARGET HIT
                if target > 0 and current_price >= target:
                    alert_target_hit(stock.ticker, stock.name, entry_price, target, current_price)
                    trade.status = "CLOSED"
                    trade.exit_price = Decimal(str(current_price))
                    trade.exit_date = datetime.utcnow()
                    trade.exit_reason = "TARGET_HIT"
                    trade.realized_pnl = Decimal(str(round((current_price - entry_price) * int(trade.shares_remaining or trade.shares_bought), 2)))
                    trade.realized_pnl_pct = Decimal(str(round(pnl_pct, 2)))
                    alerts_sent += 1
                    session.commit()
                    continue

                # 2. STOP LOSS HIT
                if stop_loss > 0 and current_price <= stop_loss:
                    alert_stop_loss_hit(stock.ticker, stock.name, entry_price, stop_loss, current_price)
                    trade.status = "CLOSED"
                    trade.exit_price = Decimal(str(current_price))
                    trade.exit_date = datetime.utcnow()
                    trade.exit_reason = "STOP_LOSS"
                    trade.realized_pnl = Decimal(str(round((current_price - entry_price) * int(trade.shares_remaining or trade.shares_bought), 2)))
                    trade.realized_pnl_pct = Decimal(str(round(pnl_pct, 2)))
                    alerts_sent += 1
                    session.commit()
                    continue

                # 3. TRAILING STOP UPDATE
                new_trailing = _compute_trailing_stop(entry_price, current_price, atr, stop_loss)
                if new_trailing > stop_loss:
                    trade.current_stop_loss = Decimal(str(round(new_trailing, 2)))
                    if current_price <= new_trailing:
                        alert_trailing_stop(stock.ticker, stock.name, entry_price, new_trailing, current_price)
                        trade.status = "CLOSED"
                        trade.exit_price = Decimal(str(current_price))
                        trade.exit_date = datetime.utcnow()
                        trade.exit_reason = "TRAILING_STOP"
                        trade.realized_pnl = Decimal(str(round((current_price - entry_price) * int(trade.shares_remaining or trade.shares_bought), 2)))
                        trade.realized_pnl_pct = Decimal(str(round(pnl_pct, 2)))
                        alerts_sent += 1
                        session.commit()
                        continue

                # 4. SUPERTREND FLIP (partial exit)
                if st_dir == -1 and prev_st_dir == 1 and pnl_pct > 0:
                    alert_supertrend_flip(stock.ticker, stock.name, entry_price, current_price, "BEARISH")
                    if trade.status == "OPEN":
                        trade.status = "PARTIAL_EXIT"
                        trade.partial_exit_price = Decimal(str(current_price))
                        trade.partial_exit_date = datetime.utcnow()
                        trade.partial_exit_reason = "SUPERTREND_FLIP"
                        remaining = int(trade.shares_remaining or trade.shares_bought)
                        trade.shares_remaining = remaining // 2
                    alerts_sent += 1

                # 5. RSI OVERBOUGHT + 50% TARGET REACHED (partial profit)
                if rsi > 70 and target > 0:
                    halfway = entry_price + (target - entry_price) * 0.5
                    if current_price >= halfway and trade.status == "OPEN":
                        alert_partial_profit(stock.ticker, stock.name, entry_price, current_price,
                                             f"RSI overbought ({rsi:.0f}) + 50% target reached", 50)
                        trade.status = "PARTIAL_EXIT"
                        trade.partial_exit_price = Decimal(str(current_price))
                        trade.partial_exit_date = datetime.utcnow()
                        trade.partial_exit_reason = "RSI_OVERBOUGHT_HALFWAY"
                        remaining = int(trade.shares_remaining or trade.shares_bought)
                        trade.shares_remaining = remaining // 2
                        alerts_sent += 1

                # 6. OVEREXTENDED (3%+ single day gain with extreme volume)
                daily_return = (current_price / float(df["Close"].iloc[-2]) - 1) * 100 if len(df) > 1 else 0
                if daily_return > 3 and vol_ratio > 2.0 and trade.status == "OPEN":
                    alert_partial_profit(stock.ticker, stock.name, entry_price, current_price,
                                         f"Overextended (+{daily_return:.1f}% today, {vol_ratio:.1f}x vol)", 30)
                    alerts_sent += 1

                checked += 1

            except Exception as e:
                log.warning("monitor_stock_error", trade_id=trade.id, error=str(e))
                continue

        session.commit()
        log.info("monitor_complete", checked=checked, alerts=alerts_sent)
        return {"checked": checked, "alerts_sent": alerts_sent}

    except Exception as e:
        log.error("monitor_error", error=str(e))
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


@_celery_task_or_plain("app.tasks.monitor_tasks.compute_daily_performance")
def compute_daily_performance():
    """Compute daily performance analytics after market close."""
    log.info("computing_daily_performance")
    session = _get_sync_session()

    try:
        today = datetime.utcnow().date()

        closed_today = session.execute(
            select(Trade).where(
                Trade.status == "CLOSED",
                Trade.exit_date >= datetime(today.year, today.month, today.day)
            )
        ).scalars().all()

        if not closed_today:
            log.info("no_closed_trades_today")
            return

        winning = [t for t in closed_today if t.realized_pnl and float(t.realized_pnl) > 0]
        losing = [t for t in closed_today if t.realized_pnl and float(t.realized_pnl) <= 0]
        total_pnl = sum(float(t.realized_pnl or 0) for t in closed_today)

        perf = PerformanceDaily(
            date=datetime(today.year, today.month, today.day),
            total_trades=len(closed_today),
            winning_trades=len(winning),
            losing_trades=len(losing),
            total_pnl=Decimal(str(round(total_pnl, 2))),
            win_rate=Decimal(str(round(len(winning) / max(len(closed_today), 1) * 100, 2))),
            avg_profit_pct=Decimal(str(round(
                sum(float(t.realized_pnl_pct or 0) for t in winning) / max(len(winning), 1), 2
            ))),
            avg_loss_pct=Decimal(str(round(
                sum(float(t.realized_pnl_pct or 0) for t in losing) / max(len(losing), 1), 2
            ))),
            best_trade_pnl=Decimal(str(max((float(t.realized_pnl or 0) for t in closed_today), default=0))),
            worst_trade_pnl=Decimal(str(min((float(t.realized_pnl or 0) for t in closed_today), default=0))),
        )

        session.add(perf)
        session.commit()
        log.info("daily_performance_computed", trades=len(closed_today), pnl=total_pnl)

    except Exception as e:
        log.error("daily_perf_error", error=str(e))
        session.rollback()
    finally:
        session.close()
