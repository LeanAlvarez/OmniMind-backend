"""fastapi application: main server and routes."""

import base64
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.core.schemas import AgentState, IngestRequest, IngestResponse
from src.agent.graph import app as graph_app

logger = logging.getLogger(__name__)

# initialize fastapi app
app = FastAPI(
    title="OmniMind Backend",
    description="LangGraph agent for processing images/text and categorizing items",
    version="0.1.0",
)

# configure cors middleware for kmp app (android/ios)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# maximum file size: 5mb
MAX_FILE_SIZE = 5 * 1024 * 1024


def _parse_metadata(metadata_str: str) -> Dict[str, Any]:
    """parse metadata string to dictionary.
    
    args:
        metadata_str: json string or empty string
        
    returns:
        parsed metadata dictionary
    """
    if not metadata_str or metadata_str.strip() == "":
        return {}
    
    try:
        return json.loads(metadata_str)
    except json.JSONDecodeError:
        logger.warning(f"invalid metadata json, using empty dict: {metadata_str[:50]}")
        return {}


def _file_to_base64(file_bytes: bytes) -> str:
    """convert file bytes to base64 string.
    
    args:
        file_bytes: raw file bytes
        
    returns:
        base64 encoded string
    """
    return base64.b64encode(file_bytes).decode("utf-8")


def _prepare_raw_input(
    file_base64: Optional[str] = None,
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    text: Optional[str] = None,
) -> str | Dict[str, Any]:
    """prepare raw_input from request parameters.
    
    supports file upload (as base64), url, base64, or text input.
    maintains compatibility with url-based testing.
    
    args:
        file_base64: base64 encoded file from upload
        image_url: image url (for testing)
        image_base64: base64 encoded image
        text: text input
        
    returns:
        raw_input in format expected by agent state
    """
    # prioritize file upload if provided
    if file_base64:
        return {"image_base64": file_base64}
    
    # fallback to url for testing
    if image_url:
        return image_url
    
    # use base64 if provided
    if image_base64:
        return {"image_base64": image_base64}
    
    # use text if provided
    if text:
        return text
    
    return ""


@app.post("/ingest", response_model=IngestResponse)
async def ingest_item(
    file: Optional[UploadFile] = File(None, description="image file to process"),
    image_url: Optional[str] = Form(None, description="image url (for testing)"),
    image_base64: Optional[str] = Form(None, description="base64 encoded image"),
    text: Optional[str] = Form(None, description="text input"),
    metadata: str = Form("{}", description="metadata as json string"),
) -> IngestResponse:
    """ingest endpoint: process image/text and categorize item.
    
    accepts multipart form data with file upload or url/base64/text for testing.
    converts uploaded files to base64 for compatibility with vision node.
    
    args:
        file: uploaded image file (max 5mb)
        image_url: image url (for testing compatibility)
        image_base64: base64 encoded image
        text: text input
        metadata: json string with additional metadata
        
    returns:
        ingest response with processed data, category, and metadata
        
    raises:
        HTTPException: if input validation fails, file too large, or graph execution fails
    """
    logger.info("received ingest request")
    
    # validate that at least one input is provided
    if not file and not image_url and not image_base64 and not text:
        raise HTTPException(
            status_code=400,
            detail="at least one input must be provided: file, image_url, image_base64, or text",
        )
    
    try:
        # handle file upload
        file_base64: Optional[str] = None
        if file and file.size > 0:
            # check file size
            file_bytes = await file.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"file size exceeds maximum of {MAX_FILE_SIZE / (1024 * 1024):.1f}MB",
                )
            
            # convert to base64
            file_base64 = _file_to_base64(file_bytes)
            logger.info(f"file uploaded: {file.filename}, size: {len(file_bytes)} bytes")
        
        # parse metadata
        parsed_metadata = _parse_metadata(metadata)
        
        # prepare raw input (prioritize file, then url, then base64, then text)
        raw_input = _prepare_raw_input(
            file_base64=file_base64,
            image_url=image_url,
            image_base64=image_base64,
            text=text,
        )
        
        # prepare initial state for the graph
        initial_state: AgentState = {
            "raw_input": raw_input,
            "processed_data": None,
            "category": None,
            "research_notes": None,
            "metadata": {
                **parsed_metadata,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "request_received": True,
            },
            "next_action": None,
        }
        
        logger.info(f"invoking graph with initial state: raw_input type={type(raw_input).__name__}")
        
        # run the graph asynchronously
        result = await graph_app.ainvoke(initial_state)
        
        logger.info(f"graph execution completed: category={result.get('category')}, next_action={result.get('next_action')}")
        
        # convert result to response model
        response = IngestResponse(
            raw_input=result.get("raw_input"),
            processed_data=result.get("processed_data"),
            category=result.get("category"),
            research_notes=result.get("research_notes"),
            metadata=result.get("metadata", {}),
            next_action=result.get("next_action"),
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"error processing ingest request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"internal server error: {str(e)}",
        )


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """health check endpoint.
    
    returns:
        status information
    """
    return {
        "status": "healthy",
        "service": "omnimind-backend",
        "version": "0.1.0",
    }
