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

# Find the absolute path to the 'app' directory
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
APP_PATH="$SCRIPT_DIR/app"

# --- Stop existing services ---
systemctl --user stop hindsight-api.service
systemctl --user stop hindsight-rebuild.timer
pkill -f memory_daemon.py
# Add a small delay to allow processes to terminate cleanly
sleep 2

# --- Run the startup script, which will handle starting and notifications ---
bash "$APP_PATH/scripts/ensure_hindsight_running.sh"
