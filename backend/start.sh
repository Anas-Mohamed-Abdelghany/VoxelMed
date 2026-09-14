#!/bin/bash
set -e

echo "=== VoxelMed Backend ==="
echo "Installing dependencies..."
pip install -r requirements.txt

DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(dirname "$DIR")"

echo "Starting FastAPI server on port 8000..."
cd "$DIR"
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

echo ""
echo "To run the desktop app instead, from $PARENT:"
echo "  python -m backend.app"
