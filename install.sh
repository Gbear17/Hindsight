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

# Hindsight v0.6+ Installer
# This script handles dependency checking, user configuration,
# and the complete setup of the Hindsight application.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Source the helper file for logging and robust command execution ---
# This assumes install.sh is in the project root and helpers.sh is in app/scripts/
source "$(pwd)/app/scripts/helpers.sh"

# --- 1. Welcome & Pre-flight Checks ---
clear
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN} Hindsight Unified Installer & Updater ${NC}"
echo -e "${GREEN}=======================================${NC}\n"

HINDSIGHT_PATH=$(eval echo ~$USER)/hindsight

if [ -d "$HINDSIGHT_PATH" ]; then
    echo -e "${YELLOW}An existing Hindsight installation was found at ${HINDSIGHT_PATH}.${NC}"
    read -p "Create a backup of the existing installation? (y/n): " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        mkdir -p "$HINDSIGHT_PATH/backups"
        BACKUP_FILE="$HINDSIGHT_PATH/backups/hindsight_backup_$(date +%s).zip"
        log_info "Backing up to ${BACKUP_FILE}..."
        zip -r "$BACKUP_FILE" "$HINDSIGHT_PATH" -x "$HINDSIGHT_PATH/backups/*"
    fi
fi

log_info "Checking System Dependencies"
missing_deps=()
required_deps=("git" "curl" "zip" "recoll" "maim" "xdotool" "tesseract" "tesseract-data-eng" "gnome-terminal")

for dep in "${required_deps[@]}"; do
    if ! command -v "$dep" &> /dev/null; then
        missing_deps+=("$dep")
    fi
done

if [ ${#missing_deps[@]} -ne 0 ]; then
    echo -e "${YELLOW}The following dependencies are missing: ${missing_deps[*]}${NC}"
    read -p "May I install them using 'sudo pacman -S'? (y/n): " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        # This command needs to be run with user interaction, so we don't wrap it in run_command
        sudo pacman -S --noconfirm "${missing_deps[@]}"
    else
        log_error "User aborted. Please install dependencies manually and re-run."
        exit 1
    fi
fi
log_info "All system dependencies are met."

# --- 2. Interactive Configuration ---
echo -e "\n${GREEN}--- User Configuration ---${NC}"
echo "Please provide the following settings (press Enter to accept defaults):"
echo ""
echo "Storage Recommendations (Estimated):"
echo " - 30 days:  ~33 GB"
echo " - 90 days:  ~99 GB"
echo " - 180 days: ~198 GB"
echo " - 365 days: ~402 GB"
read -p "Days of history to keep [90]: " DAYS_TO_KEEP
DAYS_TO_KEEP=${DAYS_TO_KEEP:-90}

read -p "Screenshot polling interval in seconds [5]: " POLL_INTERVAL
POLL_INTERVAL=${POLL_INTERVAL:-5}

read -p "AI model for query refinement [gemini-2.5-flash]: " REFINER_MODEL
REFINER_MODEL=${REFINER_MODEL:-"gemini-2.5-flash"}

echo ""
GIT_BRANCH="main" # Initialize with default value
read -p "Configure developer settings (e.g., git branch)? (y/n): " dev_choice
if [[ "$dev_choice" =~ ^[Yy]$ ]]; then
    read -p "Git branch to check for updates [main]: " dev_branch
    GIT_BRANCH=${dev_branch:-"main"}
fi

# --- 3. Generate hindsight.conf ---
log_info "Generating Configuration File"
APP_PATH="$HINDSIGHT_PATH/app"
SCRIPTS_PATH="$APP_PATH/scripts"
VENV_PATH="$APP_PATH/venv"
DATA_DIR="$HINDSIGHT_PATH/data"

cp resources/hindsight.conf.template hindsight.conf

sed -i "s|%%VERSION%%|0.6|g" hindsight.conf
sed -i "s|%%DAYS_TO_KEEP%%|$DAYS_TO_KEEP|g" hindsight.conf
sed -i "s|%%POLL_INTERVAL%%|$POLL_INTERVAL|g" hindsight.conf
sed -i "s|%%REFINER_MODEL%%|$REFINER_MODEL|g" hindsight.conf
sed -i "s|%%GIT_BRANCH%%|$GIT_BRANCH|g" hindsight.conf
sed -i "s|%%HINDSIGHT_PATH%%|$HINDSIGHT_PATH|g" hindsight.conf
sed -i "s|%%APP_PATH%%|$APP_PATH|g" hindsight.conf
sed -i "s|%%SCRIPTS_PATH%%|$SCRIPTS_PATH|g" hindsight.conf
sed -i "s|%%VENV_PATH%%|$VENV_PATH|g" hindsight.conf
sed -i "s|%%DATA_DIR%%|$DATA_DIR|g" hindsight.conf
sed -i "s|%%SCREENSHOT_DIR%%|$DATA_DIR/screenshots|g" hindsight.conf
sed -i "s|%%OCR_TEXT_DIR%%|$DATA_DIR/ocr_text|g" hindsight.conf
sed -i "s|%%DB_DIR%%|$DATA_DIR/db|g" hindsight.conf
sed -i "s|%%LOG_FILE%%|$DATA_DIR/hindsight.log|g" hindsight.conf
sed -i "s|%%SERVICE_ACCOUNT_JSON%%|$APP_PATH/service-account.json|g" hindsight.conf

log_info "hindsight.conf generated successfully."

# --- 4. Make Source Scripts and Python Fiels Executable ---
log_info "Setting script and python file permissions"
chmod +x "$(pwd)/app/scripts/"*.sh
chmod +x "$(pwd)/app/"*.py
log_info "Script and python file permissions set."

# --- 5. Initial Setup & File Copy ---
log_info "Copying Project Files"
mkdir -p "$HINDSIGHT_PATH"
# rsync -a will now preserve the executable permissions we just set.
run_command rsync -a --exclude='.git/' --exclude='install.sh' "$(pwd)/" "$HINDSIGHT_PATH/"
log_info "Files copied to ${HINDSIGHT_PATH}."

# --- 6. Python Environment Setup ---
log_info "Setting up Python Virtual Environment"
run_command python -m venv "$VENV_PATH"
log_info "Virtual environment created."
run_command "$VENV_PATH/bin/pip" install -r "$HINDSIGHT_PATH/requirements.txt"
log_info "Python requirements installed."

# --- 7 & 8. Execute Configuration & Update ---
log_info "Running Initial Configuration"
"$SCRIPTS_PATH/configure.sh"

log_info "Checking for Updates"
"$SCRIPTS_PATH/update.sh"
update_exit_code=$?

if [ "$update_exit_code" -eq 10 ]; then
    log_info "Update downloaded, re-running configuration"
    "$SCRIPTS_PATH/configure.sh"
fi

# --- 9. Enable Services ---
log_info "Enabling services to start on login..."
run_command systemctl --user enable hindsight-api.service
run_command systemctl --user enable hindsight-daemon.service
run_command systemctl --user enable hindsight-rebuild.timer
log_info "Services enabled."

# --- 10. Final Instructions ---
echo -e "\n${GREEN}✅ Hindsight installation and configuration complete!${NC}"
echo -e "\n${CYAN}--- FINAL STEPS ---${NC}"
echo -e "1. Place your 'service-account.json' file in: ${YELLOW}${APP_PATH}/${NC}"
echo -e "2. Enable services to run after logout with this one-time command:"
echo -e "   ${YELLOW}loginctl enable-linger \$(whoami)${NC}"
echo -e "\n3. ${YELLOW}REBOOT${NC} your computer to apply all changes."
