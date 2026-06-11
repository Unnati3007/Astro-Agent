#!/bin/bash
# AstroAgent — start backend + frontend together
set -e

echo "✦ Starting AstroAgent..."

# Backend
cd backend
if [ ! -d ".venv" ]; then
  echo "→ Creating Python virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "→ Installing Python dependencies..."
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "⚠️  No .env found — copying from .env.example"
  cp .env.example .env
  echo "   Edit backend/.env and add your API key, then re-run."
  exit 1
fi

echo "→ Starting backend on http://localhost:8000"
python -m api.server &
BACKEND_PID=$!
cd ..

# Frontend
cd frontend
if [ ! -d "node_modules" ]; then
  echo "→ Installing Node dependencies..."
  npm install -q
fi
echo "→ Starting frontend on http://localhost:5173"
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✦ AstroAgent is running:"
echo "   Frontend → http://localhost:5173"
echo "   Backend  → http://localhost:8000"
echo "   API docs → http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
