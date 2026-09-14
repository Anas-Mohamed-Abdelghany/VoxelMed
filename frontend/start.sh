#!/bin/bash
set -e

echo "=== VoxelMed Web Frontend ==="
echo "Installing dependencies..."
npm install

echo "Starting Vite dev server on port 3000..."
npm run dev
