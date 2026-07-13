"""
Real-time information retrieval tools.
Integrates the Tavily search API and timezone resolution utilities.
"""
import os
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool


def get_search_tool():
    """Initializes and returns a configured Tavily API client for advanced web search."""
    return TavilySearchResults(
        max_results=5,
        search_depth="advanced",
        include_answer=True,
        include_raw_content=False,
        include_images=False,
    )


@tool
def web_search(query: str) -> str:
    """
    Executes a real-time web search for current events and factual queries.
    Returns a consolidated summary of search results with corresponding source URLs.
    
    Args:
        query: The search query string.
    
    Returns:
        A formatted string with search results and source URLs.
    """
    search = TavilySearchResults(
        max_results=5,
        search_depth="advanced",
        include_answer=True,
    )
    results = search.invoke(query)
    
    if not results:
        return "No results found for the query."
    
    formatted = []
    for i, result in enumerate(results, 1):
        formatted.append(
            f"**Result {i}:**\n"
            f"Title: {result.get('title', 'N/A')}\n"
            f"URL: {result.get('url', 'N/A')}\n"
            f"Content: {result.get('content', 'N/A')}\n"
        )
    
    return "\n---\n".join(formatted)

@tool
def get_current_time(timezone_name: str) -> str:
    """
    Resolves the current date and time for a given IANA timezone identifier.
    Must be utilized when determining localized times outside the system's default timezone.
    """
    import datetime
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(timezone_name)
    except Exception:
        # Fallback if timezone not found
        return f"Error: Could not find timezone '{timezone_name}'. Please use a standard IANA timezone like 'Asia/Tokyo'."
    
    current_time = datetime.datetime.now(tz)
    return f"The current time in {timezone_name} is {current_time.strftime('%A, %B %d, %Y at %I:%M %p')}"
