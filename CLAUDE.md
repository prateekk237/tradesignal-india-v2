# CLAUDE.md — TradeSignal India v2.0 Project Handoff

> **Upload this file at the start of any new Claude session to get full project context.**
> Last updated: 30 March 2026

---

## PROJECT OVERVIEW

**TradeSignal India v2.0** — AI-Powered NSE Equity Signal System
- Scans 131 NSE stocks with 15 technical indicators (127-point scoring model)
- LLM-first sentiment analysis (NVIDIA NIM Mistral Small 3.1 → VADER fallback → TextBlob)
- Auto-scan scheduler (Mon-Fri 9:20 AM IST, 1 PM, Sunday 6 PM)
- Telegram bot with 13 commands including Hindi news translation
- React dark-mode trading dashboard with real-time scan progress
- Deployed as a **single Railway service** (FastAPI serves React + API from one URL)

**Owner:** Prateek (prateekk237)
**Live URL:** https://tradesignal-india-v2-production.up.railway.app
**GitHub:** https://github.com/prateekk237/tradesignal-india-v2 (branch: master)
**Railway:** Single service + PostgreSQL plugin (no Redis)

---

## TECH STACK

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn, SQLAlchemy (async), structlog |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand, TanStack Query, Axios |
| Database | PostgreSQL (Railway plugin, asyncpg driver) |
| AI/LLM | NVIDIA NIM API (Mistral Small 3.1 24B) via OpenAI SDK |
| Sentiment | VADER (60+ Indian financial terms) + TextBlob (last resort) |
| Stock Data | yfinance (Yahoo Finance), ta library for indicators |
| News | 8 Indian RSS feeds (ET, Moneycontrol, LiveMint, BS, NDTV Profit, etc.) |
| Telegram | python-telegram-bot (polling mode) |
| Deploy | Docker multi-stage (Node builds React → Python serves all), Railway |

---

## ARCHITECTURE (Single Service)

```
Railway Service (one Dockerfile)
├── Stage 1: Node builds React → /frontend/dist
├── Stage 2: Python copies dist → /app/static
└── FastAPI serves BOTH:
    ├── /api/*          → API endpoints (JSON)
    ├── /health         → Health check
    ├── /docs           → Swagger UI
    ├── /ws/updates     → WebSocket
    ├── /               → React index.html
    ├── /scan, /news    → React SPA routes (404 handler → index.html)
    └── /assets/*       → Static JS/CSS bundles
```

**Key design decision:** SPA catch-all uses `@app.exception_handler(404)` NOT `@app.get("/{path:path}")` — the latter steals API routes.

---

## FILE STRUCTURE

```
repo-root/
├── Dockerfile                    # Multi-stage: Node + Python
├── .dockerignore                 # Excludes frontend/node_modules, NOT frontend/
├── .gitignore
├── .env.example
├── requirements.txt              # Python dependencies
├── README.md
├── app/                          # Python backend
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, all routes, SPA serving, startup
│   ├── config.py                 # Pydantic settings from env vars
│   ├── database.py               # Async SQLAlchemy (graceful when DB unavailable)
│   ├── models/__init__.py        # 8 SQLAlchemy models
│   ├── schemas/__init__.py       # 9 Pydantic request/response schemas
│   ├── engine/
│   │   ├── indicators.py         # 15 technical indicator calculations
│   │   ├── scoring.py            # 127-point scoring model, signal classification
│   │   ├── scanner.py            # Full scan orchestrator with progress callback
│   │   └── stock_universe.py     # 131 NSE stocks with sector/cap classification
│   ├── sentiment/
│   │   └── analyzer.py           # LLM→VADER→TextBlob pipeline, rate limiter, RSS
│   ├── integrations/
│   │   ├── telegram_bot.py       # 9 alert message templates
│   │   └── telegram_commands.py  # 13 bot commands including /hindinews
│   ├── routers/
│   │   └── trades.py             # Trade CRUD endpoints
│   └── tasks/
│       ├── auto_scheduler.py     # Background thread scheduler (no Redis needed)
│       ├── celery_app.py         # Celery config (for future Redis deployment)
│       ├── monitor_tasks.py      # Position monitoring tasks
│       ├── news_tasks.py         # Breaking news scanner
│       └── scan_tasks.py         # Weekly scan tasks
└── frontend/                     # React app
    ├── Dockerfile                # Standalone nginx (NOT USED in prod — backend serves)
    ├── package.json
    ├── index.html
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── tsconfig.json
    └── src/
        ├── main.tsx              # React entry point
        ├── App.tsx               # Router, sidebar, SystemLogs, StatusBar
        ├── index.css             # Dark mode CSS, form controls, glass cards
        ├── api/client.ts         # Axios client, all API functions
        ├── store/useAppStore.ts  # Zustand global state
        ├── lib/types.ts          # TypeScript interfaces
        ├── lib/utils.ts          # Helpers (formatINR, confidenceColor, etc.)
        ├── pages/
        │   ├── Dashboard.tsx     # Overview with market sentiment
        │   ├── Scan.tsx          # Scanner with live progress polling
        │   ├── Portfolio.tsx     # Allocation calculator
        │   ├── Screener.tsx      # Stock screener/filter
        │   ├── News.tsx          # News feed with AI sentiment arrows
        │   ├── TradeHistory.tsx  # Trade log (placeholder)
        │   └── Settings.tsx      # Config display
        └── components/widgets/
            ├── SystemLogs.tsx    # Real-time REST/WS log viewer
            └── StatusBar.tsx     # Bottom status strip
```

