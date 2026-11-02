"""
utils/search.py — 100% Free Real-time Web Search using DuckDuckGo.
Requires zero API keys. Supports live search queries and fact lookup.
"""
from ddgs import DDGS
from utils.logger import logger
from utils.retry import retry_on_failure


@retry_on_failure(max_retries=2, base_delay=1.0)
def search_web(query: str, max_results: int = 4) -> list[dict]:
    """
    Search the live web for a query.

    Returns:
        List of dicts with 'title', 'snippet', 'url'.
    """
    clean_query = query.strip()
    logger.info(f"🔍 Searching web for: '{clean_query}'")

    try:
        ddgs = DDGS(timeout=8)
        raw_results = list(ddgs.text(clean_query, max_results=max_results))
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            })
        logger.info(f"Retrieved {len(results)} web search results.")
        return results
    except Exception as e:
        logger.warning(f"Web search error for '{clean_query}': {e}")
        return []


def format_search_results(query: str, results: list[dict]) -> str:
    """Format search results into clean Telegram markdown."""
    if not results:
        return f"🔍 No web search results found for *'{query}'*."

    lines = [f"🌐 **Web Search Results for:** *{query}*\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **[{r['title']}]({r['url']})**")
        if r.get("snippet"):
            lines.append(f"   _{r['snippet'][:180]}..._\n")

    return "\n".join(lines)


def get_search_context_for_ai(query: str) -> str:
    """Fetch search snippets formatted as knowledge context for LLM response generation."""
    results = search_web(query, max_results=3)
    if not results:
        return ""
    snippets = []
    for r in results:
        snippets.append(f"Source ({r['title']} - {r['url']}):\n{r['snippet']}")
    return "\n\n".join(snippets)
