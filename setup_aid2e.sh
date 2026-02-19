#!/bin/bash
# AID2E Framework - Environment Setup Script
# This script activates the virtual environment and sets up PYTHONPATH

# Get the directory where this script is located
current_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment if it exists
if [ -f "$current_dir/.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$current_dir/.venv/bin/activate"
else
    echo "Warning: Virtual environment not found at $current_dir/.venv"
    echo "Please create it with: python3 -m venv .venv"
fi

# Set up PYTHONPATH to include src, tests, examples, and current directory
if [ -z "$PYTHONPATH" ]; then
    # PYTHONPATH is empty or unset, create new one
    export PYTHONPATH="$current_dir/src:$current_dir/tests:$current_dir/examples:$current_dir"
else
    # PYTHONPATH exists, append to it
    export PYTHONPATH="$current_dir/src:$current_dir/tests:$current_dir/examples:$current_dir:$PYTHONPATH"
fi

echo "Environment setup complete!"
echo "PYTHONPATH: $PYTHONPATH"
echo ""
echo "You can now run AID2E commands and scripts."
