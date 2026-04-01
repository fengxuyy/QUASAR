#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_DIR="$REPO_ROOT/cli"
OUTPUT_DIR="$REPO_ROOT/quasar_node"

echo "==> Installing CLI dependencies..."
cd "$CLI_DIR"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi

echo "==> Bundling CLI for the Python package..."
mkdir -p "$OUTPUT_DIR/dist"

npx --yes esbuild src/cli.tsx \
  --bundle \
  --platform=node \
  --format=esm \
  --external:fsevents \
  --alias:react-devtools-core=./src/shims/reactDevtoolsCore.ts \
  --define:process.env.DEV=\"false\" \
  --banner:js="import { createRequire as __quasarCreateRequire } from 'module'; const require = __quasarCreateRequire(import.meta.url);" \
  --outfile="$OUTPUT_DIR/dist/cli.js"

cp package.json "$OUTPUT_DIR/package.json"

echo "==> Frontend bundle ready at $OUTPUT_DIR/dist/cli.js"
