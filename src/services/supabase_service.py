"""supabase service: handle database operations."""

import logging
from typing import Any, Dict, Optional

from supabase import Client, create_client

from src.core.config import settings
from src.core.utils import clean_currency, validate_and_fix_date

logger = logging.getLogger(__name__)


class SupabaseService:
    """supabase service class for database operations."""
    
    def __init__(self):
        """initialize supabase service."""
        self._client: Optional[Client] = None
    
    def _get_client(self) -> Client:
        """get or create supabase client instance.
        
        returns:
            supabase client instance
        """
        if self._client is None:
            if not settings.supabase_url or not settings.supabase_key:
                raise ValueError("supabase_url and supabase_key must be configured")
            
            self._client = create_client(settings.supabase_url, settings.supabase_key)
            logger.info("supabase client initialized")
        
        return self._client
    
    def insert_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """insert item into items table.
        
        args:
            item_data: dictionary with item fields to insert
            
        returns:
            inserted record from supabase
            
        raises:
            Exception: if insert fails
        """
        try:
            client = self._get_client()
            
            # insert into items table
            result = client.table("items").insert(item_data).execute()
            
            if result.data:
                logger.info(f"item inserted successfully: {result.data[0].get('id')}")
                return result.data[0]
            else:
                raise Exception("no data returned from insert")
                
        except Exception as e:
            logger.error(f"error inserting item: {str(e)}", exc_info=True)
            raise
    
    def insert_reminder(self, reminder_data: Dict[str, Any]) -> Dict[str, Any]:
        """insert reminder into reminders table.
        
        args:
            reminder_data: dictionary with reminder fields (item_id, label, due_date, amount)
            
        returns:
            inserted record from supabase
            
        raises:
            Exception: if insert fails
        """
        try:
            client = self._get_client()
            
            # clean and validate amount field
            if "amount" in reminder_data:
                amount_value = reminder_data.get("amount")
                if amount_value is not None:
                    # if it's a string, clean it
                    if isinstance(amount_value, str):
                        cleaned_amount = clean_currency(amount_value)
                        reminder_data["amount"] = cleaned_amount
                    # if it's already a number, ensure it's a float
                    elif isinstance(amount_value, (int, float)):
                        reminder_data["amount"] = float(amount_value)
                    else:
                        reminder_data["amount"] = None
                else:
                    reminder_data["amount"] = None
            
            # validate and fix due_date field
            if "due_date" in reminder_data:
                due_date_value = reminder_data.get("due_date")
                if due_date_value:
                    fixed_date = validate_and_fix_date(due_date_value)
                    reminder_data["due_date"] = fixed_date
                else:
                    reminder_data["due_date"] = None
            
            # safety check: do not insert if due_date is null or invalid
            if not reminder_data.get("due_date"):
                logger.warning(f"cannot insert reminder: due_date is null or invalid. reminder_data: {reminder_data}")
                raise ValueError("due_date is required and cannot be null")
            
            # insert into reminders table
            result = client.table("reminders").insert(reminder_data).execute()
            
            if result.data:
                logger.info(f"reminder inserted successfully: {result.data[0].get('id')}")
                return result.data[0]
            else:
                raise Exception("no data returned from insert")
                
        except Exception as e:
            logger.error(f"error inserting reminder: {str(e)}", exc_info=True)
            raise


# global service instance
supabase_service = SupabaseService()
