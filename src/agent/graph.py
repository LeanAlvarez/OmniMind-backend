"""langgraph definition: orchestrate agent nodes."""

import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from src.core.schemas import AgentState
from src.agent.nodes.classifier import classifier_node
from src.agent.nodes.research import research_node
from src.agent.nodes.save import save_node
from src.agent.nodes.vision import vision_node

logger = logging.getLogger(__name__)


def route_after_vision(state: AgentState) -> Literal["classifier", "error"]:
    """route decision after vision node.
    
    args:
        state: current agent state
        
    returns:
        next node name based on error state
    """
    # check if vision node failed
    if state.get("next_action") == "error" or not state.get("processed_data"):
        return "error"
    return "classifier"


def route_after_classifier(state: AgentState) -> Literal["research", "save", "error"]:
    """route decision after classifier node.
    
    if item is warranty or food and (brand is null or expiry_date is null),
    route to research_node. otherwise, go to save_node.
    
    args:
        state: current agent state
        
    returns:
        next node name based on category and missing data
    """
    next_action = state.get("next_action")
    
    if next_action == "error":
        return "error"
    
    category = state.get("category")
    processed_data = state.get("processed_data", {})
    
    # check if research is needed
    if category in ["warranty", "food", "reading"]:
        brand = processed_data.get("brand")
        expiry_date = processed_data.get("expiry_date")
        item_name = processed_data.get("item_name")
        
        # route to research if brand is missing or (expiry_date is missing and it's warranty)
        if item_name and (not brand or (category == "warranty" and not expiry_date)):
            return "research"
    
    return "save"


def finalize_node(state: AgentState) -> AgentState:
    """finalize node: prepare final state for response.
    
    args:
        state: current agent state
        
    returns:
        final state with next_action set to complete
    """
    logger.info("executing finalize node")
    
    updated_state = dict(state)
    updated_state["next_action"] = "complete"
    updated_state["metadata"] = state.get("metadata", {})
    updated_state["metadata"]["finalize_node_executed"] = True
    updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["finalize"]
    
    logger.info("finalize node completed")
    return updated_state


def error_node(state: AgentState) -> AgentState:
    """error node: handle errors in the workflow.
    
    args:
        state: current agent state with error metadata
        
    returns:
        state with error information
    """
    logger.error(f"error node executed: {state.get('metadata', {}).get('error', 'unknown error')}")
    
    updated_state = dict(state)
    updated_state["next_action"] = "error"
    updated_state["metadata"] = state.get("metadata", {})
    updated_state["metadata"]["error_node_executed"] = True
    updated_state["metadata"]["nodes_executed"] = state.get("metadata", {}).get("nodes_executed", []) + ["error"]
    
    return updated_state


# create the graph
def create_graph() -> StateGraph:
    """create and compile the langgraph state graph.
    
    returns:
        compiled graph app
    """
    # initialize graph
    workflow = StateGraph(AgentState)
    
    # add nodes
    workflow.add_node("vision", vision_node)
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("research", research_node)
    workflow.add_node("save", save_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_node("error", error_node)
    
    # set entry point
    workflow.set_entry_point("vision")
    
    # add edges
    workflow.add_conditional_edges(
        "vision",
        route_after_vision,
        {
            "classifier": "classifier",
            "error": "error",
        },
    )
    workflow.add_conditional_edges(
        "classifier",
        route_after_classifier,
        {
            "research": "research",
            "save": "save",
            "error": "error",
        },
    )
    workflow.add_edge("research", "save")
    workflow.add_edge("save", "finalize")
    workflow.add_edge("finalize", END)
    workflow.add_edge("error", END)
    
    # compile graph
    app = workflow.compile()
    
    logger.info("langgraph compiled successfully")
    return app


# create and export the graph app
app = create_graph()


