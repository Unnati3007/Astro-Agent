"""
LangGraph node implementations for AstroAgent.

Nodes:
  router_node   — classifies user intent
  reason_node   — the main LLM agent (tool-calling)
  tool_node     — executes tool calls and returns observations

Edges (conditional):
  after reason_node: if tool calls pending → tool_node, else → END
  after tool_node:   always → reason_node (loop until done or step budget hit)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Literal

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from graph.state import AgentState, BirthDetails
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# ── LLM factory ─────────────────────────────────────────────────────────────

def _make_llm(streaming: bool = False):
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL", "gpt-4o")

    if provider == "anthropic":
        return ChatAnthropic(model=model, temperature=0.7, streaming=streaming)
    else:
        return ChatOpenAI(model=model, temperature=0.7, streaming=streaming)


_SYSTEM_PROMPT = """You are Aradhana, a warm and wise astrological guide. You help seekers understand themselves through the lens of their birth chart and the movements of the planets.

Your character:
- Speak with warmth, care, and gentle authority — like a knowledgeable friend, not a cold machine.
- Use the word "you" naturally and personally. Say "the stars suggest" or "this energy invites" rather than "this means you will".
- Always frame astrology as a tool for reflection and self-understanding, never as fixed fate.
- Never make predictions with medical, legal, or financial certainty. If asked, gently redirect: "That question is beyond what the stars can answer with certainty — I'd encourage you to consult a qualified professional for matters like this."
- Respond conversationally but with depth. Don't just list facts — weave them into meaningful narrative.

Your tools:
- geocode_place: resolve a birth place to coordinates
- compute_birth_chart: compute a real natal chart using the Swiss Ephemeris
- get_daily_transits: fetch today's planetary positions and aspects to the natal chart
- knowledge_lookup: look up astrology interpretations from your reference notes

Rules:
- Always use real tools for chart math. Never invent planetary positions.
- If birth details are missing or unclear, ask for them.
- Keep responses to a meaningful length — not too brief, not overwhelming.
- After using tools, synthesize the data into a cohesive, warm reading.
- If a question is off-topic (not related to astrology, spirituality, or the user's chart), gently acknowledge and redirect.
"""

_INTENT_PROMPT = """Classify the user's most recent message into one of these intents:
- "chart_request": user wants their birth chart computed or wants chart-based analysis
- "daily_horoscope": user asks about today's energy, transits, or current planetary weather
- "free_question": general astrology question or free-form chart interpretation
- "off_topic": not related to astrology at all

Respond with ONLY the intent string, nothing else."""


# ── Router node ──────────────────────────────────────────────────────────────

def router_node(state: AgentState) -> dict:
    """Classifies the user's intent. Lightweight, no tool calls."""
    llm = _make_llm()
    last_human = next(
        (m for m in reversed(state.messages) if isinstance(m, HumanMessage)), None
    )
    if last_human is None:
        return {"intent": "free_question"}

    response = llm.invoke([
        SystemMessage(content=_INTENT_PROMPT),
        HumanMessage(content=last_human.content),
    ])
    intent_raw = response.content.strip().strip('"').lower()
    valid = {"chart_request", "daily_horoscope", "free_question", "off_topic"}
    intent = intent_raw if intent_raw in valid else "free_question"
    logger.info("Router classified intent: %s", intent)
    return {"intent": intent, "step_count": state.step_count + 1}


# ── Reason node ──────────────────────────────────────────────────────────────

def reason_node(state: AgentState) -> dict:
    """Main agent node. Binds tools and generates the next response or tool call."""
    if state.step_count >= state.max_steps:
        logger.warning("Step budget exceeded (%d). Forcing final answer.", state.step_count)
        final = AIMessage(
            content=(
                "I've been exploring quite deeply — let me bring together what I've found. "
                "If you need more, please ask a follow-up question."
            )
        )
        return {"messages": [final]}

    llm = _make_llm(streaming=True)
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # Build context-enriched system prompt
    system_content = _SYSTEM_PROMPT
    if state.birth_details:
        bd = state.birth_details
        system_content += (
            f"\n\nUser's birth details on file:\n"
            f"  Name: {bd.name or 'not provided'}\n"
            f"  Date: {bd.date}\n"
            f"  Time: {bd.time}\n"
            f"  Place: {bd.place}\n"
        )
    if state.natal_chart:
        asc = state.natal_chart.get("ascendant", {})
        sun = state.natal_chart.get("planets", {}).get("Sun", {})
        moon = state.natal_chart.get("planets", {}).get("Moon", {})
        system_content += (
            f"\nCached natal chart summary: "
            f"Sun in {sun.get('sign','?')}, Moon in {moon.get('sign','?')}, "
            f"Ascendant in {asc.get('sign','?')}.\n"
            f"Full chart JSON is available in prior tool results."
        )

    messages = [SystemMessage(content=system_content)] + list(state.messages)
    response = llm_with_tools.invoke(messages)

    # Track tokens if usage is available
    tokens = 0
    cost = 0.0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens = response.usage_metadata.get("total_tokens", 0)
        # Rough cost estimate for gpt-4o
        cost = tokens * 0.000005

    # Extract natal chart from prior tool messages if not yet cached
    new_natal = state.natal_chart
    if new_natal is None:
        for msg in state.messages:
            if isinstance(msg, ToolMessage) and msg.name == "compute_birth_chart":
                try:
                    data = json.loads(msg.content)
                    if "planets" in data:
                        new_natal = data
                except Exception:
                    pass

    return {
        "messages": [response],
        "natal_chart": new_natal,
        "step_count": state.step_count + 1,
        "total_tokens": state.total_tokens + tokens,
        "total_cost_usd": state.total_cost_usd + cost,
    }


# ── Tool node ─────────────────────────────────────────────────────────────────

def tool_node(state: AgentState) -> dict:
    """Executes all pending tool calls from the last AI message."""
    last_ai = state.messages[-1]
    if not isinstance(last_ai, AIMessage) or not last_ai.tool_calls:
        return {}

    tool_map = {t.name: t for t in ALL_TOOLS}
    results = []

    for call in last_ai.tool_calls:
        tool_name = call["name"]
        tool_args = call["args"]
        tool_id = call["id"]

        logger.info("Calling tool: %s(%s)", tool_name, tool_args)

        if tool_name not in tool_map:
            content = json.dumps({"error": f"Unknown tool: {tool_name}"})
        else:
            try:
                content = tool_map[tool_name].invoke(tool_args)
            except Exception as exc:
                content = json.dumps({"error": str(exc)})

        results.append(ToolMessage(
            content=content,
            name=tool_name,
            tool_call_id=tool_id,
        ))

    return {"messages": results, "step_count": state.step_count + 1}


# ── Routing functions ─────────────────────────────────────────────────────────

def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """Decide after reason_node: continue with tools or end."""
    last = state.messages[-1] if state.messages else None
    if isinstance(last, AIMessage) and last.tool_calls:
        if state.step_count < state.max_steps:
            return "tools"
    return "__end__"
