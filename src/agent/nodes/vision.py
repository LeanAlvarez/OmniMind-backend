"""vision node: extract information from images using llm vision capabilities."""

import json
import logging
from typing import Any, Dict
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage

from src.core.schemas import AgentState
from src.core.utils import clean_currency, validate_and_fix_date
from src.services.llm_service import llm

logger = logging.getLogger(__name__)


def _is_valid_url(url: str) -> bool:
    """check if string is a valid url."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def _prepare_image_content(image_url: str | None, image_base64: str | None) -> list[Dict[str, Any]]:
    """prepare image content for vision api.
    
    args:
        image_url: url of the image
        image_base64: base64 encoded image data
        
    returns:
        list of content dicts for vision api
    """
    content = []
    
    if image_url and _is_valid_url(image_url):
        content.append({
            "type": "image_url",
            "image_url": {"url": image_url},
        })
    elif image_base64:
        # remove data url prefix if present
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
            },
        })
    
    return content


def vision_node(state: AgentState) -> Dict[str, Any]:
    """extract item information from image using vision llm.
    
    processes image (url or base64) and extracts:
    - item_name: name of the item
    - expiry_date: expiration date if applicable
    - brand: brand name if visible
    
    args:
        state: current agent state
        
    returns:
        updated state dict with processed_data
    """
    logger.info("executing vision node")
    
    try:
        raw_input = state.get("raw_input", {})
        
        # handle different input formats
        if isinstance(raw_input, str):
            # if raw_input is a string, treat as image_url
            image_url = raw_input if _is_valid_url(raw_input) else None
            image_base64 = None
            text_input = None if image_url else raw_input
        elif isinstance(raw_input, dict):
            image_url = raw_input.get("image_url")
            image_base64 = raw_input.get("image_base64")
            text_input = raw_input.get("text")
        else:
            image_url = None
            image_base64 = None
            text_input = None
        
        # prepare vision prompt
        if image_url or image_base64:
            image_content = _prepare_image_content(image_url, image_base64)
            
            if not image_content:
                raise ValueError("invalid image input: neither url nor base64 provided")
            
            prompt = """you are an expert at reading utility bills and receipts. distinguish clearly between the issue date (fecha de emisión) and the due date (fecha de vencimiento). your goal is to extract the due date for the expiry_date field. if there are multiple due dates, pick the first one (primary due date).

for utility bills (like electricity, water, or internet), look for labels like 'vencimiento', 'fecha de vencimiento', 'vence el', or 'pagar hasta'. do not confuse these with issue dates or emission dates.

important date format rules:
- always return dates in yyyy-mm-dd format
- if you find a partial expiry date in MM/YY or MM/YYYY format, convert it to a full date using the last day of that month (e.g., 01/27 becomes 2027-01-31, 03/2025 becomes 2025-03-31)
- always return a valid yyyy-mm-dd string, never partial dates

important: always populate the reminders list, even if there is only one due date. if you detect multiple payment installments (e.g., cuota 1, cuota 2) or multiple due dates (1° vencimiento, 2° vencimiento), extract all of them and create a clear label for each one. if there is only a single due date (like a simple bill or a food item with expiration), create one reminder with label "vencimiento único".

analyze this image and extract the following information in json format:
{
    "item_name": "name of the item",
    "expiry_date": "primary due date (fecha de vencimiento) in yyyy-mm-dd format if visible, null otherwise. this is the date when payment is due, not the issue date. if multiple dates exist, use the first one. convert partial dates (MM/YY) to full dates (yyyy-mm-dd).",
    "issue_date": "issue date (fecha de emisión) in yyyy-mm-dd format if visible, null otherwise. this is when the bill was issued.",
    "brand": "brand name if visible, null otherwise",
    "reminders": [
        {
            "label": "clear label for this reminder. use 'vencimiento único' for single due dates, or specific labels like 'Cuota 1', '1° Vencimiento', 'Primera cuota' for multiple installments",
            "due_date": "due date in yyyy-mm-dd format. if you find MM/YY or MM/YYYY, convert to full date using last day of month (e.g., 01/27 -> 2027-01-31)",
            "amount": "amount to pay as string (e.g., '100.00', '$ 13.234,20') or null if not visible"
        }
    ]
}

