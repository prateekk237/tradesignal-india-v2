"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class StockOut(BaseModel):
    id: int
    ticker: str
    name: str
    sector: Optional[str]
    cap: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class ScanRequest(BaseModel):
    scope: str = Field(default="all", description="all|large|mid|small|sector")
    sectors: list[str] = Field(default=[], description="Filter sectors when scope=sector")
    mode: str = Field(default="weekly", description="weekly|monthly")
    use_ai: bool = Field(default=True, description="Enable NVIDIA NIM AI analysis")
    min_confidence: float = Field(default=65.0)
    max_positions: int = Field(default=5)
    capital: float = Field(default=100000.0)


class ScanResultOut(BaseModel):
    ticker: str
    name: str
    sector: str
    cap: str
    current_price: float
    final_confidence: float
    final_signal: str
    base_confidence: float
    news_modifier: float
    ai_modifier: float
    entry_exit: dict
    sr_levels: dict
    indicator_scores: Optional[dict] = None
    news_sentiment: Optional[dict] = None
    ai_data: Optional[dict] = None
    holding_mode: str


class ScanSummaryOut(BaseModel):
    scan_id: str
    scan_date: str
    mode: str
    scope: str
    total_stocks: int
    analyzed: int
    errors: int
    buy_signals_count: int
    results: list[ScanResultOut]


class TradeCreate(BaseModel):
    scan_result_id: Optional[int] = None
    stock_ticker: str
    entry_price: float
    shares_bought: int
    allocated_amount: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    holding_mode: str = "weekly"


class TradeOut(BaseModel):
    id: int
    stock_ticker: str
    stock_name: str
    status: str
    entry_price: float
    entry_date: datetime
    shares_bought: int
    shares_remaining: Optional[int]
    current_target: Optional[float]
    current_stop_loss: Optional[float]
    exit_price: Optional[float]
    exit_date: Optional[datetime]
    exit_reason: Optional[str]
    realized_pnl: Optional[float]
    realized_pnl_pct: Optional[float]
    holding_mode: str

    class Config:
        from_attributes = True


class PortfolioAllocRequest(BaseModel):
    capital: float
    candidates: list[dict]
    max_positions: int = 5
    min_confidence: float = 65.0


class SettingsUpdate(BaseModel):
    nim_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    default_capital: Optional[float] = None
    default_min_confidence: Optional[float] = None
    default_holding_mode: Optional[str] = None


class HealthOut(BaseModel):
    status: str
    version: str
    timestamp: str
