# CLAUDE.md — TradeSignal India v2.3 Project Handoff

> **Upload this file at the start of any new Claude session to get full project context.**
> Last updated: 2 April 2026

---

## PROJECT OVERVIEW

**TradeSignal India v2.3** — AI-Powered NSE Equity Signal System
- Scans 140 NSE stocks with 15 technical indicators (127-point scoring model)
- **Smart single-stock scanner** — auto-analyzes weekly + monthly + trend, recommends hold duration
- **Budget picks** — suggests stocks under ₹500 for ₹15K-₹20K capital
- **Live prices** from Yahoo Finance `ticker.info` (not stale history close)
- LLM-first sentiment analysis (NVIDIA NIM Mistral Small 3.1 → VADER fallback → TextBlob)
- Auto-scan scheduler (Mon-Fri 10:30 AM IST, Wed 1 PM, Fri 3 PM, Sunday 6 PM)
- **Position monitor** — checks exit conditions every 15 min during market hours (no Celery needed)
- **Breaking news scanner** — checks for emergency exit triggers every 10 min
- Telegram bot with 16 commands including `/scanstock`, `/budgetpicks`, `/hindinews`
- React dark-mode trading dashboard with real-time scan progress
- Deployed as a **single Railway service** (FastAPI serves React + API from one URL)

**Owner:** Prateek (prateekk237)
**Live URL:** https://tradesignal-india-v2-production.up.railway.app
**GitHub:** https://github.com/prateekk237/tradesignal-india-v2 (branch: master)
**Railway:** Single service + PostgreSQL plugin (no Redis)

---

## WHAT WAS BUILT/FIXED IN v2.1–v2.3 SESSION

