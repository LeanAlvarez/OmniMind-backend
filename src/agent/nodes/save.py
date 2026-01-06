"""save node: persist item data to supabase and trigger webhook if needed."""

import logging
from datetime import datetime
from typing import Any, Dict

import httpx

from src.core.config import settings
from src.core.schemas import AgentState
from src.services.supabase_service import supabase_service

logger = logging.getLogger(__name__)


def _format_expiry_date(expiry_date: str | None) -> str | None:
    """format expiry_date as iso timestamp.
    
    args:
        expiry_date: date string in yyyy-mm-dd format or iso format
        
    returns:
        iso timestamp string or None
    """
    if not expiry_date:
        return None
    
    try:
        # if already in iso format, return as is
        if "T" in expiry_date or expiry_date.endswith("Z"):
            return expiry_date
        
        # parse yyyy-mm-dd format and convert to iso timestamp
        date_obj = datetime.strptime(expiry_date, "%Y-%m-%d")
        return date_obj.isoformat() + "Z"
    except Exception as e:
        logger.warning(f"error formatting expiry_date '{expiry_date}': {str(e)}")
        return expiry_date


def _format_item_data(state: AgentState) -> Dict[str, Any]:
    """format state data for items table.
    
    maps processed_data and metadata to table columns:
    name, category, expiry_date, brand, raw_input, metadata.
    
    args:
        state: current agent state
        
    returns:
        formatted dictionary for items table
    """
    processed_data = state.get("processed_data", {})
    metadata = state.get("metadata", {})
    
    # map to table columns
    item_data = {
        "name": processed_data.get("item_name"),
        "category": state.get("category"),
        "expiry_date": _format_expiry_date(processed_data.get("expiry_date")),
        "brand": processed_data.get("brand"),
        "raw_input": str(state.get("raw_input", "")),
        "metadata": metadata,
    }
    
    # remove None values
    item_data = {k: v for k, v in item_data.items() if v is not None}
    
    return item_data


async def _call_n8n_webhook(state: AgentState) -> None:
    """call n8n webhook asynchronously if configured and next_action is set.
    
    args:
        state: current agent state
    """
    if not settings.n8n_webhook_url:
        logger.debug("n8n webhook url not configured, skipping")
        return
    
    next_action = state.get("next_action")
    if not next_action or next_action == "complete":
        logger.debug("no next_action to trigger webhook")
        return
    
    try:
        # prepare webhook payload with item details
        payload = {
            "next_action": next_action,
            "category": state.get("category"),
            "processed_data": state.get("processed_data"),
            "metadata": state.get("metadata"),
            "item_name": state.get("processed_data", {}).get("item_name"),
            "expiry_date": state.get("processed_data", {}).get("expiry_date"),
            "brand": state.get("processed_data", {}).get("brand"),
        }
        
        # async http post call to n8n webhook
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.n8n_webhook_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(f"n8n webhook called successfully: {response.status_code}")
        
    except Exception as e:
        logger.warning(f"error calling n8n webhook: {str(e)}")


def save_node(state: AgentState) -> Dict[str, Any]:
    """save node: persist item to database and trigger webhook.
    
    maps processed_data and metadata to table columns,
    persists via supabase_service, and calls n8n webhook if next_action is set.
    
    args:
        state: current agent state
        
    returns:
        updated state dict
    """
    logger.info("executing save node")
    
    try:
        # format data for items table
        item_data = _format_item_data(state)
        
        # persist to supabase via service
        inserted_item = supabase_service.insert_item(item_data)
        
        # call n8n webhook if needed (fire and forget)
        # note: langgraph nodes are sync, so we'll use httpx sync for now
        # in a fully async context, this would be awaited
        next_action = state.get("next_action")
        if next_action and next_action != "complete" and settings.n8n_webhook_url:
            try:
                payload = {
                    "next_action": next_action,
                    "category": state.get("category"),
                    "processed_data": state.get("processed_data"),
                    "metadata": state.get("metadata"),
                    "item_name": state.get("processed_data", {}).get("item_name"),
                    "expiry_date": state.get("processed_data", {}).get("expiry_date"),
                    "brand": state.get("processed_data", {}).get("brand"),
                }
                # sync call for now (can be made async in future)
                httpx.post(settings.n8n_webhook_url, json=payload, timeout=10.0)
                logger.info(f"n8n webhook called for next_action: {next_action}")
            except Exception as e:
                logger.warning(f"error calling n8n webhook: {str(e)}")
        
        # update state
        updated_state = dict(state)
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["save_node_executed"] = True
        updated_state["metadata"]["item_id"] = inserted_item.get("id")
        updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["save"]
        
        logger.info(f"save node completed: item_id={inserted_item.get('id')}")
        return updated_state
        
    except Exception as e:
        logger.error(f"save node error: {str(e)}", exc_info=True)
        # update state with error but don't fail the workflow
        updated_state = dict(state)
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["save_error"] = str(e)
        updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["save"]
        return updated_state
