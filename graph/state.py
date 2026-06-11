"""
Shared state schema for the AstroAgent LangGraph graph.
"""
from __future__ import annotations

from typing import Annotated, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class BirthDetails(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    time: str = Field(..., description="HH:MM 24-hour")
    place: str = Field(..., description="Human-readable birth place")
    name: Optional[str] = None


class AgentState(BaseModel):
    """The full state passed between graph nodes."""

    # Conversation messages (LangGraph merges via add_messages)
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # Birth details captured from the form or conversation
    birth_details: Optional[BirthDetails] = None

    # Cached natal chart result (avoid re-computing on every turn)
    natal_chart: Optional[dict] = None

    # Intent classified by the router node
    intent: Optional[str] = None  # "chart_request" | "daily_horoscope" | "free_question" | "off_topic"

    # Running token/cost counters (updated after each LLM call)
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    # Step budget enforcement
    step_count: int = 0
    max_steps: int = 12

    class Config:
        arbitrary_types_allowed = True
