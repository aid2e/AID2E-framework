#!/usr/bin/env bash
set -euo pipefail

# Deploy MkDocs site to GitHub Pages
if ! command -v mkdocs >/dev/null 2>&1; then
  echo "mkdocs not found. Install docs extras:"
  echo "  pip install -e '.[docs]'"
  exit 1
fi

# Requires that the repository has GitHub Pages enabled
mkdocs gh-deploy -f mkdocs.yml --force