### Critical Bug Fixes
| Bug | Root Cause | Fix |
|-----|-----------|-----|
| `/api/scans/latest/summary` → 500 on every page load | `_active_scans[k]` KeyError — auto-scan IDs not in manual scans dict | Changed to `all_scans[k]` using merged dict |
| `/api/scans/progress/{id}` → undefined `all_scans` | Variable never defined in that scope | Added `_get_all_scans()` call |
| Auto-scan Telegram → `NoneType.__format__` crash | `target_price=None` passed to `f"₹{target:,.2f}"` | Added `if target else "N/A"` pattern everywhere |
| Single stock scan → 500 at 2 AM / market closed | Yahoo returns `NaN` for today's incomplete candle | `df.dropna(subset=["Close"])` + `_safe_float()` utility |
| Single stock scan → stale price (yesterday's close) | `history()` returns only completed candles | Added `get_live_price()` using `ticker.info["currentPrice"]` |
| 5 delisted tickers causing scan errors | TATAMOTORS, GMRINFRA, PEL, MCDOWELL-N, ZOMATO all 404 on Yahoo | Removed/replaced with working tickers |
| Exit alerts / position monitor NEVER ran | All in `@celery_app.task` — no Redis configured | Converted to plain functions, run in background thread |
| Telegram `/scan` silently failed | Tried to use Celery `.delay()` which doesn't exist | Now runs `run_full_scan()` directly in thread |

### New Features Built
| Feature | Where | Description |
|---------|-------|-------------|
| **Smart single stock scan** | `/api/scan/stock/{ticker}`, Telegram `/scanstock`, Frontend Scan page | Auto-analyzes weekly + monthly + 6-month trend, recommends hold duration (1-2 weeks / 1-2 months / 3-6 months / WAIT) |
| **Budget picks** | `/api/budget-picks`, Telegram `/budgetpicks`, Frontend Scan page | Filters BUY signals under ₹500, allocates for ₹15K-₹20K budget, shows shares to buy |
| **Ticker aliases** | `stock_universe.py` `resolve_ticker()` | 81 aliases: RTN→RTNINDIA, SBI→SBIN, NALCO→NATIONALUM, ZOMATO→ETERNAL, etc. |
| **Position monitor thread** | `auto_scheduler.py` → `_monitor_loop()` | Checks 6 exit conditions every 15 min during market hours — no Celery needed |
| **Breaking news monitor** | `auto_scheduler.py` → `_run_news_monitor()` | Scans for emergency exit triggers every 10 min |
| **Live price** | `scanner.py` → `get_live_price()` | Uses `ticker.info["currentPrice"]` for real-time price instead of stale `history()` close |
| **ATR-based targets** | `scoring.py` → `compute_entry_exit()` | Weekly: 3.5× ATR target, min 5%, min 1:2 R:R. Monthly: 5× ATR, min 8%, min 1:2.5 R:R |
| **News with stock impact** | `/api/news`, News.tsx, Telegram `/news` | Each headline shows sentiment arrow, impact level (HIGH/MEDIUM/LOW), affected stock tickers |
| **Improved /sectors** | Telegram command | Shows actual stock names per sector + BUY signal count from latest scan |
| **Low-price stocks** | `stock_universe.py` | Added RTNPOWER (₹7), RPOWER (₹20), RTNINDIA (₹25), HFCL (₹68), NBCC (₹78), IREDA (₹109) |

### Profitability Improvements
| Change | Before | After |
|--------|--------|-------|
| Weekly target | ~2% (e.g., ₹390→₹397) | 5-15% (ATR-based, e.g., ₹386→₹446) |
| Monthly target | ~3% | 8-25% |
| Min R:R ratio weekly | None (was ~0.3:1) | 1:2 enforced |
| Min R:R ratio monthly | None | 1:2.5 enforced |
| Scan timing | 9:20 AM (opening chaos) | 10:30 AM (after volatility settles) |
| Hold duration | User guesses weekly/monthly | System auto-recommends based on multi-timeframe analysis |

---

## TECH STACK

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn, SQLAlchemy (async), structlog |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand, TanStack Query, Axios |
| Database | PostgreSQL (Railway plugin, asyncpg driver) |
| AI/LLM | NVIDIA NIM API (Mistral Small 3.1 24B) via OpenAI SDK |
| Sentiment | VADER (60+ Indian financial terms) + TextBlob (last resort) |
| Stock Data | yfinance (Yahoo Finance — history + live price via ticker.info), ta library for indicators |
| News | 8 Indian RSS feeds (ET, Moneycontrol, LiveMint, BS, NDTV Profit, etc.) |
| Telegram | python-telegram-bot (polling mode) |
| Deploy | Docker multi-stage (Node builds React → Python serves all), Railway |

---

## FILE STRUCTURE

```
repo-root/
├── Dockerfile                    # Multi-stage: Node + Python
├── requirements.txt              # Python dependencies
├── CLAUDE.md                     # THIS FILE — project handoff
├── app/                          # Python backend
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, all routes, SPA serving, startup
│   ├── config.py                 # Pydantic settings from env vars
│   ├── database.py               # Async SQLAlchemy (graceful when DB unavailable)
│   ├── models/__init__.py        # 8 SQLAlchemy models
│   ├── schemas/__init__.py       # 9 Pydantic request/response schemas
│   ├── engine/
│   │   ├── indicators.py         # 15 technical indicator calculations
│   │   ├── scoring.py            # 127-point scoring model, ATR-based entry/exit
│   │   ├── scanner.py            # Full scan orchestrator + smart single stock + live price
│   │   └── stock_universe.py     # 140 NSE stocks + 81 aliases + resolve_ticker()
│   ├── sentiment/
│   │   └── analyzer.py           # LLM→VADER→TextBlob pipeline, rate limiter, RSS
│   ├── integrations/
│   │   ├── telegram_bot.py       # 9 alert message templates (None-safe)
│   │   └── telegram_commands.py  # 16 bot commands including /scanstock, /budgetpicks
│   ├── routers/
│   │   └── trades.py             # Trade CRUD endpoints (create, close, partial exit, performance)
│   └── tasks/
│       ├── auto_scheduler.py     # Background scheduler + position monitor + news monitor
│       ├── monitor_tasks.py      # 6 exit conditions (works without Celery)
│       ├── news_tasks.py         # Breaking news scanner (works without Celery)
│       ├── celery_app.py         # Celery config (optional, for future Redis)
│       └── scan_tasks.py         # Scan task wrappers
└── frontend/                     # React app
    ├── src/
    │   ├── App.tsx               # Router, sidebar, SystemLogs, StatusBar
    │   ├── api/client.ts         # Axios client + scanSingleStock + fetchBudgetPicks
    │   ├── store/useAppStore.ts  # Zustand global state
    │   ├── lib/types.ts          # TypeScript interfaces
    │   ├── pages/
    │   │   ├── Dashboard.tsx     # Overview with market sentiment
    │   │   ├── Scan.tsx          # Smart single stock scan + budget picks + full scan
    │   │   ├── Portfolio.tsx     # Allocation calculator
    │   │   ├── Screener.tsx      # Stock screener/filter
    │   │   ├── News.tsx          # News feed with impact badges + affected stocks
    │   │   ├── TradeHistory.tsx  # ⚠️ PLACEHOLDER — needs to be built
    │   │   └── Settings.tsx      # Config display
    │   └── components/widgets/
    │       ├── SystemLogs.tsx    # Real-time REST/WS log viewer
    │       └── StatusBar.tsx     # Bottom status strip
    └── ...config files
```

---

## API ENDPOINTS

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (JSON) |
| GET | `/api/settings` | App config + DB status |
| GET | `/api/stocks` | List stocks (DB or in-memory fallback) |
| GET | `/api/stocks/sectors` | List 33 sectors |
| **GET** | **`/api/scan/stock/{ticker}`** | **Smart single stock scan — auto-recommends hold duration** |
| **GET** | **`/api/budget-picks?budget=20000`** | **Budget stock picks for small capital** |
| POST | `/api/scans` | Trigger background scan → returns scan_id |
| GET | `/api/scans/progress/{id}` | Real-time scan progress |
| GET | `/api/scans/{id}` | Full scan results |
| GET | `/api/scans/{id}/signals` | BUY signals only |
| GET | `/api/scans/latest/summary` | Most recent scan summary |
| GET | `/api/auto-scan/status` | Auto-scheduler status + next scan time |
| GET | `/api/news` | RSS news with sentiment + impact + affected stocks |
| GET | `/api/news/sentiment` | Market sentiment (LLM pipeline) |
| POST | `/api/portfolio/allocate` | Confidence-weighted allocation |
| POST | `/api/trades` | Create trade |
| GET | `/api/trades` | List trades |
| GET | `/api/trades/open` | Open positions |
| PUT | `/api/trades/{id}/close` | Close trade with P&L |
| PUT | `/api/trades/{id}/partial-exit` | Partial profit booking |
| GET | `/api/trades/performance` | Win rate, P&L analytics |
| WS | `/ws/updates` | WebSocket for live updates |

---

## TELEGRAM BOT COMMANDS

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | All commands |
| `/news` | Latest 10 headlines with sentiment arrows + impact |
| `/hindinews` | Hindi translation + stock impact via LLM (30s timeout, VADER fallback) |
| `/sentiment` | Full AI sentiment analysis |
| **`/scanstock NALCO`** | **Smart scan — weekly + monthly + trend → recommended hold duration** |
| **`/budgetpicks 15000`** | **Best affordable stocks for your budget** |
| `/signals` | Latest BUY signals from scan |
| `/status` | Open positions & P&L |
| `/portfolio` | Current allocation (₹20K default) |
| `/stock RELIANCE` | Quick stock lookup with latest scan data |
| `/scan` | Trigger full market scan (3-10 min) |
| `/autoscan` | Auto-scan schedule & status |
| `/sectors` | Sector breakdown with stock names + BUY counts |
| `/alerts on/off` | Toggle notifications |

---

## AUTO-SCAN SCHEDULE (IST)

| Day | Time | Scope | AI | Purpose |
|-----|------|-------|-----|---------|
| Mon-Fri | 10:30 AM | All 140 stocks | ✅ ON | Morning scan (after opening noise) |
| Wednesday | 1:00 PM | All stocks | ✅ ON | Mid-week fresh setups |
| Friday | 3:00 PM | Large Cap | ❌ OFF | Weekend watchlist prep |
| Sunday | 6:00 PM | All stocks | ✅ ON | Weekly preview |

---

## POSITION MONITORING (Background Thread — No Redis Needed)

Runs every **15 minutes** during market hours (9:15 AM - 3:45 PM IST, Mon-Fri).

### 6 Exit Conditions Checked:
1. **Target hit** → auto-close + Telegram alert
2. **Stop-loss hit** → auto-close + Telegram alert
3. **Trailing stop** → ATR-based stop that only moves up, triggers if reversed
4. **SuperTrend flip** → bearish flip triggers 50% partial exit
5. **RSI overbought + 50% target** → partial profit booking alert
6. **Overextended** (+3% single day + 2x volume) → partial profit alert

### Breaking News Scanner (every 10 min):
- Matches news against open positions
- HIGH impact negative news (fraud, SEBI ban, default) → emergency exit alert
- MEDIUM impact negative → partial profit alert

**⚠️ IMPORTANT:** These monitors require trades to be entered in the DB. Currently the frontend Trade History page is a placeholder — trades must be created via API (`POST /api/trades`).

---

## SMART HOLD DURATION LOGIC

When scanning a single stock, the system analyzes 3 dimensions:

| Dimension | How |
|-----------|-----|
| Weekly signal | `analyze_single_stock(mode="weekly")` — 3mo data, weekly ATR targets |
| Monthly signal | `analyze_single_stock(mode="monthly")` — 6mo data, monthly ATR targets |
| Long-term trend | 6mo data: price vs SMA20, SMA50, SMA100 + SMA20>SMA50 alignment |

**Recommendation matrix:**
| Condition | Hold Duration |
|-----------|---------------|
| Weekly ≥70% + Monthly ≥65% + Trend ≥3/4 | 2-4 weeks |
| Monthly ≥65% + Trend ≥3/4 | 1-2 months |
| Trend ≥4/4 + Monthly ≥55% | 3-6 months |
| Only Weekly ≥65% | 1-2 weeks |
| Only Monthly ≥60% | 2-4 weeks |
| All weak | WAIT — no clear entry |

---

## ENVIRONMENT VARIABLES (Railway)

```
CORS_ORIGINS=*
DATABASE_URL=postgresql://postgres:xxx@postgres.railway.internal:5432/railway
DATABASE_URL_SYNC=postgresql://postgres:xxx@mainline.proxy.rlwy.net:22583/railway
DEBUG=false
ENVIRONMENT=production
NIM_API_KEY=nvapi-xxx
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NIM_MODEL=mistralai/mistral-small-3.1-24b-instruct-2503
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

---

## KNOWN ISSUES & THINGS NOT YET BUILT

### ⚠️ Trade History Page — PLACEHOLDER
`frontend/src/pages/TradeHistory.tsx` is a placeholder showing "coming in Sprint 6". The backend API (`/api/trades`, `/api/trades/performance`) is fully functional, but the frontend doesn't call it. **This needs to be built** to show:
- List of all trades (open + closed)
- Entry/exit prices, P&L per trade
- Win rate, cumulative P&L chart
- Signal accuracy tracking

### ⚠️ DB Trade Lifecycle Not Connected to Frontend
- The DB models (Trade, PriceSnapshot, PerformanceDaily) exist
- The API endpoints (create, close, partial-exit, performance) work
- The position monitor checks these trades for exit conditions
- **BUT** the frontend has no "Enter Trade" or "Close Trade" buttons
- Currently trades can only be created via API or Telegram

### ⚠️ Hindi News LLM Timeout
- NVIDIA NIM free tier often times out (30s+) for translation
- Fallback shows English with VADER sentiment arrows
- Reducing headlines to 5 helps but doesn't eliminate timeouts
- Consider: paid NIM tier, or use a lighter model, or client-side translation

### ⚠️ Some Stocks May Still 404 on Yahoo
- Yahoo Finance periodically changes ticker symbols for NSE
- ZOMATO became ETERNAL in late 2025
- If new 404s appear in Railway logs, update `stock_universe.py`
- The `_safe_float()` and `get_live_price()` functions handle errors gracefully

### ⚠️ Full Market Scan Takes 10-30 Minutes
- 140 stocks × LLM calls = slow (NVIDIA rate limit 25/min)
- With AI OFF, scan takes ~3-5 minutes
- With AI ON, 15-30 minutes depending on NIM responsiveness

---

## QUICK REFERENCE — File to Edit for Common Tasks

| Task | File(s) |
|------|---------|
| Add new stock to universe | `app/engine/stock_universe.py` (STOCK_UNIVERSE dict + TICKER_ALIASES) |
| Fix broken Yahoo ticker | `app/engine/stock_universe.py` |
| Change scoring weights | `app/engine/scoring.py` |
| Change ATR target multipliers | `app/engine/scoring.py` → `compute_entry_exit()` |
| Change hold duration logic | `app/main.py` → `scan_single_stock()` AND `telegram_commands.py` → `cmd_scanstock()` |
| Change auto-scan schedule | `app/tasks/auto_scheduler.py` → `_scheduler_loop()` |
| Add new Telegram command | `app/integrations/telegram_commands.py` (add handler + register in `create_bot_application`) |
| Add exit condition | `app/tasks/monitor_tasks.py` → `monitor_open_positions()` |
| Change LLM model | `app/config.py` (NIM_MODEL) + Railway ENV |
| Add RSS news source | `app/sentiment/analyzer.py` (NEWS_RSS_FEEDS) |
| Fix NaN/price issues | `app/engine/scanner.py` → `_safe_float()`, `get_live_price()` |
| **Build Trade History page** | `frontend/src/pages/TradeHistory.tsx` + `frontend/src/api/client.ts` |
| **Add "Enter Trade" button** | `frontend/src/pages/Scan.tsx` (after BUY signal results) |

---

## FUTURE ENHANCEMENTS (Priority Order)

### Sprint 6 — Trade Lifecycle (HIGH PRIORITY)
- [ ] Build TradeHistory.tsx frontend — fetch from `/api/trades` and `/api/trades/performance`
- [ ] Add "Enter Trade" button on BUY signals (calls `POST /api/trades`)
- [ ] Add "Close Trade" / "Partial Exit" buttons on open positions
- [ ] Show real-time P&L using live prices
- [ ] Daily P&L snapshot chart (data already in `PerformanceDaily` model)

### Sprint 7 — Accuracy & Backtesting
- [ ] Track signal accuracy: was the BUY signal profitable after the recommended hold?
- [ ] Backtesting engine against 6-month historical data
- [ ] Show accuracy metrics on Dashboard (win rate, avg profit, Sharpe ratio)
- [ ] A/B test: compare results with AI ON vs AI OFF

### Sprint 8 — Advanced Features
- [ ] Price alerts via Telegram when target/stop-loss hit for watched stocks
- [ ] Options chain data integration (PCR, max pain levels)
- [ ] FII/DII daily flow data from NSE (use `nsepython` library)
- [ ] Delivery percentage filter (>50% = genuine buying)
- [ ] Custom stock universe (add/remove stocks from dashboard)

### Sprint 9 — Scale
- [ ] Celery workers with Redis (for heavier background processing)
- [ ] Multi-user support with authentication
- [ ] Mobile-responsive improvements
- [ ] Email alerts as alternative to Telegram

---

## HOW TO DEPLOY

### Push to Railway (auto-deploys):
```bash
cd tradesignal-india-v2-FINAL
git init
git remote add origin https://github.com/prateekk237/tradesignal-india-v2.git
git add -A
git commit -m "v2.3: Smart hold duration, live prices, exit monitor, budget picks"
git branch -M master
git push -f origin master
```

### Verify deployment:
1. Dashboard loads: `https://tradesignal-india-v2-production.up.railway.app`
2. Health check: `/health` → `{"status":"ok"}`
3. Stocks API: `/api/stocks` → JSON list with IDs (DB connected)
4. Single stock: `/api/scan/stock/NALCO` → live price + recommendation
5. Railway logs show: `database_tables_created`, `telegram_bot_started`, `auto_scheduler_thread_started`, `position_monitor_thread_started`
6. Telegram: `/scanstock NALCO` → smart analysis with hold duration

### Common TypeScript gotchas:
- Use `(value?.length ?? 0) > 0` not `value?.length > 0`
- All store setters need explicit types: `(v: boolean) => ...`
- Import all new API functions in the file that uses them
