"""
Sentiment Engine v2.1 — LLM-First Architecture with Rate Limiting.
Primary: NVIDIA NIM (Mistral Small 3.1 24B — fast, high accuracy).
Fallback: VADER with Indian financial lexicon.
Last resort: TextBlob.
"""

import json
import re
import time
import threading
from datetime import datetime, timedelta
from typing import Optional
from openai import OpenAI
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from textblob import TextBlob
import feedparser
import structlog

from app.config import get_settings

log = structlog.get_logger()
settings = get_settings()

# ═══════════════════════════════════════════════════════════════════════════
#  RATE LIMITER — Stay under 40 RPM NVIDIA free tier
# ═══════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Simple token-bucket rate limiter. Max N calls per minute."""
    def __init__(self, max_per_minute: int = 30):
        self.min_interval = 60.0 / max_per_minute  # seconds between calls
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        """Block until it's safe to make the next API call."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                time.sleep(sleep_time)
            self.last_call = time.time()

_llm_rate_limiter = RateLimiter(max_per_minute=25)  # Stay well under 40 RPM


# ═══════════════════════════════════════════════════════════════════════════
#  RSS NEWS FEEDS (8 sources)
# ═══════════════════════════════════════════════════════════════════════════

NEWS_RSS_FEEDS = [
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "name": "Economic Times"},
    {"url": "https://www.moneycontrol.com/rss/marketreports.xml", "name": "Moneycontrol"},
    {"url": "https://www.livemint.com/rss/markets", "name": "LiveMint"},
    {"url": "https://www.business-standard.com/rss/markets-106.rss", "name": "Business Standard"},
    {"url": "https://in.investing.com/rss/news.rss", "name": "Investing.com"},
    {"url": "https://tradebrains.in/blog/feed", "name": "Trade Brains"},
    {"url": "https://www.tickertape.in/blog/feed", "name": "Ticker Tape"},
    {"url": "https://www.ndtvprofit.com/rss/markets", "name": "NDTV Profit"},
]

# ═══════════════════════════════════════════════════════════════════════════
#  NEWS IMPACT KEYWORDS
# ═══════════════════════════════════════════════════════════════════════════

IMMEDIATE_EXIT_TRIGGERS = [
    "fraud", "scam", "sebi ban", "suspended", "default", "bankruptcy",
    "criminal", "arrest", "raid", "accounting irregularity", "restatement",
    "delisting", "promoter sell bulk", "insider trading", "credit downgrade",
    "debt default", "forensic audit",
]

PARTIAL_PROFIT_TRIGGERS = [
    "target cut", "downgrade", "sector headwind", "margin pressure",
    "fii selling heavy", "results below", "guidance cut", "capex delay",
    "order cancellation", "regulatory risk",
]

HOLD_STRONG_TRIGGERS = [
    "results beat", "upgrade", "target raised", "order win", "expansion",
    "fii buying heavy", "block deal buy", "promoter buying", "dividend",
    "buyback", "sector tailwind", "margin improvement",
]


# ═══════════════════════════════════════════════════════════════════════════
#  RSS FETCHING (with timeout)
# ═══════════════════════════════════════════════════════════════════════════

_news_cache = {"articles": [], "timestamp": 0}
_NEWS_CACHE_TTL = 120  # 2 minutes


def fetch_news_from_rss(max_articles: int = 80) -> list:
    """Fetch latest market news from 8 Indian financial RSS feeds (cached)."""
    now = time.time()

    # Return cached if fresh
    if _news_cache["articles"] and (now - _news_cache["timestamp"]) < _NEWS_CACHE_TTL:
        return _news_cache["articles"][:max_articles]

    articles = []
    per_feed = max(max_articles // len(NEWS_RSS_FEEDS), 5)

    for feed_info in NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:per_feed]:
                published = ""
                if hasattr(entry, "published"):
                    published = entry.published
                elif hasattr(entry, "updated"):
                    published = entry.updated

                articles.append({
                    "title": entry.get("title", "").strip(),
                    "summary": entry.get("summary", "")[:500].strip(),
                    "link": entry.get("link", ""),
                    "published": published,
                    "source": feed_info["name"],
                })
        except Exception as e:
            log.warning("rss_fetch_error", feed=feed_info["name"], error=str(e)[:100])

    # Update cache
    _news_cache["articles"] = articles
    _news_cache["timestamp"] = now

    return articles[:max_articles]


# ═══════════════════════════════════════════════════════════════════════════
#  SMART STOCK-NEWS MATCHING (fixed from v1)
# ═══════════════════════════════════════════════════════════════════════════

def match_news_to_stock(stock_ticker: str, stock_name: str, stock_sector: str,
                        articles: list) -> list:
    """Match news to a specific stock using ticker + full name + sector."""
    ticker_clean = stock_ticker.replace(".NS", "").lower()
    name_lower = stock_name.lower()

    keywords = [ticker_clean, name_lower]
    exclude = {"limited", "india", "industries", "corp", "corporation", "company", "ltd"}
    for word in stock_name.lower().split():
        if len(word) > 4 and word not in exclude:
            keywords.append(word)

    matched = []
    for article in articles:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()

        if ticker_clean in text:
            matched.append({**article, "match_type": "ticker"})
            continue
        if name_lower in text:
            matched.append({**article, "match_type": "name"})
            continue
        if any(kw in text for kw in keywords[2:]):
            matched.append({**article, "match_type": "keyword"})

    return matched[:10]


# ═══════════════════════════════════════════════════════════════════════════
#  LLM SENTIMENT (PRIMARY) — NVIDIA NIM with rate limiting + retry
# ═══════════════════════════════════════════════════════════════════════════

def _get_nim_client() -> Optional[OpenAI]:
    """Create NVIDIA NIM OpenAI-compatible client."""
    if not settings.NIM_API_KEY:
        return None
    try:
        return OpenAI(
            base_url=settings.NIM_BASE_URL,
            api_key=settings.NIM_API_KEY,
            timeout=60,  # 60 second timeout (was 30 — caused VADER fallback)
        )
    except Exception:
        return None


def _call_llm_with_retry(client, messages, temperature=0.2, max_tokens=1024, retries=3) -> Optional[str]:
    """Call LLM API with rate limiting and retry on 429."""
    for attempt in range(retries + 1):
        _llm_rate_limiter.wait()  # Rate limit

        try:
            completion = client.chat.completions.create(
                model=settings.NIM_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw = completion.choices[0].message.content.strip()
            return raw

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "Too Many" in error_str:
                wait = 3 * (attempt + 1)  # 3s, 6s, 9s
                log.warning("llm_rate_limited", attempt=attempt + 1, wait=wait)
                time.sleep(wait)
                continue
            else:
                log.warning("llm_call_error", error=error_str[:200])
                return None

    log.warning("llm_all_retries_exhausted")
    return None


def _parse_llm_json(raw: str) -> Optional[dict]:
    """Parse JSON from LLM response, handling markdown wrapping."""
    if not raw:
        return None
    try:
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return None


def llm_analyze_sentiment(headlines: list[str], stock_name: str = "",
                          stock_ticker: str = "") -> Optional[dict]:
    """Use NVIDIA NIM to analyze sentiment of news headlines."""
    client = _get_nim_client()
    if not client or not headlines:
        return None

    headlines_text = "\n".join([f"- {h}" for h in headlines[:15]])
    context = f" for {stock_name} ({stock_ticker})" if stock_name else ""

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert Indian stock market sentiment analyst. "
                "Analyze news headlines and return ONLY a JSON object. "
                "Focus on short-term (5-day to 30-day) trading impact for NSE stocks. "
                "Consider Indian market context: FII/DII flows, RBI policy, SEBI regulations, "
                "sector rotation, earnings season, and global cues. "
                "Respond with ONLY valid JSON, no markdown, no backticks."
            )
        },
        {
            "role": "user",
            "content": f"""Analyze these Indian market headlines{context}:

