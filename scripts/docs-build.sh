#!/usr/bin/env bash
set -euo pipefail

# Build MkDocs site
if ! command -v mkdocs >/dev/null 2>&1; then
  echo "mkdocs not found. Install docs extras:"
  echo "  pip install -e '.[docs]'"
  exit 1
fi

mkdocs build -f mkdocs.yml --strict
