"""SQLAlchemy ORM models for TradeSignal India v2."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey,
    JSON, Numeric, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    sector = Column(String(50))
    cap = Column(String(10))  # Large, Mid, Small
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    scan_results = relationship("ScanResult", back_populates="stock")
    trades = relationship("Trade", back_populates="stock")


class ScanResult(Base):
    __tablename__ = "scan_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String(36), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False)
    scan_date = Column(DateTime, default=datetime.utcnow, index=True)
    holding_mode = Column(String(10), default="weekly")

    current_price = Column(Numeric(12, 2))
    final_confidence = Column(Numeric(5, 1))
    final_signal = Column(String(20))
    base_score = Column(Numeric(5, 1))
    news_modifier = Column(Numeric(4, 1), default=0)
    ai_modifier = Column(Numeric(4, 1), default=0)

    entry_price = Column(Numeric(12, 2))
    target_price = Column(Numeric(12, 2))
    stop_loss = Column(Numeric(12, 2))
    risk_reward = Column(Numeric(5, 2))

    indicator_scores = Column(JSONB)
    sr_levels = Column(JSONB)
    ai_analysis = Column(Text)
    news_sentiment = Column(JSONB)

    created_at = Column(DateTime, default=datetime.utcnow)

    stock = relationship("Stock", back_populates="scan_results")
    trades = relationship("Trade", back_populates="scan_result")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_result_id = Column(Integer, ForeignKey("scan_results.id"))
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False)
    status = Column(String(20), default="OPEN", index=True)
    holding_mode = Column(String(10))

    entry_price = Column(Numeric(12, 2), nullable=False)
    entry_date = Column(DateTime, nullable=False)
    shares_bought = Column(Integer, nullable=False)
    allocated_amount = Column(Numeric(12, 2))

    original_target = Column(Numeric(12, 2))
    current_target = Column(Numeric(12, 2))
    original_stop_loss = Column(Numeric(12, 2))
    current_stop_loss = Column(Numeric(12, 2))

    shares_remaining = Column(Integer)
    partial_exit_price = Column(Numeric(12, 2))
    partial_exit_date = Column(DateTime)
    partial_exit_reason = Column(String(100))

    exit_price = Column(Numeric(12, 2))
    exit_date = Column(DateTime)
    exit_reason = Column(String(100))

    realized_pnl = Column(Numeric(12, 2))
    realized_pnl_pct = Column(Numeric(5, 2))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stock = relationship("Stock", back_populates="trades")
    scan_result = relationship("ScanResult", back_populates="trades")
    snapshots = relationship("PriceSnapshot", back_populates="trade")
    alerts = relationship("Alert", back_populates="trade")


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"))
    price = Column(Numeric(12, 2))
    rsi = Column(Numeric(5, 1))
    macd_hist = Column(Numeric(10, 4))
    supertrend_signal = Column(String(10))
    volume_ratio = Column(Numeric(5, 2))
    position_health = Column(Numeric(5, 1))
    snapshot_at = Column(DateTime, default=datetime.utcnow)

    trade = relationship("Trade", back_populates="snapshots")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=True)
    alert_type = Column(String(30), nullable=False)
    message = Column(Text)
    sent_via = Column(String(20), default="telegram")
    sent_at = Column(DateTime, default=datetime.utcnow)

    trade = relationship("Trade", back_populates="alerts")


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500))
    summary = Column(Text)
    source = Column(String(100))
    url = Column(String(500), unique=True)
    published_at = Column(DateTime, index=True)
    sentiment_polarity = Column(Numeric(4, 3))
    sentiment_label = Column(String(20))
    impact_level = Column(String(10))
    matched_stocks = Column(JSONB)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PerformanceDaily(Base):
    __tablename__ = "performance_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, unique=True, nullable=False)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pnl = Column(Numeric(12, 2), default=0)
    cumulative_pnl = Column(Numeric(12, 2), default=0)
    win_rate = Column(Numeric(5, 2), default=0)
    avg_profit_pct = Column(Numeric(5, 2), default=0)
    avg_loss_pct = Column(Numeric(5, 2), default=0)
    best_trade_pnl = Column(Numeric(12, 2))
    worst_trade_pnl = Column(Numeric(12, 2))
    computed_at = Column(DateTime, default=datetime.utcnow)
