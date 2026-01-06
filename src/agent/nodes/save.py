"""save node: persist item data to supabase and trigger webhook if needed."""

import logging
from datetime import datetime
from typing import Any, Dict, List

import httpx

from src.core.config import settings
from src.core.schemas import AgentState
from src.core.utils import validate_and_fix_date
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
        item_id = inserted_item.get("id")
        
        # insert reminders if present
        processed_data = state.get("processed_data", {})
        reminders = processed_data.get("reminders", [])
        
        # fallback: if expiry_date exists but reminders is empty, create one reminder
        if (not reminders or not isinstance(reminders, list) or len(reminders) == 0) and item_id:
            expiry_date = processed_data.get("expiry_date")
            if expiry_date:
                logger.info(f"no reminders found, creating fallback reminder from expiry_date: {expiry_date}")
                # try to get total amount from processed_data
                total_amount = None
                # look for common amount field names
                for amount_key in ["total_amount", "amount", "total", "monto_total"]:
                    if amount_key in processed_data:
                        total_amount = processed_data.get(amount_key)
                        break
                
                # validate and fix expiry_date before creating reminder
                fixed_expiry_date = validate_and_fix_date(expiry_date)
                if fixed_expiry_date:
                    # create fallback reminder
                    reminders = [{
                        "label": "vencimiento único",
                        "due_date": fixed_expiry_date,
                        "amount": total_amount,
                    }]
                else:
                    logger.warning(f"could not validate expiry_date for fallback reminder: {expiry_date}")
        
        if reminders and isinstance(reminders, list) and item_id:
            logger.info(f"inserting {len(reminders)} reminders for item {item_id}")
            for reminder in reminders:
                if isinstance(reminder, dict):
                    # validate due_date before creating reminder_data
                    reminder_due_date = reminder.get("due_date")
                    if not reminder_due_date:
                        # try to use item's global expiry_date as fallback
                        expiry_date = processed_data.get("expiry_date")
                        if expiry_date:
                            fixed_date = validate_and_fix_date(expiry_date)
                            if fixed_date:
                                reminder_due_date = fixed_date
                                logger.info(f"using expiry_date as fallback for reminder: {fixed_date}")
                            else:
                                logger.warning(f"reminder has no valid due_date and expiry_date fallback failed: {reminder}")
                                continue
                        else:
                            logger.warning(f"reminder has no due_date and no expiry_date fallback available: {reminder}")
                            continue
                    else:
                        # validate and fix the reminder's due_date
                        reminder_due_date = validate_and_fix_date(reminder_due_date)
                        if not reminder_due_date:
                            # try expiry_date as fallback
                            expiry_date = processed_data.get("expiry_date")
                            if expiry_date:
                                reminder_due_date = validate_and_fix_date(expiry_date)
                                if reminder_due_date:
                                    logger.info(f"fixed reminder due_date using expiry_date fallback: {reminder_due_date}")
                                else:
                                    logger.warning(f"reminder due_date invalid and expiry_date fallback failed: {reminder}")
                                    continue
                            else:
                                logger.warning(f"reminder due_date invalid and no expiry_date fallback: {reminder}")
                                continue
                    
                    reminder_data = {
                        "item_id": item_id,
                        "label": reminder.get("label"),
                        "due_date": _format_expiry_date(reminder_due_date),
                        "amount": reminder.get("amount"),
                    }
                    # remove None values (but keep due_date as it's required)
                    reminder_data = {k: v for k, v in reminder_data.items() if k == "due_date" or v is not None}
                    
                    try:
                        supabase_service.insert_reminder(reminder_data)
                    except Exception as e:
                        logger.warning(f"error inserting reminder: {str(e)}")
        
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