reminders must always contain at least one entry if a due date is found. all dates must be in yyyy-mm-dd format. if you cannot determine a value, use null. return only valid json."""
            
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    *image_content,
                ]
            )
            
            response = llm.invoke([message])
            response_text = response.content.strip()
            
            # parse json response
            # remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            processed_data = json.loads(response_text)
            
            # clean currency amounts in reminders
            if "reminders" in processed_data and isinstance(processed_data["reminders"], list):
                for reminder in processed_data["reminders"]:
                    if isinstance(reminder, dict) and "amount" in reminder:
                        cleaned_amount = clean_currency(reminder.get("amount"))
                        if cleaned_amount is not None:
                            reminder["amount"] = cleaned_amount
                        else:
                            reminder["amount"] = None
            
        elif text_input:
            # for text input, try to extract information
            prompt = f"""you are an expert at reading utility bills and receipts. distinguish clearly between the issue date (fecha de emisión) and the due date (fecha de vencimiento). your goal is to extract the due date for the expiry_date field. if there are multiple due dates, pick the first one (primary due date).

for utility bills (like electricity, water, or internet), look for labels like 'vencimiento', 'fecha de vencimiento', 'vence el', or 'pagar hasta'. do not confuse these with issue dates or emission dates.

important date format rules:
- always return dates in yyyy-mm-dd format
- if you find a partial expiry date in MM/YY or MM/YYYY format, convert it to a full date using the last day of that month (e.g., 01/27 becomes 2027-01-31, 03/2025 becomes 2025-03-31)
- always return a valid yyyy-mm-dd string, never partial dates

important: always populate the reminders list, even if there is only one due date. if you detect multiple payment installments (e.g., cuota 1, cuota 2) or multiple due dates (1° vencimiento, 2° vencimiento), extract all of them and create a clear label for each one. if there is only a single due date (like a simple bill or a food item with expiration), create one reminder with label "vencimiento único".

extract the following information from this text in json format:
{text_input}

return json with:
{{
    "item_name": "name of the item",
    "expiry_date": "primary due date (fecha de vencimiento) in yyyy-mm-dd format if mentioned, null otherwise. this is the date when payment is due, not the issue date. if multiple dates exist, use the first one. convert partial dates (MM/YY) to full dates (yyyy-mm-dd).",
    "issue_date": "issue date (fecha de emisión) in yyyy-mm-dd format if mentioned, null otherwise. this is when the bill was issued.",
    "brand": "brand name if mentioned, null otherwise",
    "reminders": [
        {{
            "label": "clear label for this reminder. use 'vencimiento único' for single due dates, or specific labels like 'Cuota 1', '1° Vencimiento', 'Primera cuota' for multiple installments",
            "due_date": "due date in yyyy-mm-dd format. if you find MM/YY or MM/YYYY, convert to full date using last day of month (e.g., 01/27 -> 2027-01-31)",
            "amount": "amount to pay as string (e.g., '100.00', '$ 13.234,20') or null if not visible"
        }}
    ]
}}

reminders must always contain at least one entry if a due date is found. all dates must be in yyyy-mm-dd format. return only valid json."""
            
            message = HumanMessage(content=prompt)
            response = llm.invoke([message])
            response_text = response.content.strip()
            
            # parse json response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            processed_data = json.loads(response_text)
            
            # clean currency amounts and validate dates in reminders
            if "reminders" in processed_data and isinstance(processed_data["reminders"], list):
                for reminder in processed_data["reminders"]:
                    if isinstance(reminder, dict):
                        # clean currency amount
                        if "amount" in reminder:
                            cleaned_amount = clean_currency(reminder.get("amount"))
                            if cleaned_amount is not None:
                                reminder["amount"] = cleaned_amount
                            else:
                                reminder["amount"] = None
                        
                        # validate and fix due_date
                        if "due_date" in reminder:
                            fixed_date = validate_and_fix_date(reminder.get("due_date"))
                            if fixed_date:
                                reminder["due_date"] = fixed_date
                            else:
                                reminder["due_date"] = None
        else:
            raise ValueError("no valid input provided: need image_url, image_base64, or text")
        
        # update state
        updated_state = dict(state)
        updated_state["processed_data"] = processed_data
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["vision_node_executed"] = True
        updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["vision"]
        
        logger.info(f"vision node completed: extracted {processed_data}")
        return updated_state
        
    except Exception as e:
        logger.error(f"vision node error: {str(e)}", exc_info=True)
        # update state with error
        updated_state = dict(state)
        updated_state["metadata"] = state.get("metadata", {})
        updated_state["metadata"]["error"] = str(e)
        updated_state["metadata"]["error_node"] = "vision"
        updated_state["next_action"] = "error"
        return updated_state