{headlines_text}

Return JSON:
- "overall_sentiment": "VERY_BULLISH"|"BULLISH"|"NEUTRAL"|"BEARISH"|"VERY_BEARISH"
- "sentiment_score": float -1.0 to 1.0
- "impact_level": "HIGH"|"MEDIUM"|"LOW"
- "confidence": float 0.0 to 1.0
- "key_themes": list of max 3 strings
- "trading_action": "STRONG_BUY_SIGNAL"|"BUY_SIGNAL"|"HOLD"|"PARTIAL_EXIT"|"FULL_EXIT"|"NO_ACTION"
- "score_modifier": integer -10 to +10
- "reasoning": string (1-2 sentences)
- "risk_alert": string or null"""
        }
    ]

    raw = _call_llm_with_retry(client, messages, temperature=0.2)
    result = _parse_llm_json(raw)

    if result:
        required = ["overall_sentiment", "sentiment_score", "impact_level", "score_modifier"]
        if all(k in result for k in required):
            result["sentiment_score"] = max(-1.0, min(1.0, float(result["sentiment_score"])))
            result["score_modifier"] = max(-10, min(10, int(result["score_modifier"])))
            result["source"] = "llm"
            return result

    return None


def llm_analyze_stock(stock_data: dict) -> dict:
    """Use NIM for deep AI analysis on a stock's technical + news data."""
    client = _get_nim_client()
    if not client:
        return {"ai_analysis": "", "ai_confidence_modifier": 0, "source": "none"}

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert Indian stock market analyst for short-term "
                "(5-day to 30-day) equity trading on NSE. Analyze technical indicators, volume, "
                "support/resistance, and news sentiment. Respond ONLY in valid JSON."
            )
        },
        {
            "role": "user",
            "content": f"""Analyze this Indian stock for short-term trade:

Stock: {stock_data.get('name', 'Unknown')} ({stock_data.get('ticker', 'Unknown')})
Sector: {stock_data.get('sector', 'Unknown')} | Cap: {stock_data.get('cap', 'Unknown')}
Price: ₹{stock_data.get('current_price', 0):.2f}

Technical: RSI={stock_data.get('rsi', 'N/A')}, MACD_Hist={stock_data.get('macd_hist', 'N/A')},
BB%={stock_data.get('bb_pct', 'N/A')}, ADX={stock_data.get('adx', 'N/A')},
SuperTrend={'Bullish' if stock_data.get('supertrend_dir', 0) == 1 else 'Bearish'},
Vol_Ratio={stock_data.get('vol_ratio', 'N/A')}x

MAs: vs SMA10={stock_data.get('vs_sma10')}, vs SMA20={stock_data.get('vs_sma20')}, vs SMA50={stock_data.get('vs_sma50')}
Returns: 1D={stock_data.get('daily_return')}%, 5D={stock_data.get('weekly_return')}%, 20D={stock_data.get('monthly_return')}%
S/R: Supports={stock_data.get('supports', [])}, Resistances={stock_data.get('resistances', [])}
Score: {stock_data.get('signal_score', 0)}/100 | News: {stock_data.get('news_sentiment', 'N/A')}

Return JSON:
- "analysis": string (2-3 sentences)
- "recommendation": "STRONG_BUY"|"BUY"|"HOLD"|"SELL"|"STRONG_SELL"
- "confidence_modifier": -10 to +10
- "key_factors": list of 3 strings
- "risk_factors": list of 2 strings
- "expected_move_pct": float"""
        }
    ]

    raw = _call_llm_with_retry(client, messages, temperature=0.3)
    result = _parse_llm_json(raw)

    if result:
        return {
            "ai_analysis": result.get("analysis", ""),
            "ai_recommendation": result.get("recommendation", "HOLD"),
            "ai_confidence_modifier": max(-10, min(10, int(result.get("confidence_modifier", 0)))),
            "ai_key_factors": result.get("key_factors", []),
            "ai_risk_factors": result.get("risk_factors", []),
            "ai_expected_move": result.get("expected_move_pct", 0),
            "source": "llm",
        }

    return {"ai_analysis": "", "ai_confidence_modifier": 0, "source": "error"}


