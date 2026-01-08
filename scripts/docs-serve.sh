#!/usr/bin/env bash
set -euo pipefail

# Serve MkDocs locally
if ! command -v mkdocs >/dev/null 2>&1; then
  echo "mkdocs not found. Install docs extras:"
  echo "  pip install -e '.[docs]'"
  exit 1
fi

mkdocs serve -f mkdocs.yml -a 0.0.0.0:8000
