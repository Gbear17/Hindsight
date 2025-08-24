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
APP_PATH="$SCRIPT_DIR/.."   # FIX (was scripts/app)

# --- 1. Check and Start the API Service ---
if systemctl --user is-active --quiet hindsight-api.service; then
  API_STATUS="✅ API: Running"
else
  systemctl --user enable --now hindsight-api.service
  API_STATUS="⚠️ API: Started"
fi

# --- 2. Check and Start the Indexing Timer ---
if systemctl --user is-active --quiet hindsight-rebuild.timer; then
  TIMER_STATUS="✅ Timer: Active"
else
  systemctl --user enable --now hindsight-rebuild.timer
  TIMER_STATUS="⚠️ Timer: Started"
fi

# --- 3. Check and Start the Memory Daemon ---
if systemctl --user is-active --quiet hindsight-daemon.service; then
  DAEMON_STATUS="✅ Daemon: Running"
else
  if systemctl --user start hindsight-daemon.service 2>/dev/null; then
    DAEMON_STATUS="⚠️ Daemon: Started (systemd)"
  else
    (cd "$APP_PATH" && nohup ./scripts/start_daemon.sh &>/dev/null &)
    DAEMON_STATUS="⚠️ Daemon: Started (fallback)"
  fi
fi

# --- Build the final message and send the notification ---
MESSAGE_BODY=$(printf "%s\n%s\n%s" "$API_STATUS" "$TIMER_STATUS" "$DAEMON_STATUS")

notify-send "Hindsight Status" "$MESSAGE_BODY" -i utilities-terminal
notify-send "Hindsight Status" "$MESSAGE_BODY" -i utilities-terminal