---

## API ENDPOINTS

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (JSON) |
| GET | `/api/settings` | App config + DB status |
| GET | `/api/stocks` | List stocks (DB or in-memory fallback) |
| GET | `/api/stocks/sectors` | List 33 sectors |
| POST | `/api/scans` | Trigger background scan → returns scan_id |
| GET | `/api/scans/progress/{id}` | Real-time scan progress (polled by frontend) |
| GET | `/api/scans/{id}` | Full scan results |
| GET | `/api/scans/{id}/signals` | BUY signals only |
| GET | `/api/scans/latest/summary` | Most recent scan summary |
| GET | `/api/auto-scan/status` | Auto-scheduler status + next scan time |
| GET | `/api/news` | RSS news with per-article VADER scores |
| GET | `/api/news/sentiment` | Market sentiment (LLM pipeline) |
| POST | `/api/portfolio/allocate` | Confidence-weighted allocation |
| POST | `/api/trades` | Create trade |
| GET | `/api/trades` | List trades |
| WS | `/ws/updates` | WebSocket for live updates |
| GET | `/docs` | Swagger UI |

---

## 15 TECHNICAL INDICATORS (127-point model)

| # | Indicator | Max Score | Source |
|---|-----------|-----------|--------|
| 1 | RSI (14) | 12 | ta library |
| 2 | MACD + Signal + Histogram | 12 | ta |
| 3 | Moving Averages (SMA 10/20/50) | 10 | pandas |
| 4 | Bollinger Bands %B | 8 | ta |
| 5 | Volume Ratio | 10 | pandas |
| 6 | Stochastic %K | 7 | ta |
| 7 | ADX (trend strength) | 8 | ta |
| 8 | Support/Resistance (R:R ratio) | 10 | custom pivots |
| 9 | Momentum (ROC) | 5 | pandas |
| 10 | VWAP distance | 8 | custom |
| 11 | SuperTrend | 8 | custom ATR-based |
| 12 | Ichimoku Cloud | 10 | custom |
| 13 | Fibonacci Retracement | 7 | custom |
| 14 | EMA Ribbon (8/13/21/34/55) | 5 | pandas |
| 15 | Relative Strength vs Nifty 50 | 7 | custom |
| | **TOTAL** | **127** | normalized to 0-100 |

Volume gate: if volume < average, confidence capped at 65%.

Signal classification:
- ≥75%: STRONG BUY
- ≥60%: BUY
- ≥45%: HOLD / NEUTRAL
- ≥30%: SELL
- <30%: STRONG SELL

---

## SENTIMENT PIPELINE

```
LLM (Mistral Small 3.1 via NVIDIA NIM)    ← Primary (deep analysis + reasoning)
    ↓ fails/429?
VADER (60+ Indian financial custom terms)  ← Fallback #1 (fast, reliable)
    ↓ fails?
TextBlob                                   ← Fallback #2 (basic)
```

