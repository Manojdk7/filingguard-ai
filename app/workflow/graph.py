import logging
from typing import Optional
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver

from app.workflow.checkpointer import get_checkpointer
from app.workflow.nodes import (
    complete_node,
    extract_node,
    human_review_node,
    retrieve_node,
    review_routing_node,
    score_node,
    validate_node,
)
from app.workflow.routing import (
    route_after_extract,
    route_after_retrieve,
    route_after_review_routing,
)
from app.workflow.state import FilingWorkflowState

logger = logging.getLogger("filingguard.workflow.graph")


def build_workflow_graph() -> StateGraph:
    """Construct the LangGraph workflow graph definition for FilingGuard AI."""
    builder = StateGraph(FilingWorkflowState)

    # 1. Add nodes
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("extract", extract_node)
    builder.add_node("score", score_node)
    builder.add_node("validate", validate_node)
    builder.add_node("review_routing", review_routing_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("complete", complete_node)

    # 2. Add edges
    builder.add_edge(START, "retrieve")

    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {
            "extract": "extract",
            "complete": "complete",
        },
    )

    builder.add_conditional_edges(
        "extract",
        route_after_extract,
        {
            "score": "score",
            "complete": "complete",
        },
    )

    builder.add_edge("score", "validate")
    builder.add_edge("validate", "review_routing")

    builder.add_conditional_edges(
        "review_routing",
        route_after_review_routing,
        {
            "human_review": "human_review",
            "complete": "complete",
        },
    )

    builder.add_edge("human_review", "complete")
    builder.add_edge("complete", END)

    return builder


def compile_workflow_graph(checkpointer: Optional[SqliteSaver] = None):
    """Compile graph with durable checkpointer."""
    saver = checkpointer or get_checkpointer()
    builder = build_workflow_graph()
    return builder.compile(checkpointer=saver)

