#!/bin/bash
# TraceX Demo Run Script
# Starts backend, generates test data, runs ingestion, starts frontend
set -e

echo "═══════════════════════════════════════════════════"
echo "  TraceX — AML Intelligence Demo"
echo "═══════════════════════════════════════════════════"

cd "$(dirname "$0")/.."

# 1. Start backend
echo ""
echo "📦 Starting backend..."
if [ -d "venv" ]; then
    source venv/bin/activate
else
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements_v3.txt
fi

# Start uvicorn in background
uvicorn api.server:app --port 8000 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
sleep 3

# 2. Generate test data
echo ""
echo "📊 Generating test EOD data..."
python scripts/generate_test_eod.py --output data/demo_eod_day1.csv --num-txns 2000 --num-accounts 300 --date "2026/05/31"
python scripts/generate_test_eod.py --output data/demo_eod_day2.csv --num-txns 1500 --num-accounts 250 --date "2026/06/01"

# 3. Initialize system
echo ""
echo "🚀 Initializing system with Day 1 data..."
curl -sS -X POST "http://127.0.0.1:8000/api/init" \
    -H "Content-Type: application/json" \
    -d '{"source":"ibm_aml","filepath":"data/demo_eod_day1.csv"}' | python -m json.tool

# 4. Run incremental ingestion for Day 2
echo ""
echo "📥 Running EOD ingestion for Day 2..."
python scripts/ingest_eod.py --filepath data/demo_eod_day2.csv --date 2026-06-01

# 5. Check health
echo ""
echo "🏥 Health check..."
curl -sS "http://127.0.0.1:8000/api/health" | python -m json.tool

# 6. Start frontend
echo ""
echo "🎨 Starting frontend..."
cd frontend
if [ -d "node_modules" ]; then
    npm run dev &
else
    npm install && npm run dev &
fi
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ TraceX is running!"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop."
echo "═══════════════════════════════════════════════════"

# Wait for background processes
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