**Rate limiter:** 25 calls/min max (NVIDIA free tier = 40 RPM). Auto-retry on 429 with 3s→6s→9s backoff.
**News cache:** RSS results cached for 2 minutes.
**Per-article scoring:** Each news article gets a VADER sentiment arrow (▲/▼) on the frontend.

---

## AUTO-SCAN SCHEDULE (IST)

| Day | Time | Scope | AI | Telegram Alert |
|-----|------|-------|-----|----------------|
| Mon-Fri | 9:20 AM | All 131 stocks | ✅ ON | ✅ Full results |
| Mon-Fri | 1:00 PM | Large Cap only | ❌ OFF | ✅ Quick summary |
| Sunday | 6:00 PM | All 131 stocks | ✅ ON | ✅ Weekly preview |

Runs as a background thread in the same process (no Redis/Celery needed). Results stored in memory + sent to Telegram + available on dashboard.

---

## TELEGRAM BOT COMMANDS

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | All commands |
| `/news` | Latest 10 headlines (English) |
| `/hindinews` | News translated to Hindi via LLM |
| `/sentiment` | Full AI sentiment analysis |
| `/signals` | Latest BUY signals |
| `/status` | Open positions |
| `/portfolio` | Current allocation |
| `/stock RELIANCE` | Quick stock lookup |
| `/scan` | Trigger manual scan |
| `/autoscan` | Auto-scan schedule & next scan time |
| `/sectors` | Sector breakdown |
| `/alerts on/off` | Toggle notifications |

---

## ENVIRONMENT VARIABLES (Railway)

```
CORS_ORIGINS=*
DATABASE_URL=postgresql://postgres:xxx@postgres.railway.internal:5432/railway
DATABASE_URL_SYNC=postgresql://postgres:xxx@mainline.proxy.rlwy.net:22583/railway
DEBUG=false
ENVIRONMENT=production
NIM_API_KEY=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
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NIM_MODEL=mistralai/mistral-small-3.1-24b-instruct-2503
TELEGRAM_BOT_TOKEN=8063104992:AAHMupQ_2Do-5QJBUohUXeF5ZRX54-Z0D8Y
TELEGRAM_CHAT_ID=1027802442
```

**IMPORTANT:** No quotes around values in Railway. Railway auto-injects `PORT=8080`.

---

## RAILWAY DEPLOYMENT NOTES

- **Root Directory:** BLANK (files are at repo root)
- **Builder:** Dockerfile (auto-detected)
- **Single service** serves both frontend + backend
- `database.py` gracefully handles missing DB (engine=None, app still starts)
- `database.py` auto-converts `postgres://` → `postgresql+asyncpg://` for Railway
- Connection timeout: 5 seconds (prevents 60s startup hang)
- `.dockerignore` must NOT exclude `frontend/` (needed for build stage)
- `.dockerignore` MUST exclude `frontend/node_modules` and `frontend/dist`

---

## KNOWN ISSUES & FIXES APPLIED

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| `requirements.txt not found` | Dockerfile in `backend/` subfolder | Moved all backend files to repo root |
| `Could not parse SQLAlchemy URL` | Empty/invalid DATABASE_URL | `database.py` checks URL before creating engine, sets `engine=None` |
| API returns HTML instead of JSON | `/{path:path}` catch-all steals API routes | Changed to `@app.exception_handler(404)` |
| `nginx` in logs instead of `uvicorn` | Root Directory set to `frontend` | Root Directory must be BLANK |
| Telegram bot conflict | Two instances polling | `drop_pending_updates=True`, wait 1-2 min on redeploy |
| 429 Too Many Requests (NIM) | Free tier 40 RPM limit | Rate limiter (25/min) + retry with backoff |
| Scan timeout in browser | 130 stocks takes 10+ min synchronously | Background thread + progress polling endpoint |
| Scan progress lost on tab switch | `useState` resets on unmount | Moved scanId to Zustand global store |
| White dropdown in dark mode | Native `<select>` styling | Custom CSS with `!important` for dark backgrounds |
| 60s startup delay | DB connection timeout | Added `connect_args={"timeout": 5}` |
| News stuck on "Loading" | RSS fetch slow, no cache | Added 2-min cache for RSS results |

---

## STOCK UNIVERSE

