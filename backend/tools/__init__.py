"""
All agent tools, wrapped as LangChain StructuredTools so LangGraph can bind them.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from tools.geocode import geocode_place as _geocode
from tools.birth_chart import compute_birth_chart as _chart
from tools.daily_transits import get_daily_transits as _transits
from tools.knowledge_lookup import knowledge_lookup as _lookup

logger = logging.getLogger(__name__)

# ── Pydantic schemas ─────────────────────────────────────────────────────────


class GeocodeInput(BaseModel):
    place: str = Field(..., description="Human-readable place name, e.g. 'Mumbai, India'")


class BirthChartInput(BaseModel):
    date: str = Field(..., description="Birth date in YYYY-MM-DD format")
    time: str = Field(..., description="Birth time in HH:MM (24-hour) local time. Use '12:00' if unknown.")
    place: str = Field(..., description="Birth place, e.g. 'New Delhi, India'")


class DailyTransitsInput(BaseModel):
    query_date: Optional[str] = Field(
        None, description="Date in YYYY-MM-DD; defaults to today"
    )
    natal_chart_json: Optional[str] = Field(
        None,
        description="JSON string of the natal chart from compute_birth_chart, to compute natal aspects"
    )


class KnowledgeInput(BaseModel):
    query: str = Field(..., description="Topic or question to look up in astrology reference notes")
    top_k: int = Field(3, description="Number of reference passages to return (1–10)")


# ── Wrapper functions ────────────────────────────────────────────────────────


def _safe_geocode(place: str) -> str:
    try:
        return json.dumps(_geocode(place))
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _safe_chart(date: str, time: str, place: str) -> str:
    try:
        return json.dumps(_chart(date, time, place))
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _safe_transits(query_date: Optional[str] = None,
                   natal_chart_json: Optional[str] = None) -> str:
    try:
        natal = None
        if natal_chart_json:
            natal = json.loads(natal_chart_json)
        return json.dumps(_transits(query_date, natal))
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _safe_lookup(query: str, top_k: int = 3) -> str:
    try:
        return json.dumps(_lookup(query, top_k))
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── LangChain tool definitions ───────────────────────────────────────────────

geocode_tool = StructuredTool.from_function(
    func=_safe_geocode,
    name="geocode_place",
    description=(
        "Resolve a place name to latitude, longitude, and timezone. "
        "Call this before computing a birth chart when you need coordinates."
    ),
    args_schema=GeocodeInput,
)

birth_chart_tool = StructuredTool.from_function(
    func=_safe_chart,
    name="compute_birth_chart",
    description=(
        "Compute a natal birth chart using the Swiss Ephemeris. "
        "Returns real planetary positions, house placements, Ascendant, and Midheaven. "
        "Requires: date (YYYY-MM-DD), time (HH:MM 24h), place name."
    ),
    args_schema=BirthChartInput,
)

daily_transits_tool = StructuredTool.from_function(
    func=_safe_transits,
    name="get_daily_transits",
    description=(
        "Fetch current (or given date) planetary transits. "
        "Optionally pass natal_chart_json (JSON string from compute_birth_chart) "
        "to compute transit-to-natal aspects."
    ),
    args_schema=DailyTransitsInput,
)

knowledge_tool = StructuredTool.from_function(
    func=_safe_lookup,
    name="knowledge_lookup",
    description=(
        "Search the curated astrology reference notes for interpretations, "
        "planet meanings, house meanings, aspect definitions, and tone guidelines."
    ),
    args_schema=KnowledgeInput,
)

ALL_TOOLS = [geocode_tool, birth_chart_tool, daily_transits_tool, knowledge_tool]
