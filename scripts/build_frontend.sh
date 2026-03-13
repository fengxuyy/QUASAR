#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build_frontend.sh
#
# Bundles the Node/TypeScript CLI into a single self-contained JS file and
# copies it to quasar_node/dist/cli.js so it can be shipped inside the
# quasar-core Python wheel.
#
# Run this BEFORE `python -m build`.
# Requirements: node >= 18, npm
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_DIR="$REPO_ROOT/cli"
OUTPUT_DIR="$REPO_ROOT/quasar_node"

echo "==> Installing Node dependencies..."
cd "$CLI_DIR"
npm install

echo "==> Bundling CLI with esbuild..."
mkdir -p "$OUTPUT_DIR/dist"

# esbuild bundles every import (including ink, react, etc.) into one ESM file.
# --external:fsevents  avoids macOS-only native addon bundling errors on Linux.
npx esbuild src/cli.tsx \
  --bundle \
  --platform=node \
  --format=esm \
  --external:fsevents \
  --define:process.env.DEV=\"false\" \
  --banner:js="import { createRequire as __quasarCreateRequire } from 'module'; const require = __quasarCreateRequire(import.meta.url);" \
  --outfile="$OUTPUT_DIR/dist/cli.js"

# Copy package.json so Node can read version/name metadata at runtime if needed.
cp package.json "$OUTPUT_DIR/package.json"

echo "==> Frontend bundle ready: $OUTPUT_DIR/dist/cli.js"
echo ""
echo "Next step: python -m build"
