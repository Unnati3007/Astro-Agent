"""
AstroAgent graph construction.

Graph topology:
  START → router → reason → (tool_calls?) → tools → reason → … → END

                   ┌─────────────┐
  START ──► router ──► reason ◄──┤ tools      │
                         │       └─────────────┘
                    tool_calls?
                         │ yes ──► tools
                         │ no  ──► END
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import AgentState
from graph.nodes import router_node, reason_node, tool_node, should_continue


def build_graph(checkpointer=None):
    """
    Build and compile the AstroAgent LangGraph graph.

    Parameters
    ----------
    checkpointer : Optional LangGraph checkpointer for conversation persistence.
                   Defaults to MemorySaver (in-memory).
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    builder = StateGraph(AgentState)

    # ── Add nodes ────────────────────────────────────────────────────────
    builder.add_node("router", router_node)
    builder.add_node("reason", reason_node)
    builder.add_node("tools", tool_node)

    # ── Add edges ────────────────────────────────────────────────────────
    builder.add_edge(START, "router")
    builder.add_edge("router", "reason")

    # Conditional edge: after reasoning, either call tools or end
    builder.add_conditional_edges(
        "reason",
        should_continue,
        {"tools": "tools", "__end__": END},
    )

    # After tools, always go back to reasoning
    builder.add_edge("tools", "reason")

    graph = builder.compile(checkpointer=checkpointer)
    return graph


# Singleton for use in the API
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
