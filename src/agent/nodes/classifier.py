"""classifier node: categorize items based on extracted data."""

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage

from src.core.schemas import AgentState
from src.services.llm_service import llm

logger = logging.getLogger(__name__)

# valid categories
VALID_CATEGORIES = ["food", "warranty", "subscription", "reading"]


def classifier_node(state: AgentState) -> Dict[str, Any]:
    """categorize item based on processed data.
    
    assigns category: food, warranty, subscription, or reading.
    
    args:
        state: current agent state with processed_data
        
    returns:
        updated state dict with category and next_action
    """
    logger.info("executing classifier node")
    
    try:
        processed_data = state.get("processed_data")
        
        if not processed_data:
            # if no processed_data, set error and return
            logger.warning("no processed_data available for classification")
            updated_state = dict(state)
            updated_state["metadata"] = state.get("metadata", {})
            updated_state["metadata"]["error"] = "no processed_data available for classification"
            updated_state["metadata"]["error_node"] = "classifier"
            updated_state["next_action"] = "error"
            return updated_state
        
        item_name = processed_data.get("item_name", "")
        brand = processed_data.get("brand", "")
        
        # build classification prompt
        prompt = f"""categorize this item into one of these categories: food, warranty, subscription, or reading.

item name: {item_name}
brand: {brand or "unknown"}

return json with:
{{
    "category": "one of: food, warranty, subscription, reading",
    "reasoning": "brief explanation"
}}

return only valid json."""
        
        message = HumanMessage(content=prompt)
        response = llm.invoke([message])
        response_text = response.content.strip()
        
        # parse json response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        classification = json.loads(response_text)
        category = classification.get("category", "").lower()
        
        # validate category
        if category not in VALID_CATEGORIES:
            logger.warning(f"invalid category '{category}', defaulting to 'food'")
            category = "food"
        
        # determine next action based on category
        if category in ["warranty"]:
            next_action = "research"
        else:
            next_action = "finalize"
        
        # update state
        updated_state = dict(state)
        updated_state["category"] = category
        updated_state["next_action"] = next_action
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["classifier_node_executed"] = True
        updated_state["metadata"]["classification_reasoning"] = classification.get("reasoning", "")
        updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["classifier"]
        
        logger.info(f"classifier node completed: category={category}, next_action={next_action}")
        return updated_state
        
    except Exception as e:
        logger.error(f"classifier node error: {str(e)}", exc_info=True)
        # update state with error
        updated_state = dict(state)
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["error"] = str(e)
        updated_state["metadata"]["error_node"] = "classifier"
        updated_state["next_action"] = "error"
        return updated_state