# ═══════════════════════════════════════════════════════════════════════════
#  VADER SENTIMENT (FALLBACK #1) — Indian financial lexicon
# ═══════════════════════════════════════════════════════════════════════════

_vader_analyzer = None

def _get_vader() -> SentimentIntensityAnalyzer:
    """Get VADER analyzer with Indian financial custom lexicon."""
    global _vader_analyzer
    if _vader_analyzer is None:
        _vader_analyzer = SentimentIntensityAnalyzer()
        custom_lexicon = {
            "bullish": 2.5, "bearish": -2.5, "rally": 2.0, "crash": -3.0,
            "surge": 2.0, "plunge": -2.5, "soar": 2.5, "tumble": -2.0,
            "nifty high": 1.5, "sensex drop": -2.0, "all-time high": 2.5,
            "fii buying": 2.0, "fii selling": -2.0, "fii outflow": -2.5,
            "dii support": 1.5, "dii buying": 1.5,
            "rbi hike": -1.0, "rbi cut": 1.5, "rbi pause": 0.5,
            "sebi ban": -3.0, "sebi penalty": -2.0, "sebi warning": -1.5,
            "block deal": 1.0, "bulk deal": 0.5,
            "promoter pledge": -2.0, "promoter buying": 2.0, "promoter selling": -2.0,
            "dividend": 1.5, "buyback": 2.0, "bonus": 1.5, "split": 0.5,
            "downgrade": -2.5, "upgrade": 2.5,
            "target raised": 2.0, "target cut": -2.0, "target price": 0.5,
            "results beat": 2.5, "results miss": -2.5, "profit growth": 2.0,
            "revenue growth": 1.5, "margin expansion": 2.0, "margin pressure": -1.5,
            "order win": 2.0, "order book": 1.5, "order cancellation": -2.0,
            "expansion": 1.5, "capex": 1.0, "debt reduction": 1.5,
            "default": -3.5, "fraud": -4.0, "scam": -4.0, "raid": -3.0,
            "restructuring": -1.0, "layoff": -1.5, "cost cutting": 0.5,
            "breakout": 2.0, "breakdown": -2.0, "support": 0.5, "resistance": -0.5,
            "oversold": 1.5, "overbought": -1.0, "golden cross": 2.0, "death cross": -2.0,
        }
        for word, score in custom_lexicon.items():
            _vader_analyzer.lexicon[word] = score

    return _vader_analyzer


