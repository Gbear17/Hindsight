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

# Hindsight Configuration Script
# Reads from hindsight.conf to process and deploy systemd and desktop files.

set -e
HINDSIGHT_PATH=$(eval echo ~$USER)/hindsight
CONF_FILE="$HINDSIGHT_PATH/hindsight.conf"

# --- 1. Safe Configuration Parsing ---
get_config_value() {
    grep "^${1}=" "$CONF_FILE" | cut -d'=' -f2- | sed 's/"//g'
}

APP_PATH=$(get_config_value "APP_PATH")
SCRIPTS_PATH=$(get_config_value "SCRIPTS_PATH")
VENV_PATH=$(get_config_value "VENV_PATH")
SERVICE_ACCOUNT_JSON=$(get_config_value "SERVICE_ACCOUNT_JSON")

SYSTEMD_PATH="$HOME/.config/systemd/user"
DESKTOP_APPS_PATH="$HOME/.local/share/applications"
AUTOSTART_PATH="$HOME/.config/autostart"

mkdir -p "$SYSTEMD_PATH" "$DESKTOP_APPS_PATH" "$AUTOSTART_PATH"

# --- 2. Stop Services ---
echo "Stopping all Hindsight services..."
"$SCRIPTS_PATH/stop_hindsight.sh"

# --- 3. Process Templates ---
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
    temp_processed_file="$HINDSIGHT_PATH/$final_filename"

    echo "----------------------------------------"
    echo "Processing: $template_file"
    cp "$source_template_path" "$temp_processed_file"

    # Generic replacements
    sed -i "s|%%HINDSIGHT_PATH%%|$HINDSIGHT_PATH|g" "$temp_processed_file"
    sed -i "s|%%APP_PATH%%|$APP_PATH|g" "$temp_processed_file"
    sed -i "s|%%SCRIPTS_PATH%%|$SCRIPTS_PATH|g" "$temp_processed_file"
    sed -i "s|%%VENV_PATH%%|$VENV_PATH|g" "$temp_processed_file"
    sed -i "s|%%SERVICE_ACCOUNT_JSON%%|$SERVICE_ACCOUNT_JSON|g" "$temp_processed_file"
    
    # --- 4. Deploy Files Safely ---
    destination_path=""
    if [[ "$final_filename" == "recoll-hindsight.desktop" ]]; then
        destination_path="$AUTOSTART_PATH/$final_filename"
    elif [[ "$final_filename" == *.desktop ]]; then
        destination_path="$DESKTOP_APPS_PATH/$final_filename"
    elif [[ "$final_filename" == *.service ]] || [[ "$final_filename" == *.timer ]]; then
        destination_path="$SYSTEMD_PATH/$final_filename"
    fi

    if [ -n "$destination_path" ]; then
        echo "  -> Deploying to: $destination_path"
        rm -f "$destination_path"
        sleep 1
        cp "$temp_processed_file" "$destination_path"
    else
        echo "  -> [WARNING] Unknown file type for $final_filename. Not deployed."
    fi
    
    rm -f "$temp_processed_file" # Cleanup
done

# --- 5. Finalize ---
echo "----------------------------------------"
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "Updating desktop application database..."
update-desktop-database "$DESKTOP_APPS_PATH"

echo "✅ Configuration complete!"
