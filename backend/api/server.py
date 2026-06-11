"""
AstroAgent FastAPI server.

Endpoints:
  POST /chat/stream      — SSE stream of agent tokens and events
  POST /chat             — Non-streaming single-response (for eval harness)
  POST /session/birth    — Store birth details for a session
  GET  /session/{id}     — Retrieve session state
  GET  /health           — Health check
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from graph import get_graph, AgentState, BirthDetails

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AstroAgent API", version="1.0.0")

# ── CORS ─────────────────────────────────────────────────────────────────────
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory session store (swap for Redis/DB in production) ─────────────────
_sessions: dict[str, dict] = {}


def _get_or_create_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "session_id": session_id,
            "birth_details": None,
            "natal_chart": None,
        }
    return _sessions[session_id]


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    birth_details: Optional[dict] = None   # { date, time, place, name? }


class BirthDetailsRequest(BaseModel):
    session_id: str
    date: str
    time: str
    place: str
    name: Optional[str] = None


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_agent(
    message: str,
    session_id: str,
    birth_details_dict: Optional[dict],
) -> AsyncIterator[str]:
    """Core async generator that drives the graph and yields SSE events."""
    graph = get_graph()
    session = _get_or_create_session(session_id)

    # Merge birth details
    bd_obj = None
    if birth_details_dict:
        bd_obj = BirthDetails(**birth_details_dict)
        session["birth_details"] = birth_details_dict
    elif session.get("birth_details"):
        bd_obj = BirthDetails(**session["birth_details"])

    config = {"configurable": {"thread_id": session_id}}

    start_time = time.perf_counter()

    yield _sse("start", {"session_id": session_id})

    try:
        async for chunk in graph.astream(
            {
                "messages": [HumanMessage(content=message)],
                "birth_details": bd_obj,
                "natal_chart": session.get("natal_chart"),
            },
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_output in chunk.items():
                if node_output is None:
                    continue

                # Tool activity events
                if node_name == "tools":
                    msgs = node_output.get("messages", [])
                    for msg in msgs:
                        if isinstance(msg, ToolMessage):
                            try:
                                tool_result = json.loads(msg.content)
                                # Don't send full chart JSON — too large
                                if "planets" in tool_result:
                                    tool_result = {"summary": "Natal chart computed", "planets_count": len(tool_result["planets"])}
                            except Exception:
                                tool_result = {"raw": str(msg.content)[:200]}

                            yield _sse("tool_call", {
                                "tool": msg.name,
                                "result_preview": tool_result,
                            })
                            # Cache natal chart in session
                            if msg.name == "compute_birth_chart":
                                try:
                                    full = json.loads(msg.content)
                                    if "planets" in full:
                                        session["natal_chart"] = full
                                except Exception:
                                    pass

                # Token streaming from reason node
                if node_name == "reason":
                    msgs = node_output.get("messages", [])
                    for msg in msgs:
                        if isinstance(msg, AIMessage) and not msg.tool_calls:
                            # Stream content token by token (simulate streaming)
                            content = msg.content
                            if content:
                                # Send full content as one chunk (graph.astream gives updates)
                                yield _sse("token", {"text": content})

        elapsed = time.perf_counter() - start_time
        yield _sse("done", {"elapsed_ms": round(elapsed * 1000)})

    except Exception as exc:
        logger.exception("Graph error: %s", exc)
        yield _sse("error", {"message": str(exc)})


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "astroagent"}


@app.post("/session/birth")
async def set_birth_details(req: BirthDetailsRequest):
    session = _get_or_create_session(req.session_id)
    session["birth_details"] = {
        "date": req.date,
        "time": req.time,
        "place": req.place,
        "name": req.name,
    }
    return {"ok": True, "session_id": req.session_id}


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Return safe subset
    return {
        "session_id": session_id,
        "has_birth_details": session.get("birth_details") is not None,
        "has_natal_chart": session.get("natal_chart") is not None,
    }


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming endpoint."""
    session_id = req.session_id or str(uuid.uuid4())
    return StreamingResponse(
        _stream_agent(req.message, session_id, req.birth_details),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/chat")
async def chat_sync(req: ChatRequest):
    """Non-streaming endpoint used by the eval harness."""
    session_id = req.session_id or str(uuid.uuid4())
    full_text = ""
    tool_calls = []
    elapsed_ms = 0

    async for raw in _stream_agent(req.message, session_id, req.birth_details):
        # Strip SSE framing
        for line in raw.split("\n"):
            if line.startswith("data: "):
                try:
                    evt_data = json.loads(line[6:])
                    if "text" in evt_data:
                        full_text += evt_data["text"]
                    if "tool" in evt_data:
                        tool_calls.append(evt_data["tool"])
                    if "elapsed_ms" in evt_data:
                        elapsed_ms = evt_data["elapsed_ms"]
                except Exception:
                    pass

    return {
        "response": full_text,
        "tool_calls": tool_calls,
        "elapsed_ms": elapsed_ms,
        "session_id": session_id,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=True)
