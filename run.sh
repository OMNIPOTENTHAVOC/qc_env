#!/usr/bin/env bash
# run.sh — Start the full QKD system
#
# Launches Node B, Node A, and the Streamlit dashboard in the background.
# All logs are written to logs/. Run from the project root.
#
# Usage:
#   chmod +x run.sh
#   ./run.sh          # start everything
#   ./run.sh stop     # kill all three processes

set -euo pipefail

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# ── Stop ──────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "stop" ]]; then
    echo "Stopping QKD processes..."
    pkill -f "node_b.py"   2>/dev/null && echo "  Node B stopped"   || echo "  Node B was not running"
    pkill -f "node_a.py"   2>/dev/null && echo "  Node A stopped"   || echo "  Node A was not running"
    pkill -f "dashboard.py" 2>/dev/null && echo "  Dashboard stopped" || echo "  Dashboard was not running"
    exit 0
fi

# ── Start ─────────────────────────────────────────────────────────────────────

echo "Starting QKD system..."

# Node B must be up before Node A tries to connect
echo "  [1/3] Starting Node B (port 5002)..."
python api/node_b.py > "$LOG_DIR/node_b.log" 2>&1 &
NODE_B_PID=$!

# Give Node B a moment to bind its port
sleep 1

# Check Node B actually started
if ! kill -0 $NODE_B_PID 2>/dev/null; then
    echo "  ERROR: Node B failed to start. Check $LOG_DIR/node_b.log"
    exit 1
fi

echo "  [2/3] Starting Node A (port 5001)..."
python api/node_a.py > "$LOG_DIR/node_a.log" 2>&1 &
NODE_A_PID=$!

sleep 1

if ! kill -0 $NODE_A_PID 2>/dev/null; then
    echo "  ERROR: Node A failed to start. Check $LOG_DIR/node_a.log"
    kill $NODE_B_PID 2>/dev/null
    exit 1
fi

echo "  [3/3] Starting Streamlit dashboard..."
streamlit run ui/dashboard.py \
    --server.port 8501 \
    --server.headless true \
    > "$LOG_DIR/dashboard.log" 2>&1 &

sleep 2

echo ""
echo "QKD system running:"
echo "  Node B    →  http://localhost:5002"
echo "  Node A    →  http://localhost:5001"
echo "  Dashboard →  http://localhost:8501"
echo ""
echo "Logs: $LOG_DIR/"
echo "Stop: ./run.sh stop"
