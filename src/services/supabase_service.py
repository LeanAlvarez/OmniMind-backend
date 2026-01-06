"""supabase service: handle database operations."""

import logging
from typing import Any, Dict, Optional

from supabase import Client, create_client

from src.core.config import settings

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


# global service instance
supabase_service = SupabaseService()
