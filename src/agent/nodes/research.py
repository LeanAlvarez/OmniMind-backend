"""research node: search for missing information and synthesize results."""

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from src.core.schemas import AgentState
from src.services.llm_service import llm
from src.services.search_service import perform_search

logger = logging.getLogger(__name__)


def _should_research(state: AgentState) -> bool:
    """determine if research is needed based on category and missing data.
    
    args:
        state: current agent state
        
    returns:
        true if research should be performed
    """
    category = state.get("category")
    processed_data = state.get("processed_data", {})
    
    # research for warranty, food, or reading categories
    if category not in ["warranty", "food", "reading"]:
        return False
    
    # check if brand or expiry_date is missing
    brand = processed_data.get("brand")
    expiry_date = processed_data.get("expiry_date")
    item_name = processed_data.get("item_name")
    
    if not item_name:
        return False
    
    # research if brand is missing or (expiry_date is missing and it's a warranty)
    if not brand:
        return True
    
    if category == "warranty" and not expiry_date:
        return True
    
    return False


def _build_search_queries(state: AgentState) -> List[str]:
    """build search queries based on missing data.
    
    args:
        state: current agent state
        
    returns:
        list of search queries
    """
    processed_data = state.get("processed_data", {})
    category = state.get("category")
    item_name = processed_data.get("item_name", "")
    
    queries = []
    
    # if brand is missing, search for manufacturer
    if not processed_data.get("brand"):
        queries.append(f"{item_name} manufacturer")
    
    # if expiry_date is missing and it's a warranty, search for warranty info
    if category == "warranty" and not processed_data.get("expiry_date"):
        queries.append(f"standard warranty for {item_name}")
    
    return queries


def _synthesize_search_results(
    search_results: str,
    processed_data: Dict[str, Any],
    category: str,
) -> Dict[str, Any]:
    """use llm to synthesize search results and fill missing fields.
    
    args:
        search_results: combined search results text
        processed_data: current processed data
        category: item category
        
    returns:
        updated processed_data with filled fields
    """
    item_name = processed_data.get("item_name", "")
    current_brand = processed_data.get("brand")
    current_expiry_date = processed_data.get("expiry_date")
    
    prompt = f"""based on the following search results, extract missing information about this item:

item name: {item_name}
category: {category}
current brand: {current_brand or "unknown"}
current expiry_date: {current_expiry_date or "unknown"}

search results:
{search_results}

extract and return json with:
{{
    "brand": "brand name if found in search results, otherwise keep current value or null",
    "expiry_date": "expiry/warranty date in yyyy-mm-dd format if found, otherwise keep current value or null",
    "research_summary": "brief summary of what was found"
}}

if information is not found in search results, use null. return only valid json."""
    
    try:
        message = HumanMessage(content=prompt)
        response = llm.invoke([message])
        response_text = response.content.strip()
        
        # parse json response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        synthesized = json.loads(response_text)
        
        # update processed_data with found information
        updated_data = dict(processed_data)
        
        if synthesized.get("brand") and not current_brand:
            updated_data["brand"] = synthesized.get("brand")
        
        if synthesized.get("expiry_date") and not current_expiry_date:
            updated_data["expiry_date"] = synthesized.get("expiry_date")
        
        return updated_data, synthesized.get("research_summary", "")
        
    except Exception as e:
        logger.error(f"error synthesizing search results: {str(e)}", exc_info=True)
        return processed_data, ""


def research_node(state: AgentState) -> Dict[str, Any]:
    """research node: search for missing information and update processed_data.
    
    triggers if category is warranty, food, or reading and data is missing.
    searches for brand or expiry_date, then uses llm to synthesize results.
    
    args:
        state: current agent state
        
    returns:
        updated state dict with research_notes and updated processed_data
    """
    logger.info("executing research node")
    
    try:
        # check if research is needed
        if not _should_research(state):
            logger.info("research not needed, skipping")
            updated_state = dict(state)
            updated_state["metadata"] = state.get("metadata", {})
            updated_state["metadata"]["research_node_executed"] = True
            updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["research"]
            return updated_state
        
        # build search queries
        queries = _build_search_queries(state)
        
        if not queries:
            logger.info("no search queries generated, skipping")
            updated_state = dict(state)
            updated_state["metadata"] = state.get("metadata", {})
            updated_state["metadata"]["research_node_executed"] = True
            updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["research"]
            return updated_state
        
        # perform searches
        search_results_list = []
        for query in queries:
            logger.info(f"searching for: {query}")
            results = perform_search(query)
            if results:
                search_results_list.append(f"query: {query}\nresults: {results}\n")
        
        # combine search results
        combined_results = "\n".join(search_results_list)
        
        if not combined_results:
            logger.warning("no search results obtained")
            updated_state = dict(state)
            updated_state["research_notes"] = "search performed but no results found"
            updated_state["metadata"] = state.get("metadata", {})
            updated_state["metadata"]["research_node_executed"] = True
            updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["research"]
            return updated_state
        
        # synthesize results using llm
        processed_data = state.get("processed_data", {})
        category = state.get("category", "")
        
        updated_processed_data, research_summary = _synthesize_search_results(
            combined_results,
            processed_data,
            category,
        )
        
        # update state
        updated_state = dict(state)
        updated_state["processed_data"] = updated_processed_data
        updated_state["research_notes"] = research_summary or combined_results[:500]  # limit length
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["research_node_executed"] = True
        updated_state["metadata"]["search_queries"] = queries
        updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["research"]
        
        logger.info(f"research node completed: updated brand={updated_processed_data.get('brand')}, expiry_date={updated_processed_data.get('expiry_date')}")
        return updated_state
        
    except Exception as e:
        logger.error(f"research node error: {str(e)}", exc_info=True)
        # update state with error but continue workflow
        updated_state = dict(state)
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["error"] = str(e)
        updated_state["metadata"]["error_node"] = "research"
        updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["research"]
        return updated_state

