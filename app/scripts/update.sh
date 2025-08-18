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

# Hindsight Update Script
# Checks for a new version on the remote git repo and applies updates.

set -e
HINDSIGHT_PATH=$(eval echo ~$USER)/hindsight
CONF_FILE="$HINDSIGHT_PATH/hindsight.conf"
REPO_URL="https://gitlab.com/garrett.wyrick/hindsight.git"

get_config_value() {
    grep "^${1}=" "$CONF_FILE" | cut -d'=' -f2- | sed 's/"//g'
}

GIT_BRANCH=$(get_config_value "GIT_BRANCH")
LOCAL_VERSION=$(get_config_value "VERSION")

echo "--- Hindsight Updater ---"
echo "Current branch: $GIT_BRANCH"
echo "Local version: $LOCAL_VERSION"

# --- 1. Handle First-Time Update (non-git directory) ---
if [ ! -d "$HINDSIGHT_PATH/.git" ]; then
    echo "This appears to be a non-git installation."
    read -p "To check for updates, the installation must be converted to a git repository. Proceed? (y/n): " choice
    if [[ ! "$choice" =~ ^[Yy]$ ]]; then
        echo "Update check cancelled."
        exit 0
    fi
    
    echo "Converting to git repository..."
    BAK_DIR="${HINDSIGHT_PATH}_bak_$(date +%s)"
    mv "$HINDSIGHT_PATH" "$BAK_DIR"
    git clone --branch "$GIT_BRANCH" "$REPO_URL" "$HINDSIGHT_PATH"
    cp "$BAK_DIR/hindsight.conf" "$HINDSIGHT_PATH/hindsight.conf"
    echo "Conversion complete. The original directory has been backed up to $BAK_DIR"
    echo "It is safe to delete the backup directory after verifying your settings."
    # The rest of the script will now run on the new git-based directory
fi

# --- 2. Version Comparison ---
echo "Checking for remote updates..."
REMOTE_CONF_URL="https://gitlab.com/garrett.wyrick/hindsight/-/raw/$GIT_BRANCH/resources/hindsight.conf.template"
REMOTE_VERSION=$(curl -s "$REMOTE_CONF_URL" | grep "^VERSION=" | cut -d'=' -f2- | sed 's/"//g')

if [ -z "$REMOTE_VERSION" ]; then
    echo "Could not fetch remote version. Please check your internet connection."
    exit 1
fi

echo "Remote version: $REMOTE_VERSION"

is_lower=$(printf '%s\n' "$LOCAL_VERSION" "$REMOTE_VERSION" | sort -V | head -n 1)

if [ "$is_lower" != "$LOCAL_VERSION" ] || [ "$LOCAL_VERSION" == "$REMOTE_VERSION" ]; then
    echo "You are on the latest version."
    exit 0
fi

# --- 3. Prompt User ---
echo "An update is available: $LOCAL_VERSION -> $REMOTE_VERSION"
read -p "Would you like to update now? (y/n): " choice
if [[ ! "$choice" =~ ^[Yy]$ ]]; then
    echo "Update cancelled."
    exit 0
fi

# --- 4. Perform Update ---
echo "Updating..."
# Backup user settings before pulling
DAYS_TO_KEEP=$(get_config_value "DAYS_TO_KEEP")
POLL_INTERVAL=$(get_config_value "POLL_INTERVAL")
REFINER_MODEL=$(get_config_value "REFINER_MODEL")
EXCLUDED_APPS=$(get_config_value "EXCLUDED_APPS")

cd "$HINDSIGHT_PATH"
git pull origin "$GIT_BRANCH"

# Restore user settings into the new hindsight.conf
sed -i "s|^DAYS_TO_KEEP=.*|DAYS_TO_KEEP=\"$DAYS_TO_KEEP\"|g" "$CONF_FILE"
sed -i "s|^POLL_INTERVAL=.*|POLL_INTERVAL=\"$POLL_INTERVAL\"|g" "$CONF_FILE"
sed -i "s|^REFINER_MODEL=.*|REFINER_MODEL=\"$REFINER_MODEL\"|g" "$CONF_FILE"
sed -i "s|^EXCLUDED_APPS=.*|EXCLUDED_APPS=\"$EXCLUDED_APPS\"|g" "$CONF_FILE"
sed -i "s|^GIT_BRANCH=.*|GIT_BRANCH=\"$GIT_BRANCH\"|g" "$CONF_FILE" # Also restore branch

echo "Update complete!"
exit 10 # Signal to install.sh that an update was performed