# TradeSignal India v2.0

**AI-Powered Weekly/Monthly Equity Signal System for NSE**

Full-stack rebuild: React + FastAPI + PostgreSQL + Celery + Telegram Bot

---

## Quick Start (Local Development)

### Prerequisites
- Docker + Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)

### 1. Clone & Configure

```bash
cd tradesignal-v2
cp .env.example .env
# Edit .env with your API keys:
#   NIM_API_KEY=your_nvidia_nim_key
#   TELEGRAM_BOT_TOKEN=your_bot_token
#   TELEGRAM_CHAT_ID=your_chat_id
```

### 2. Start Everything 

```bash
docker-compose up --build
```

This starts:
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **FastAPI Backend** on http://localhost:8000
- **React Frontend** on http://localhost:5173

### 3. Verify

- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Frontend: http://localhost:5173

---

## Architecture

```
React (Vite+TS+Tailwind)  ←→  FastAPI (Python)  ←→  PostgreSQL
         ↕                          ↕                      ↕
     WebSocket              Celery Workers            Redis Queue
                                   ↕
                           Telegram Bot API
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand, React Query, Lightweight Charts |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Database | PostgreSQL 16 |
| Task Queue | Celery + Redis |
| AI/LLM | NVIDIA NIM (LLaMA 3.3 70B) via OpenAI SDK |
| Sentiment | LLM (primary) → VADER (fallback) → TextBlob (last resort) |
| Alerts | Telegram Bot API |
| Deploy | Railway (Docker) |

### Signal Engine — 15 Indicators

| # | Indicator | Weight | New in v2 |
|---|-----------|--------|-----------|
| 1 | RSI | 12 | |
| 2 | MACD | 12 | |
| 3 | Moving Averages | 10 | |
| 4 | Bollinger Bands | 8 | |
| 5 | Volume | 10 | |
| 6 | Stochastic | 7 | |
| 7 | ADX | 8 | |
| 8 | Support/Resistance | 10 | |
| 9 | Momentum | 5 | |
| 10 | VWAP | 8 | ✅ |
| 11 | SuperTrend | 8 | ✅ |
| 12 | Ichimoku Cloud | 10 | ✅ |
| 13 | Fibonacci | 7 | ✅ |
| 14 | EMA Ribbon | 5 | ✅ |
| 15 | Relative Strength vs Nifty | 7 | ✅ |

Total: 127 points → normalized to 0-100

### LLM-First Sentiment Pipeline

1. **Primary**: NVIDIA NIM LLaMA 3.3 70B — deep sentiment analysis with trading action recommendation
2. **Fallback**: VADER with 60+ Indian financial custom lexicon entries
3. **Last Resort**: TextBlob

### News Sources (8 RSS feeds)

Economic Times, Moneycontrol, LiveMint, Business Standard, NDTV Profit, Investing.com India, Trade Brains, Ticker Tape

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/stocks` | List stocks |
| GET | `/api/stocks/sectors` | List sectors |
| POST | `/api/scans` | Trigger market scan |
| GET | `/api/scans/{id}` | Full scan results |
| GET | `/api/scans/{id}/signals` | BUY signals only |
| POST | `/api/trades` | Record trade entry |
| GET | `/api/trades` | List trades |
| GET | `/api/trades/open` | Open positions |
| PUT | `/api/trades/{id}/close` | Close trade |
| GET | `/api/trades/performance` | P&L analytics |
| POST | `/api/portfolio/allocate` | Compute allocation |
| GET | `/api/news` | Latest news |
| GET | `/api/news/sentiment` | Market sentiment |
| GET | `/api/settings` | System settings |
| WS | `/ws/updates` | Live updates |

Full interactive docs at `/docs` (Swagger UI).

---

## Railway Deployment

### 1. Create Railway Project

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and init
railway login
railway init
```

### 2. Add Services

In Railway dashboard, add:
- **PostgreSQL** (managed plugin)
- **Redis** (managed plugin)
- **Backend** (from `/backend` directory)
- **Celery Worker** (same image, command: `celery -A app.tasks.celery_app worker`)
- **Celery Beat** (same image, command: `celery -A app.tasks.celery_app beat`)
- **Frontend** (from `/frontend` directory)

### 3. Set Environment Variables

Set these in Railway's service variables:
```
NIM_API_KEY=nvapi-xxx
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NIM_MODEL=meta/llama-3.3-70b-instruct
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
CORS_ORIGINS=https://your-frontend.railway.app
```

`DATABASE_URL` and `REDIS_URL` are auto-injected by Railway plugins.

### 4. Deploy

```bash
railway up
```

---

## Telegram Bot

### Setup
1. Message `@BotFather` on Telegram → `/newbot` → save token
2. Message your bot, then get `chat_id` from: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

### Alert Types
- 🎯 **BUY SIGNAL** — New signal with entry/target/SL
- 💰 **PARTIAL PROFIT** — Book partial gains
- 🚨 **EMERGENCY EXIT** — HIGH impact negative news
- 🛑 **STOP LOSS** — Stop triggered
- 🎯 **TARGET HIT** — Target reached
- 🔒 **TRAILING STOP** — Locked-in profit
- ⚠️ **TREND REVERSAL** — SuperTrend flip
- ⏰ **PERIOD END** — Holding period expired
- 📊 **WEEKLY SUMMARY** — Sunday 6 PM scan report

---

## Key Fixes from v1

1. `final_signal` now recalculated from `final_confidence` after all modifiers
2. NHPC.NS duplicate removed (was in both Mid and Small cap)
3. News matching uses ticker + full name (not generic word split)
4. API key removed from source code → environment variables
5. Volume gate: confidence capped at 65% when volume < average
6. `scikit-learn` removed from dependencies (was unused)

---

## License

MIT

---

*TradeSignal India v2.0 — React + FastAPI + PostgreSQL + LLM Sentiment + Telegram Alerts*