131 NSE stocks across 33 sectors, classified as Large/Mid/Small cap.
Defined in `app/engine/stock_universe.py`.

Key stocks: RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, BHARTIARTL, ITC, SBIN, LT, AXISBANK, WIPRO, HCLTECH, SUNPHARMA, TATAMOTORS, MARUTI, BAJFINANCE, POWERGRID, NTPC, ADANIENT, ULTRACEMCO, and 111 more.

**Known delisted/issue:** TATAMOTORS.NS sometimes returns 404 from Yahoo Finance. GMRINFRA.NS may be delisted.

---

## FRONTEND STATE MANAGEMENT

Zustand store (`useAppStore.ts`) holds:
- `currentScanId` — persists across tab switches
- `isScanning` — global scanning state
- `scanResults` — last scan results array
- `scanSummary` — last scan metadata
- `capital`, `minConfidence`, `maxPositions` — user settings
- `holdingMode` (weekly/monthly), `scope`, `useAI`

API calls use TanStack Query with refetch intervals (settings: 30s, health: 15s, news: 5min).

---

## CSS DESIGN SYSTEM

- Background: `#060610` (near-black)
- Cards: glass-card with `linear-gradient(145deg, rgba(14,14,36,0.95), rgba(10,10,28,0.8))`
- Accent colors: cyan (`#00d2ff`), purple (`#7b2ff7`), green (`#00e676`), red (`#ff5252`)
- Forms: `.input-dark`, `.select-dark` classes with custom dark backgrounds
- Buttons: `.btn-primary` (gradient purple), `.btn-secondary` (glass)
- Font: Inter (display), monospace for data/logs

---

## FUTURE ENHANCEMENTS (NOT BUILT YET)

- [ ] Trade lifecycle management (enter/exit/partial profit) with DB persistence
- [ ] Backtesting engine against historical data
- [ ] Portfolio P&L tracking with daily snapshots
- [ ] Smart exit system with 10 exit conditions (trailing stop, news-driven, etc.)
- [ ] Celery workers with Redis (for heavier background processing)
- [ ] Price alerts via Telegram when target/stop-loss hit
- [ ] Multi-user support with authentication
- [ ] Custom stock universe (add/remove stocks from dashboard)
- [ ] Indian options chain data integration
- [ ] Mobile app (React Native)

---

## HOW TO MAKE CHANGES

### For backend Python changes:
1. Edit file on GitHub (pencil icon → select all → delete → paste)
2. Railway auto-deploys on commit to master branch
3. Check Railway logs for errors

### For frontend React changes:
1. Edit `.tsx`/`.ts`/`.css` file on GitHub
2. Railway rebuilds: Node compiles React → Python serves it
3. Build errors show in Railway build logs (TypeScript strict mode)

### Common TypeScript gotchas:
- Use `(value?.length ?? 0) > 0` not `value?.length > 0`
- All store setters need explicit types: `(v: boolean) => ...`
- Missing schema fields cause build failure (ScanSummary needs scan_date, scope)

### To test locally:
```bash
cd repo-root
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
cp -r frontend/dist static
uvicorn app.main:app --reload --port 8000
```

---

## QUICK REFERENCE — File to Edit for Common Tasks

| Task | File(s) |
|------|---------|
| Add new API endpoint | `app/main.py` |
| Add new stock to universe | `app/engine/stock_universe.py` |
| Change scoring weights | `app/engine/scoring.py` |
| Add new indicator | `app/engine/indicators.py` + `scoring.py` |
| Change LLM model | `app/config.py` (NIM_MODEL) + Railway ENV |
| Add RSS news source | `app/sentiment/analyzer.py` (NEWS_RSS_FEEDS) |
| Add Telegram command | `app/integrations/telegram_commands.py` |
| Change auto-scan schedule | `app/tasks/auto_scheduler.py` |
| Add new frontend page | `frontend/src/pages/NewPage.tsx` + `App.tsx` router |
| Change UI styling | `frontend/src/index.css` |
| Fix scan progress UI | `frontend/src/pages/Scan.tsx` |
| Fix dropdown/form dark mode | `frontend/src/index.css` (select, input rules) |
| Add DB model | `app/models/__init__.py` + `app/schemas/__init__.py` |
