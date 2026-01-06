"""search service: perform web searches using duckduckgo."""

import logging
from typing import List

from langchain_community.tools import DuckDuckGoSearchRun

logger = logging.getLogger(__name__)

# global search tool instance
_search_tool: DuckDuckGoSearchRun | None = None


def get_search_tool() -> DuckDuckGoSearchRun:
    """get or create duckduckgo search tool instance.
    
    returns:
        DuckDuckGoSearchRun tool instance
    """
    global _search_tool
    
    if _search_tool is None:
        _search_tool = DuckDuckGoSearchRun()
        logger.info("duckduckgo search tool initialized")
    
    return _search_tool


def perform_search(query: str) -> str:
    """perform web search and return summary of results.
    
    args:
        query: search query string
        
    returns:
        summary of search results
    """
    try:
        tool = get_search_tool()
        results = tool.run(query)
        
        if results:
            logger.info(f"search completed for query: {query}")
            return str(results)
        else:
            logger.warning(f"no results found for query: {query}")
            return ""
            
    except Exception as e:
        logger.error(f"error performing search: {str(e)}", exc_info=True)
        return ""


