"""Trades API — Create, update, close trades with P&L tracking."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from decimal import Decimal
from datetime import datetime

from app.database import get_db
from app.models import Trade, Stock, PerformanceDaily
from app.schemas import TradeCreate, TradeOut

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.post("")
async def create_trade(req: TradeCreate, db: AsyncSession = Depends(get_db)):
    """Record a new trade entry."""
    # Look up stock
    result = await db.execute(select(Stock).where(Stock.ticker == req.stock_ticker))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {req.stock_ticker} not found")

    trade = Trade(
        scan_result_id=req.scan_result_id,
        stock_id=stock.id,
        status="OPEN",
        holding_mode=req.holding_mode,
        entry_price=Decimal(str(req.entry_price)),
        entry_date=datetime.utcnow(),
        shares_bought=req.shares_bought,
        shares_remaining=req.shares_bought,
        allocated_amount=Decimal(str(req.allocated_amount)),
        original_target=Decimal(str(req.target_price)) if req.target_price else None,
        current_target=Decimal(str(req.target_price)) if req.target_price else None,
        original_stop_loss=Decimal(str(req.stop_loss)) if req.stop_loss else None,
        current_stop_loss=Decimal(str(req.stop_loss)) if req.stop_loss else None,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    return {"id": trade.id, "status": "OPEN", "ticker": req.stock_ticker}


@router.get("")
async def list_trades(
    status: str = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List trades with optional status filter."""
    query = select(Trade, Stock).join(Stock, Trade.stock_id == Stock.id)
    if status:
        query = query.where(Trade.status == status)
    query = query.order_by(Trade.created_at.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "id": trade.id,
            "stock_ticker": stock.ticker,
            "stock_name": stock.name,
            "status": trade.status,
            "holding_mode": trade.holding_mode,
            "entry_price": float(trade.entry_price),
            "entry_date": trade.entry_date.isoformat() if trade.entry_date else None,
            "shares_bought": trade.shares_bought,
            "shares_remaining": trade.shares_remaining,
            "current_target": float(trade.current_target) if trade.current_target else None,
            "current_stop_loss": float(trade.current_stop_loss) if trade.current_stop_loss else None,
            "exit_price": float(trade.exit_price) if trade.exit_price else None,
            "exit_date": trade.exit_date.isoformat() if trade.exit_date else None,
            "exit_reason": trade.exit_reason,
            "realized_pnl": float(trade.realized_pnl) if trade.realized_pnl else None,
            "realized_pnl_pct": float(trade.realized_pnl_pct) if trade.realized_pnl_pct else None,
            "sector": stock.sector,
            "cap": stock.cap,
        }
        for trade, stock in rows
    ]


@router.get("/open")
async def get_open_trades(db: AsyncSession = Depends(get_db)):
    """Get all open positions."""
    query = (
        select(Trade, Stock)
        .join(Stock, Trade.stock_id == Stock.id)
        .where(Trade.status.in_(["OPEN", "PARTIAL_EXIT"]))
        .order_by(Trade.entry_date.desc())
    )
    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "id": trade.id,
            "ticker": stock.ticker,
            "name": stock.name,
            "sector": stock.sector,
            "status": trade.status,
            "entry_price": float(trade.entry_price),
            "entry_date": trade.entry_date.isoformat(),
            "shares_remaining": trade.shares_remaining or trade.shares_bought,
            "target": float(trade.current_target) if trade.current_target else None,
            "stop_loss": float(trade.current_stop_loss) if trade.current_stop_loss else None,
            "holding_mode": trade.holding_mode,
        }
        for trade, stock in rows
    ]


@router.put("/{trade_id}/partial-exit")
async def partial_exit(trade_id: int, exit_price: float, shares_to_sell: int,
                       reason: str = "manual", db: AsyncSession = Depends(get_db)):
    """Record a partial exit on a trade."""
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Trade already closed")

    remaining = trade.shares_remaining or trade.shares_bought
    if shares_to_sell > remaining:
        raise HTTPException(status_code=400, detail=f"Can't sell {shares_to_sell}, only {remaining} remaining")

    trade.status = "PARTIAL_EXIT"
    trade.partial_exit_price = Decimal(str(exit_price))
    trade.partial_exit_date = datetime.utcnow()
    trade.partial_exit_reason = reason
    trade.shares_remaining = remaining - shares_to_sell
    trade.updated_at = datetime.utcnow()

    await db.commit()
    return {"status": "PARTIAL_EXIT", "shares_remaining": trade.shares_remaining}


@router.put("/{trade_id}/close")
async def close_trade(trade_id: int, exit_price: float, reason: str = "manual",
                      db: AsyncSession = Depends(get_db)):
    """Close a trade (full exit)."""
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Trade already closed")

    shares = trade.shares_remaining or trade.shares_bought
    entry = float(trade.entry_price)
    pnl = (exit_price - entry) * shares
    pnl_pct = (exit_price - entry) / entry * 100

    trade.status = "CLOSED"
    trade.exit_price = Decimal(str(exit_price))
    trade.exit_date = datetime.utcnow()
    trade.exit_reason = reason
    trade.shares_remaining = 0
    trade.realized_pnl = Decimal(str(round(pnl, 2)))
    trade.realized_pnl_pct = Decimal(str(round(pnl_pct, 2)))
    trade.updated_at = datetime.utcnow()

    await db.commit()
    return {
        "status": "CLOSED",
        "exit_price": exit_price,
        "realized_pnl": round(pnl, 2),
        "realized_pnl_pct": round(pnl_pct, 2),
    }


@router.get("/performance")
async def get_performance(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Get trade performance analytics."""
    # Closed trades stats
    closed = await db.execute(
        select(Trade).where(Trade.status == "CLOSED").order_by(Trade.exit_date.desc()).limit(100)
    )
    trades = closed.scalars().all()

    if not trades:
        return {
            "total_trades": 0, "win_rate": 0, "total_pnl": 0,
            "avg_profit": 0, "avg_loss": 0, "best_trade": 0, "worst_trade": 0,
        }

    winners = [t for t in trades if t.realized_pnl and float(t.realized_pnl) > 0]
    losers = [t for t in trades if t.realized_pnl and float(t.realized_pnl) <= 0]
    total_pnl = sum(float(t.realized_pnl or 0) for t in trades)

    return {
        "total_trades": len(trades),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate": round(len(winners) / max(len(trades), 1) * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_profit_pct": round(
            sum(float(t.realized_pnl_pct or 0) for t in winners) / max(len(winners), 1), 2
        ),
        "avg_loss_pct": round(
            sum(float(t.realized_pnl_pct or 0) for t in losers) / max(len(losers), 1), 2
        ),
        "best_trade": max((float(t.realized_pnl or 0) for t in trades), default=0),
        "worst_trade": min((float(t.realized_pnl or 0) for t in trades), default=0),
    }
