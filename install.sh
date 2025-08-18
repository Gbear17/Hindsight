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
GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[0;33m"; CYAN="\033[0;36m"; NC="\033[0m"

log_step() { printf "\n%b--- %s ---%b\n" "${GREEN}" "$1" "${NC}"; }
log_error() { printf "%bERROR: %s%b\n" "${RED}" "$1" "${NC}"; }

# --- 1. Welcome & Pre-flight Checks ---
clear
printf "%b=======================================\n Hindsight Unified Installer & Updater \n=======================================%b\n" "$GREEN" "$NC"

HINDSIGHT_PATH=$(eval echo ~$USER)/hindsight

if [ -d "$HINDSIGHT_PATH" ]; then
    printf "${YELLOW}An existing Hindsight installation was found at %s.${NC}\n" "$HINDSIGHT_PATH"
    read -p "Create a backup of the existing installation? (y/n): " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        mkdir -p "$HINDSIGHT_PATH/backups"
        BACKUP_FILE="$HINDSIGHT_PATH/backups/hindsight_backup_$(date +%s).zip"
        printf "Backing up to %s...\n" "$BACKUP_FILE"
        zip -r "$BACKUP_FILE" "$HINDSIGHT_PATH" -x "$HINDSIGHT_PATH/backups/*"
    fi
fi

log_step "Checking System Dependencies"
missing_deps=()
required_deps=("git" "curl" "zip" "recoll" "maim" "xdotool" "tesseract" "gnome-terminal")

for dep in "${required_deps[@]}"; do
    if ! command -v "$dep" &> /dev/null; then
        missing_deps+=("$dep")
    fi
done

if [ ${#missing_deps[@]} -ne 0 ]; then
    printf "${YELLOW}The following dependencies are missing: %s${NC}\n" "${missing_deps[*]}"
    read -p "May I install them using 'sudo pacman -S'? (y/n): " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        sudo pacman -S --noconfirm "${missing_deps[@]}"
    else
        log_error "User aborted. Please install dependencies manually and re-run."
        exit 1
    fi
fi
printf "All system dependencies are met.\n"

# --- 2. Interactive Configuration ---
log_step "User Configuration"
printf "Please provide the following settings (press Enter to accept defaults):\n\n"

printf "Storage Recommendations (Estimated):\n"
printf " - 30 days:  ~33 GB\n"
printf " - 90 days:  ~99 GB\n"
printf " - 180 days: ~198 GB\n"
printf " - 365 days: ~402 GB\n"
read -p "Days of history to keep [90]: " DAYS_TO_KEEP
DAYS_TO_KEEP=${DAYS_TO_KEEP:-90}

read -p "Screenshot polling interval in seconds [5]: " POLL_INTERVAL
POLL_INTERVAL=${POLL_INTERVAL:-5}

read -p "AI model for query refinement [gemini-2.5-flash]: " REFINER_MODEL
REFINER_MODEL=${REFINER_MODEL:-"gemini-2.5-flash"}

# --- New Developer Settings Prompt ---
printf "\n"
GIT_BRANCH="main" # Initialize with default value
read -p "Configure developer settings (e.g., git branch)? (y/n): " dev_choice
if [[ "$dev_choice" =~ ^[Yy]$ ]]; then
    read -p "Git branch to check for updates [main]: " dev_branch
    GIT_BRANCH=${dev_branch:-"main"}
fi

# --- 3. Generate hindsight.conf ---
log_step "Generating Configuration File"
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

printf "hindsight.conf generated successfully.\n"

# --- 4. Initial Setup & File Copy ---
log_step "Copying Project Files"
mkdir -p "$HINDSIGHT_PATH"
# Use rsync for a robust copy, excluding git files and the installer itself
rsync -a --exclude='.git/' --exclude='install.sh' "$(pwd)/" "$HINDSIGHT_PATH/"
printf "Files copied to %s.\n" "$HINDSIGHT_PATH"

# --- 5. Python Environment Setup ---
log_step "Setting up Python Virtual Environment"
python -m venv "$VENV_PATH"
"$VENV_PATH/bin/pip" install -r "$HINDSIGHT_PATH/requirements.txt"
printf "Python environment ready.\n"

# --- 6. & 7. Execute Configuration & Update ---
log_step "Running Initial Configuration"
chmod +x "$SCRIPTS_PATH"/*.sh
"$SCRIPTS_PATH/configure.sh"

log_step "Checking for Updates"
"$SCRIPTS_PATH/update.sh"
update_exit_code=$?

if [ "$update_exit_code" -eq 10 ]; then
    log_step "Update downloaded, re-running configuration"
    "$SCRIPTS_PATH/configure.sh"
fi

# --- 8. Final Instructions ---
printf "\n%b✅ Hindsight installation and configuration complete!%b\n" "${GREEN}" "${NC}"
printf "\n%b--- FINAL STEPS ---%b\n" "${CYAN}" "${NC}"
printf "1. Place your 'service-account.json' file in: ${YELLOW}%s/${NC}\n" "$APP_PATH"
printf "2. Enable services to run after logout with this one-time command:\n"
printf "   %bloginctl enable-linger \$(whoami)%b\n" "${YELLOW}" "${NC}"
printf "\n3. %bREBOOT%b your computer to apply all changes.\n" "${YELLOW}" "${NC}"
