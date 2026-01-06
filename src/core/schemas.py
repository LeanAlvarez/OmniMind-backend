"""core schemas: agent state and api request/response models."""

from typing import Any, Dict, Optional, TypedDict

from pydantic import BaseModel, Field


class AgentState(TypedDict):
    """agent state definition for langgraph.
    
    follows the structure defined in .cursorrules with additional
    fields for research and processing workflow.
    """
    
    raw_input: str | Dict[str, Any]
    """raw input from user: image url, base64, or text."""
    
    processed_data: Optional[Dict[str, Any]]
    """extracted information: name, dates, etc.
    
    expected fields:
    - item_name: name of the item
    - expiry_date: primary due date (fecha de vencimiento) in yyyy-mm-dd format
    - issue_date: issue date (fecha de emisión) in yyyy-mm-dd format (optional)
    - brand: brand name (optional)
    - reminders: list of reminder objects with label, due_date, and amount (optional)
      each reminder represents a payment installment or due date
    """
    
    category: Optional[str]
    """item category: food, warranty, subscription, or reading."""
    
    research_notes: Optional[str]
    """context from research node for warranty/appliance items."""
    
    metadata: Dict[str, Any]
    """additional metadata: timestamps, node history, errors, etc."""
    
    next_action: Optional[str]
    """routing decision for graph flow."""


class IngestRequest(BaseModel):
    """request model for /ingest endpoint."""
    
    input_data: Optional[str | Dict[str, Any]] = Field(None, description="input data: image url, base64, text, or dict")
    image_url: Optional[str] = Field(None, description="url of the image to process")
    image_base64: Optional[str] = Field(None, description="base64 encoded image data")
    text: Optional[str] = Field(None, description="text input to process")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="additional metadata")
    
    def model_validate_input(self) -> bool:
        """validate that at least one input field is provided."""
        return bool(self.input_data or self.image_url or self.image_base64 or self.text)


class IngestResponse(BaseModel):
    """response model for /ingest endpoint."""
    
    raw_input: str | Dict[str, Any]
    processed_data: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    research_notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    next_action: Optional[str] = None
    
    class Config:
        """pydantic config."""
        json_schema_extra = {
            "example": {
                "raw_input": "https://example.com/image.jpg",
                "processed_data": {
                    "item_name": "milk",
                    "expiry_date": "2024-12-31",
                    "issue_date": None,
                    "brand": "example brand",
                    "reminders": [
                        {
                            "label": "Cuota 1",
                            "due_date": "2024-12-31",
                            "amount": "100.00"
                        }
                    ],
                },
                "category": "food",
                "research_notes": None,
                "metadata": {
                    "timestamp": "2024-01-01T00:00:00Z",
                    "nodes_executed": ["vision", "classifier"],
                },
                "next_action": "complete",
            }
        }
