#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/4] Building QUASAR CLI..."
(cd cli && npm run build)

echo "[2/4] Building QUASAR Web UI & server..."
(cd web && npm run build)

echo "[3/4] Cleaning previous dist/ artifacts..."
rm -rf dist/

echo "[4/4] Building Python sdist and wheel..."
python3 -m build

echo "Checking distributions with twine..."
python3 -m twine check dist/*

echo "Done. Built packages:"
ls -lh dist/
