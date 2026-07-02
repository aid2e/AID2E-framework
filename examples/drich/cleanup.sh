#!/usr/bin/env bash
set -euo pipefail

DRICH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EPIC_SHARE_DIR="${DRICH_DIR}/work/eic-software/share"

rm -rf \
  "${DRICH_DIR}/output"

find "${DRICH_DIR}/work" \
  -path "${DRICH_DIR}/work/eic-software" -prune -o \
  \( -path "*/drich_trial_*" -o -path "*/geometry/epic" -o -path "*/_scheduler" \) \
  -exec rm -rf {} + 2>/dev/null || true

if [[ -d "${EPIC_SHARE_DIR}" ]]; then
  find "${EPIC_SHARE_DIR}" \
    -maxdepth 1 \
    -type d \
    -regex '.*/epic_[0-9][0-9][0-9]$' \
    -exec rm -rf {} +
fi
