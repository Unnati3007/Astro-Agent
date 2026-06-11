# ✦ AstroAgent — Aradhana Internship Assignment

A conversational AI astrologer built with LangGraph and React. Computes real natal charts using the Swiss Ephemeris, fetches live planetary transits, and responds with warmth and care.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- An OpenAI or Anthropic API key

### 1. Clone and set up the backend

```bash
git clone <repo-url>
cd astroagent/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your API key
```

### 2. Run the backend

```bash
cd backend
python -m api.server
# → API available at http://localhost:8000
```

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
# → UI available at http://localhost:5173
```

### 4. Run the evaluation harness

```bash
cd backend
# Make sure the backend is running first
python -m evals.run_evals

# With LLM-as-judge (requires OPENAI_API_KEY):
python -m evals.run_evals --judge

# Run only first 10 cases:
python -m evals.run_evals --limit=10
```

---

## Architecture

### Backend

```
backend/
├── api/
│   └── server.py          FastAPI app — /chat/stream (SSE), /chat, /session/*
├── graph/
│   ├── state.py           AgentState Pydantic schema
│   ├── nodes.py           router_node, reason_node, tool_node, should_continue
│   └── graph.py           LangGraph StateGraph builder
├── tools/
│   ├── geocode.py         geocode_place() — Nominatim/OSM, no API key needed
│   ├── birth_chart.py     compute_birth_chart() — Swiss Ephemeris (pyswisseph)
│   ├── daily_transits.py  get_daily_transits() — current positions + natal aspects
│   ├── knowledge_lookup.py  TF-IDF RAG over astrology_notes.md
│   ├── astrology_notes.md   Curated reference corpus (~30 entries)
│   └── __init__.py        LangChain StructuredTool wrappers
└── evals/
    ├── golden_set.jsonl   25 versioned test cases
    ├── run_evals.py       One-command eval harness
    └── results_log.csv    Historical scorecard log
```

### Frontend

```
frontend/src/
├── components/
│   ├── ChatPage.jsx       Main chat UI, input bar, welcome screen
│   ├── ChatMessage.jsx    User / assistant / system message renderer
│   ├── BirthForm.jsx      Birth details modal with validation
│   ├── ToolActivity.jsx   Live tool-call activity indicator
│   └── StarField.jsx      Animated SVG star background
├── lib/
│   ├── store.js           Zustand store (session, messages, birth details)
│   └── api.js             SSE stream client + REST helpers
└── styles/
    └── global.css         Design tokens, resets
```

---

## LangGraph Graph Diagram

```
                    ┌─────────────────────────────────────┐
                    │              AgentState              │
                    │  messages, birth_details, intent,   │
                    │  natal_chart, step_count, tokens     │
                    └─────────────────────────────────────┘

     ┌──────────┐
     │  START   │
     └────┬─────┘
          │
          ▼
     ┌──────────────────────────────────────────────────────┐
     │  router_node                                          │
     │  Classifies intent: chart_request | daily_horoscope  │
     │                     free_question | off_topic         │
     └────────────────────────┬─────────────────────────────┘
                              │ (always)
                              ▼
     ┌──────────────────────────────────────────────────────┐
     │  reason_node  (LLM with bound tools)                  │
     │  • Reads full conversation + birth context            │
     │  • Decides to answer directly OR call tools           │
     │  • Enforces step budget (max_steps = 12)              │
     └────────────────────────┬─────────────────────────────┘
                              │
              ┌───────────────┴────────────────┐
              │  should_continue()              │
              │                                 │
        tool_calls?                       no tool calls
              │                                 │
              ▼                                 ▼
     ┌─────────────────┐                  ┌──────────┐
     │  tool_node      │                  │   END    │
     │  • geocode      │                  └──────────┘
     │  • birth_chart  │
     │  • transits     │
     │  • knowledge    │
     └────────┬────────┘
              │ (always, loop back)
              └──────────────► reason_node
```

**Key design decisions:**
- `router_node` is lightweight — single LLM call with no tools, just intent classification. This prevents the main reasoning node from spending tokens on routing.
- `reason_node` holds the full system prompt and tool-binding. It is the only node that streams tokens.
- `tool_node` is deterministic — it executes tool calls and wraps errors in `ToolMessage` objects so the LLM can reason about failures gracefully.
- Step budget (12) prevents runaway loops. On budget exhaustion, the agent sends a graceful wrap-up message.
- Natal chart is cached in `AgentState.natal_chart` to avoid re-computing on every turn.

---

## Tools

| Tool | Library | Notes |
|------|---------|-------|
| `geocode_place` | geopy (Nominatim/OSM) | No API key; cached with `lru_cache` |
| `compute_birth_chart` | pyswisseph (Swiss Ephemeris) | Real ephemeris; Moshier fallback built-in |
| `get_daily_transits` | pyswisseph | 5-aspect orb system; relates to natal chart if provided |
| `knowledge_lookup` | Custom TF-IDF | ~30 reference entries; no external embedding API needed |

---

## Evaluation

See [EVALUATION.md](./EVALUATION.md) for full analysis.

**Run the suite:**
```bash
python -m evals.run_evals
```

**Sample scorecard (from results_log.csv):**

| Run | Total | Passed | Pass Rate | p50 | p95 |
|-----|-------|--------|-----------|-----|-----|
| 2025-01-15 | 25 | 19 | 76.0% | 4823ms | 12441ms |
| 2025-01-16 | 25 | 21 | 84.0% | 4201ms | 10983ms |

---

## Known Limitations

1. **No streaming token-by-token from LangGraph**: LangGraph's `astream` with `stream_mode="updates"` gives node-level updates, not per-token streaming. The current implementation sends full assistant text as one SSE `token` event. True per-token streaming would require `stream_mode="messages"` and more complex frontend buffering.

2. **TF-IDF knowledge retrieval**: The `knowledge_lookup` tool uses simple TF-IDF, which can miss semantically similar queries with different vocabulary. Upgrading to Ada embeddings + FAISS would improve recall (see `EVALUATION.md`).

3. **Geocoding accuracy for ambiguous place names**: `"Springfield"` or `"Richmond"` without a country will resolve to the most popular result, which may be wrong. The form asks users to include a country/region.

4. **No birth chart caching across browser sessions**: The natal chart is cached in-memory per session on the backend. A database-backed cache (keyed on date+time+place hash) would eliminate redundant Swiss Ephemeris calls for returning users.

5. **Time zone edge cases**: The `zoneinfo` UTC offset calculation works for the vast majority of historical dates but may have rare inaccuracies for dates before 1970 in regions with complex timezone history. A dedicated `pytz` + `dateutil` pipeline would be more robust.

6. **LLM hallucination risk on interpretations**: The agent grounds chart math in the ephemeris but the narrative interpretation layer is entirely LLM-generated. The `knowledge_lookup` tool mitigates this but doesn't eliminate it.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Agent framework | LangGraph 0.2+ |
| LLM | OpenAI GPT-4o (configurable to Claude 3.5) |
| Ephemeris | pyswisseph (Swiss Ephemeris) |
| Geocoding | geopy / Nominatim (OpenStreetMap) |
| API server | FastAPI + uvicorn |
| Streaming | Server-Sent Events (SSE) |
| Frontend | React 18 + Vite |
| State management | Zustand (with localStorage persistence) |
| Fonts | Cormorant Garamond + DM Sans |
| Eval harness | Custom async pytest-style runner + Rich |

---

*Built with care for the Aradhana internship assignment, 2026.*