def vader_sentiment(text: str) -> dict:
    """Analyze text sentiment using VADER with financial lexicon."""
    try:
        analyzer = _get_vader()
        scores = analyzer.polarity_scores(text)
        compound = scores["compound"]

        if compound >= 0.3:
            label = "VERY_BULLISH"
        elif compound >= 0.1:
            label = "BULLISH"
        elif compound <= -0.3:
            label = "VERY_BEARISH"
        elif compound <= -0.1:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "overall_sentiment": label,
            "sentiment_score": round(compound, 3),
            "impact_level": "MEDIUM" if abs(compound) > 0.3 else "LOW",
            "score_modifier": int(compound * 5),
            "source": "vader",
        }
    except Exception:
        return {"overall_sentiment": "NEUTRAL", "sentiment_score": 0, "score_modifier": 0, "source": "vader_error"}


def textblob_sentiment(text: str) -> dict:
    """Last-resort sentiment using TextBlob."""
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        if polarity > 0.2:
            label = "BULLISH"
        elif polarity < -0.2:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "overall_sentiment": label,
            "sentiment_score": round(polarity, 3),
            "score_modifier": int(polarity * 3),
            "source": "textblob",
        }
    except Exception:
        return {"overall_sentiment": "NEUTRAL", "sentiment_score": 0, "score_modifier": 0, "source": "textblob_error"}


# ═══════════════════════════════════════════════════════════════════════════
#  UNIFIED SENTIMENT PIPELINE — LLM → VADER → TextBlob
# ═══════════════════════════════════════════════════════════════════════════

def analyze_sentiment(headlines: list[str], stock_name: str = "",
                      stock_ticker: str = "") -> dict:
    """3-tier sentiment: LLM → VADER → TextBlob."""
    if not headlines:
        return {
            "overall_sentiment": "NO_NEWS", "sentiment_score": 0,
            "impact_level": "LOW", "score_modifier": 0,
            "source": "none", "article_count": 0,
        }

    combined_text = " ".join(headlines[:15])

    # TIER 1: LLM Analysis
    llm_result = llm_analyze_sentiment(headlines, stock_name, stock_ticker)
    if llm_result:
        llm_result["article_count"] = len(headlines)
        log.info("sentiment_via_llm", stock=stock_ticker, sentiment=llm_result["overall_sentiment"])
        return llm_result

    # TIER 2: VADER
    log.info("sentiment_fallback_vader", stock=stock_ticker)
    vader_result = vader_sentiment(combined_text)
    if vader_result.get("source") != "vader_error":
        vader_result["article_count"] = len(headlines)
        return vader_result

    # TIER 3: TextBlob
    log.info("sentiment_fallback_textblob", stock=stock_ticker)
    tb_result = textblob_sentiment(combined_text)
    tb_result["article_count"] = len(headlines)
    return tb_result


def classify_news_impact(article_title: str, article_summary: str = "") -> str:
    """Classify news impact level based on keyword matching."""
    text = (article_title + " " + article_summary).lower()

    for trigger in IMMEDIATE_EXIT_TRIGGERS:
        if trigger in text:
            return "HIGH"

    for trigger in PARTIAL_PROFIT_TRIGGERS + HOLD_STRONG_TRIGGERS:
        if trigger in text:
            return "MEDIUM"

    return "LOW"


def get_stock_sentiment(stock_ticker: str, stock_name: str, stock_sector: str,
                        articles: list) -> dict:
    """Full sentiment pipeline for a single stock."""
    matched = match_news_to_stock(stock_ticker, stock_name, stock_sector, articles)

    if not matched:
        return {
            "article_count": 0, "sentiment_score": 0,
            "overall_sentiment": "NO_NEWS", "score_modifier": 0,
            "impact_level": "LOW", "articles": [], "source": "none",
        }

    headlines = [a["title"] for a in matched if a.get("title")]
    result = analyze_sentiment(headlines, stock_name, stock_ticker)

    for article in matched:
        article["impact_level"] = classify_news_impact(
            article.get("title", ""), article.get("summary", "")
        )

    if any(a.get("impact_level") == "HIGH" for a in matched):
        result["impact_level"] = "HIGH"

    result["articles"] = matched[:5]
    result["article_count"] = len(matched)

    return result
