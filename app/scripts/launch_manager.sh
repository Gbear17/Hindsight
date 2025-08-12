#!/bin/bash
# This script correctly sets up the environment and launches the manager.

# Navigate to the app's root directory (one level up from this script)
cd "$(dirname "$0")/.."

# Activate the virtual environment
source venv/bin/activate

# Run the manager
python manager.py
