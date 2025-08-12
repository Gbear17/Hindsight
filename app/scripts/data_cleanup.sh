#!/bin/bash
# Hindsight: A Personal Memory Archive
# Copyright (C) 2025 gcwyrick
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# --- Configuration ---
# Find the absolute path to the 'app' directory, where config.py lives
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
APP_PATH="$SCRIPT_DIR/.."
CONFIG_FILE="$APP_PATH/config.py"
DATA_PATH="$APP_PATH/../data"

# Read the DAYS_TO_KEEP variable from the Python config file
DAYS_TO_KEEP=$(grep '^DAYS_TO_KEEP' "$CONFIG_FILE" | cut -d '=' -f 2 | tr -d ' ')

# Check if DAYS_TO_KEEP was read correctly
if [[ -z "$DAYS_TO_KEEP" ]]; then
    echo "Hindsight Cleanup ERROR: Could not read DAYS_TO_KEEP from config.py. Exiting."
    exit 1
fi

echo "Hindsight Cleanup: Deleting files older than $DAYS_TO_KEEP days..."

# Delete old text files and screenshots
find "$DATA_PATH/ocr_text/" -type f -name "*.txt" -mtime "+$DAYS_TO_KEEP" -delete
find "$DATA_PATH/screenshots/" -type f -name "*.png" -mtime "+$DAYS_TO_KEEP" -delete

echo "Hindsight Cleanup: Old data deleted. Removing FAISS index and ID map to trigger a full rebuild on the next cycle."

# Remove the index files. The main rebuild timer will create a new, clean index.
rm -f "$DATA_PATH/db/hindsight_faiss.index"
rm -f "$DATA_PATH/db/hindsight_id_map.json"

echo "Hindsight Cleanup: Complete."