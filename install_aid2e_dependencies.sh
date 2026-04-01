#!/bin/bash
# AID2E Framework - Install Dependencies Locally
# This script installs Python dependencies from pyproject.toml into the
# current working directory using pip install with --target.
#
# Designed for remote PanDA/iDDS workers where a full virtualenv may not
# be available. Dependencies are installed locally so they can be found
# via PYTHONPATH set by setup_aid2e.sh.
#
# Project: AID2E v0.0.0 - AI assisted Detector Design for EIC

# Do not use set -e; we want to continue past non-critical failures

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Local install target: <script_dir>/.local/lib
LOCAL_LIB="$SCRIPT_DIR/.local/lib"
mkdir -p "$LOCAL_LIB"

echo "============================================="
echo " AID2E - Installing Dependencies Locally"
echo "============================================="
echo "Script directory : $SCRIPT_DIR"
echo "Install target   : $LOCAL_LIB"
echo ""

# Check if pyproject.toml exists
if [ ! -f "$SCRIPT_DIR/pyproject.toml" ]; then
    echo "Error: pyproject.toml not found in $SCRIPT_DIR"
    exit 1
fi

# Install the project and its dependencies locally
echo "Installing aid2e and core dependencies..."
pip install --target "$LOCAL_LIB" "$SCRIPT_DIR" --no-deps  2>/dev/null || \
    echo "Warning: pip install of aid2e package failed, continuing..."

echo ""
echo "Installing core dependencies..."
pip install --target "$LOCAL_LIB" \
    "pyyaml>=5.4" \
    "pydantic>=2.0" \
    "click>=8.0" \
    "numpy" \
    || echo "Warning: Some core dependencies could not be installed."

# Install joblib for local parallel execution
echo ""
echo "Installing joblib..."
pip install --target "$LOCAL_LIB" "joblib>=1.0"  2>/dev/null || true

# Add local lib to PYTHONPATH if not already there
if [[ ":$PYTHONPATH:" != *":$LOCAL_LIB:"* ]]; then
    if [ -z "$PYTHONPATH" ]; then
        export PYTHONPATH="$LOCAL_LIB"
    else
        export PYTHONPATH="$LOCAL_LIB:$PYTHONPATH"
    fi
fi

echo ""
echo "============================================="
echo " AID2E Dependencies Installed Successfully"
echo "============================================="
echo "PYTHONPATH: $PYTHONPATH"
echo ""
echo "Dependencies installed to: $LOCAL_LIB"
