"""
Breaking News Scanner — Runs every 15 min during market hours.
Matches new articles against open positions and triggers alerts.
"""

import structlog
from datetime import datetime
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Trade, Stock, NewsArticle
from app.sentiment.analyzer import (
    fetch_news_from_rss, match_news_to_stock,
    classify_news_impact, analyze_sentiment,
    IMMEDIATE_EXIT_TRIGGERS,
)
from app.integrations.telegram_bot import alert_emergency_exit, alert_partial_profit

log = structlog.get_logger()
settings = get_settings()

try:
    from app.tasks.celery_app import celery_app
    _has_celery = True
except Exception:
    _has_celery = False

def _celery_task_or_plain(name):
    def decorator(func):
        if _has_celery:
            return celery_app.task(name=name)(func)
        return func
    return decorator

# Track already-processed article URLs to avoid duplicate alerts
_processed_urls: set = set()


def _get_sync_session():
    engine = create_engine(settings.DATABASE_URL_SYNC)
    return Session(engine)


@_celery_task_or_plain("app.tasks.news_tasks.scan_breaking_news")
def scan_breaking_news():
    """
    Fetch latest news, match against open positions,
    trigger emergency exit or partial profit alerts for HIGH impact news.
    """
    log.info("breaking_news_scan_started")
    session = _get_sync_session()

    try:
        # Get open trades with their stocks
        open_trades = session.execute(
            select(Trade, Stock).join(Stock, Trade.stock_id == Stock.id).where(
                Trade.status.in_(["OPEN", "PARTIAL_EXIT"])
            )
        ).all()

        if not open_trades:
            log.info("no_open_positions_for_news")
            return {"checked": 0, "alerts": 0}

        # Fetch latest news
        articles = fetch_news_from_rss(max_articles=40)
        new_articles = [a for a in articles if a.get("link") not in _processed_urls]

        if not new_articles:
            log.info("no_new_articles")
            return {"checked": 0, "alerts": 0}

        alerts_sent = 0

        for trade, stock in open_trades:
            # Match news to this stock
            matched = match_news_to_stock(
                stock.ticker, stock.name, stock.sector, new_articles
            )

            if not matched:
                continue

            for article in matched:
                impact = classify_news_impact(
                    article.get("title", ""),
                    article.get("summary", "")
                )

                if impact == "HIGH":
                    # Check if it's negative (potential exit trigger)
                    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
                    is_negative = any(t in text for t in IMMEDIATE_EXIT_TRIGGERS)

                    if is_negative:
                        log.warning("high_impact_negative_news",
                                    stock=stock.ticker, title=article.get("title", "")[:100])

                        # Use LLM to confirm severity
                        sentiment = analyze_sentiment(
                            [article["title"]],
                            stock.name,
                            stock.ticker,
                        )

                        if sentiment.get("sentiment_score", 0) < -0.3:
                            alert_emergency_exit(
                                stock.ticker, stock.name,
                                float(trade.entry_price),
                                float(trade.entry_price),  # We don't have live price here
                                f"HIGH IMPACT: {article.get('title', '')[:150]}"
                            )
                            alerts_sent += 1
                    else:
                        # HIGH impact positive — no action needed, just log
                        log.info("high_impact_positive_news",
                                 stock=stock.ticker, title=article.get("title", "")[:100])

                elif impact == "MEDIUM":
                    # Analyze sentiment for MEDIUM impact
                    sentiment = analyze_sentiment(
                        [article["title"]],
                        stock.name,
                        stock.ticker,
                    )

                    if sentiment.get("sentiment_score", 0) < -0.2:
                        alert_partial_profit(
                            stock.ticker, stock.name,
                            float(trade.entry_price),
                            float(trade.entry_price),
                            f"Negative news: {article.get('title', '')[:100]}",
                            30,
                        )
                        alerts_sent += 1

                # Store article in DB (dedup by URL)
                try:
                    existing = session.execute(
                        select(NewsArticle).where(NewsArticle.url == article.get("link"))
                    ).scalar_one_or_none()

                    if not existing and article.get("link"):
                        news_record = NewsArticle(
                            title=article.get("title", "")[:500],
                            summary=article.get("summary", "")[:500],
                            source=article.get("source", ""),
                            url=article.get("link", ""),
                            published_at=datetime.utcnow(),
                            impact_level=impact,
                            matched_stocks=[stock.ticker],
                        )
                        session.add(news_record)
                except Exception:
                    pass

        # Mark all articles as processed
        for a in new_articles:
            if a.get("link"):
                _processed_urls.add(a["link"])

        # Keep processed set manageable
        if len(_processed_urls) > 5000:
            _processed_urls.clear()

        session.commit()
        log.info("breaking_news_scan_complete",
                 articles=len(new_articles), alerts=alerts_sent)

        return {"new_articles": len(new_articles), "alerts_sent": alerts_sent}

    except Exception as e:
        log.error("breaking_news_error", error=str(e))
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()
