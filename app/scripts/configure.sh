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

# Reads from hindsight.conf to process and deploy systemd and desktop files.

set -e
HINDSIGHT_PATH=$(eval echo ~$USER)/hindsight
CONF_FILE="$HINDSIGHT_PATH/hindsight.conf"
source "$(dirname "$0")/helpers.sh"

# --- 1. Safe Configuration Parsing ---
get_config_value() {
    grep "^${1}=" "$CONF_FILE" | cut -d'=' -f2- | sed 's/"//g'
}

# Read all necessary values from the config file
APP_PATH=$(get_config_value "APP_PATH")
SCRIPTS_PATH=$(get_config_value "SCRIPTS_PATH")
VENV_PATH=$(get_config_value "VENV_PATH")
TERMINAL_CMD=$(get_config_value "TERMINAL_CMD")

# --- FINAL FIX: Build a direct, robust execution command ---
PYTHON_EXEC="'$VENV_PATH/bin/python'"
MANAGER_SCRIPT="'$APP_PATH/manager.py'"
EXEC_COMMAND=""

if [[ "$TERMINAL_CMD" == "konsole" ]]; then
    # Konsole uses '-e' followed by the command and its arguments
    EXEC_COMMAND="$TERMINAL_CMD -e $PYTHON_EXEC $MANAGER_SCRIPT"
else
    # Most other terminals use '--' followed by the command and its arguments
    EXEC_COMMAND="$TERMINAL_CMD -- $PYTHON_EXEC $MANAGER_SCRIPT"
fi

SYSTEMD_PATH="$HOME/.config/systemd/user"
DESKTOP_APPS_PATH="$HOME/.local/share/applications"
AUTOSTART_PATH="$HOME/.config/autostart"
mkdir -p "$SYSTEMD_PATH" "$DESKTOP_APPS_PATH" "$AUTOSTART_PATH"

# --- Stop Services ---
log_info "Stopping all Hindsight services..."
"$SCRIPTS_PATH/stop_hindsight.sh"

# --- Process Templates ---
TEMPLATE_FILES=(
    "hindsight-manager.desktop.template"
    "hindsight-api.service.template"
    "hindsight-daemon.service.template"
    "hindsight-rebuild.service.template"
    "hindsight-rebuild.timer.template"
    "recoll-hindsight.desktop.template"
)

for template_file in "${TEMPLATE_FILES[@]}"; do
    final_filename="${template_file%.template}"
    source_template_path="$HINDSIGHT_PATH/resources/$template_file"
    temp_processed_file="/tmp/$final_filename"
    cp "$source_template_path" "$temp_processed_file"

    log_info "Processing: $template_file"

    sed -i "s|%%HINDSIGHT_PATH%%|$HINDSIGHT_PATH|g" "$temp_processed_file"
    sed -i "s|%%APP_PATH%%|$APP_PATH|g" "$temp_processed_file"
    sed -i "s|%%SCRIPTS_PATH%%|$SCRIPTS_PATH|g" "$temp_processed_file"
    sed -i "s|%%VENV_PATH%%|$VENV_PATH|g" "$temp_processed_file"
    sed -i "s|%%EXEC_COMMAND%%|$EXEC_COMMAND|g" "$temp_processed_file"
    
    # ... (File deployment logic remains the same) ...
    destination_path=""
    if [[ "$final_filename" == *.desktop ]]; then
        destination_path="$DESKTOP_APPS_PATH/$final_filename"
    elif [[ "$final_filename" == *.service ]] || [[ "$final_filename" == *.timer ]]; then
        destination_path="$SYSTEMD_PATH/$final_filename"
    fi
    # Note: Autostart logic removed for simplicity unless needed.

    if [ -n "$destination_path" ]; then
        log_info "  -> Deploying to: $destination_path"
        mv "$temp_processed_file" "$destination_path"
    else
        log_error "  -> [WARNING] Unknown file type for $final_filename. Not deployed."
        rm -f "$temp_processed_file"
    fi
done

# --- Finalize ---
log_info "Reloading systemd user daemon..."
systemctl --user daemon-reload
log_info "Updating desktop application database..."
update-desktop-database "$DESKTOP_APPS_PATH" &> /dev/null
log_info "✅ Configuration complete!"