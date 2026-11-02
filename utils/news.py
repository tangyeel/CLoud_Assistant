"""
utils/news.py — Real-time Finance & Technology News Radar.
Fetches top tech & market headlines 100% free with zero API keys.
"""
import httpx
import xml.etree.ElementTree as ET
from ddgs import DDGS
from utils.logger import logger
from utils.retry import retry_on_failure


@retry_on_failure(max_retries=2, base_delay=1.0)
def get_finance_and_tech_news(max_items: int = 5) -> list[dict]:
    """
    Retrieve top news items focusing on technology, AI, and finance/markets.
    """
    # 1. Primary engine: DDGS News
    try:
        ddgs = DDGS(timeout=8)
        raw_news = list(ddgs.news("technology finance markets AI", max_results=max_items))
        if raw_news:
            items = []
            for item in raw_news:
                items.append({
                    "title": item.get("title", ""),
                    "source": item.get("source", "News"),
                    "url": item.get("url", ""),
                    "snippet": item.get("body", ""),
                    "date": item.get("date", "")[:10] if item.get("date") else "",
                })
            logger.info(f"Retrieved {len(items)} news headlines via DDGS.")
            return items
    except Exception as e:
        logger.warning(f"DDGS news fetch warning: {e}. Trying RSS fallback...")

    # 2. Fallback: TechCrunch / HackerNews RSS
    try:
        rss_url = "https://techcrunch.com/feed/"
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(rss_url)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                items = []
                for item in root.findall("./channel/item")[:max_items]:
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    desc = item.findtext("description", "")
                    items.append({
                        "title": title,
                        "source": "TechCrunch",
                        "url": link,
                        "snippet": desc[:150] if desc else "",
                        "date": "",
                    })
                return items
    except Exception as err2:
        logger.warning(f"RSS fallback also failed: {err2}")

    return []


def format_news_card(items: list[dict] | None = None) -> str:
    """Format news headlines into a clean Telegram markdown digest."""
    if items is None:
        items = get_finance_and_tech_news()

    if not items:
        return "📰 No live finance or tech headlines available at this moment."

    lines = [
        "📰 **Jarvis Tech & Finance Radar**",
        "──────────────────────\n"
    ]
    for i, item in enumerate(items, 1):
        source_str = f" *({item['source']})*" if item.get("source") else ""
        lines.append(f"{i}. **[{item['title']}]({item['url']})**{source_str}")
        if item.get("snippet"):
            snippet_clean = item['snippet'].replace("\n", " ").strip()
            lines.append(f"   _{snippet_clean[:140]}..._\n")

    return "\n".join(lines)
