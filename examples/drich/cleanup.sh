#!/usr/bin/env bash
set -euo pipefail

DRICH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EPIC_SHARE_DIR="${DRICH_DIR}/work/eic-software/share"

if [[ -d "${EPIC_SHARE_DIR}" ]]; then
  find "${EPIC_SHARE_DIR}" \
    -maxdepth 1 \
    -type d \
    -regex '.*/epic_[0-9][0-9][0-9]$' \
    -exec rm -rf {} +
fi
