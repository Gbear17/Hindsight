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

set -e
GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[0;33m"; CYAN="\033[0;36m"; NC="\033[0m"
log_step() { printf "\n${GREEN}--- %s ---${NC}\n" "$1"; }
log_error() { printf "${RED}ERROR: %s${NC}\n" "$1"; }

GITLAB_REPO_URL="https://gitlab.com/garrett.wyrick/hindsight.git"

# --- Function to check for core system dependencies ---
install_system_deps() {
    log_step "Checking for core system dependencies..."
    local missing_deps=()
    local required_deps=("git" "recoll" "maim" "xdotool" "tesseract" "tesseract-data-eng" "docker" "zip" "noto-fonts-emoji" "gnome-terminal")
    
    if ! command -v pacman &> /dev/null; then
        log_error "This installer currently only supports Arch Linux via 'pacman'. Aborting."
        exit 1
    fi

    for dep in "${required_deps[@]}"; do
        if ! pacman -Q "$dep" &> /dev/null; then missing_deps+=("$dep"); fi
    done

    if [ ${#missing_deps[@]} -ne 0 ]; then
        printf "${YELLOW}The following dependencies are missing: %s${NC}\n" "${missing_deps[*]}"
        read -p "May I install them using 'sudo pacman -S'? (y/n) " -n 1 -r; echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then sudo pacman -S --noconfirm "${missing_deps[@]}"; else log_error "User aborted."; exit 1; fi
        if [[ $REPLY =~ ^[Yy$ ]; then sudo pacman -S --noconfirm "${missing_deps[@]}"; else log_error "User aborted."; exit 1; fi
    fi
    printf "All core system dependencies are installed.\n"
}

# --- Function to write all configuration files ---
write_config_files() {
    local app_path="$1"
    log_step "Writing Hindsight System Configuration Files"
    mkdir -p "$HOME/.config/systemd/user" "$HOME/.local/share/applications" "$HOME/.config/autostart"

    # Systemd Service Files
    cat > "$HOME/.config/systemd/user/hindsight-api.service" << EOL
[Unit]
Description=Hindsight Search API Service
[Service]
ExecStart=$app_path/venv/bin/gunicorn --enable-stdio-inheritance --bind localhost:5000 hindsight_api:app
WorkingDirectory=$app_path
Restart=always
Environment="GOOGLE_APPLICATION_CREDENTIALS=$app_path/service-account.json"
[Install]
WantedBy=default.target
EOL
    cat > "$HOME/.config/systemd/user/hindsight-rebuild.service" << EOL
[Unit]
Description=Hindsight FAISS Index Rebuild
[Service]
ExecStart=$app_path/venv/bin/python $app_path/rebuild_index.py
Environment="GOOGLE_APPLICATION_CREDENTIALS=$app_path/service-account.json"
EOL
    cat > "$HOME/.config/systemd/user/hindsight-rebuild.timer" << EOL
[Unit]
Description=Run Hindsight FAISS Index Rebuild every 15 minutes
[Timer]
OnCalendar=*:0/15
Persistent=true
[Install]
WantedBy=timers.target
EOL
    cat > "$HOME/.config/systemd/user/hindsight-daemon.service" << EOL
[Unit]
Description=Hindsight Memory Daemon
[Service]
WorkingDirectory=$app_path
ExecStart=$app_path/scripts/start_daemon.sh
Restart=always
RestartSec=3
Environment=DISPLAY=:0
[Install]
WantedBy=default.target
EOL

    # Desktop & Autostart Files
    cat > "$HOME/.local/share/applications/hindsight-manager.desktop" << EOL
[Desktop Entry]
Type=Application
Name=Hindsight Manager
Comment=Manage and monitor Hindsight backend services
Exec=gnome-terminal --geometry=90x24 -- "$app_path/scripts/launch_manager.sh"
Icon=utilities-terminal
Terminal=false
Categories=Utility;
EOL
    cat > "$HOME/.config/autostart/recoll-hindsight.desktop" << EOL
[Desktop Entry]
Name=Recoll Indexer (Hindsight)
Comment=Real-time file indexer for Hindsight
Exec=recollindex -m
Icon=recoll
Terminal=false
Type=Application
X-GNOME-Autostart-enabled=true
EOL
    printf "Configuration files written.\n"
}

# --- Main Installation Logic ---
clear; printf "${GREEN}===============================\n Hindsight v5 Automated Installer \n===============================${NC}\n"

log_step "Installation Path Setup"
HINDSIGHT_PATH="$HOME/hindsight"
printf "Installing Hindsight to the default location: %s\n" "$HINDSIGHT_PATH"
APP_PATH="$HINDSIGHT_PATH/app"

if [ -d "$HINDSIGHT_PATH" ] && [ "$(ls -A $HINDSIGHT_PATH)" ; then
    log_error "Installation directory '$HINDSIGHT_PATH' already exists and is not empty. Aborting."
    exit 1
fi
mkdir -p "$HINDSIGHT_PATH"

install_system_deps

log_step "Installing Hindsight Project Files"
printf "Cloning repository into '%s'...\n" "$HINDSIGHT_PATH"
git clone "$GITLAB_REPO_URL" "$HINDSIGHT_PATH"
cd "$HINDSIGHT_PATH"

log_step "Verifying Python Environment..."
REQUIRED_PYTHON_VERSION="3.12"
REQUIRED_PYTHON_EXEC="python${REQUIRED_PYTHON_VERSION}"
PYENV_PYTHON_VERSION="3.12.4"
PYTHON_TO_USE=""

if command -v "$REQUIRED_PYTHON_EXEC" &> /dev/null; then
    printf "${GREEN}'%s' found. Using existing system installation.${NC}\n" "$REQUIRED_PYTHON_EXEC"
    PYTHON_TO_USE=$(command -v "$REQUIRED_PYTHON_EXEC")
else
    printf "${YELLOW}'%s' not found on your PATH. Attempting to install via pyenv...${NC}\n" "$REQUIRED_PYTHON_EXEC"
    if ! command -v pyenv &> /dev/null; then
        printf "pyenv not found. Installing pyenv and Python build dependencies...\n"
        sudo pacman -S --noconfirm pyenv base-devel openssl zlib xz sqlite bzip2 readline ncurses llvm tk
    fi
    export PYENV_ROOT="$HOME/.pyenv"
    command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    if ! pyenv versions --bare | grep -q "^${PYENV_PYTHON_VERSION}$"; then
        printf "Installing Python %s with pyenv (this may take several minutes)...\n" "$PYENV_PYTHON_VERSION"
        pyenv install "$PYENV_PYTHON_VERSION"
    else
        printf "Python %s already installed via pyenv.\n" "$PYENV_PYTHON_VERSION"
    fi
    PYTHON_TO_USE="$(pyenv root)/versions/${PYENV_PYTHON_VERSION}/bin/python"
fi

printf "Creating virtual environment with %s...\n" "$PYTHON_TO_USE"
"$PYTHON_TO_USE" -m venv "$APP_PATH/venv"

printf "Installing/updating Python packages...\n"
"$APP_PATH/venv/bin/pip" install -q -r "$APP_PATH/requirements.txt"
printf "Python packages are up to date.\n"

log_step "Setting script permissions..."
find "$HINDSIGHT_PATH" -type f -name "*.sh" -exec chmod +x {} +

write_config_files "$APP_PATH"

log_step "Reloading system services and application database..."
systemctl --user daemon-reload
update-desktop-database "$HOME/.local/share/applications"
printf "System services have been reloaded.\n"

log_step "Enabling systemd services to run on login..."
systemctl --user enable hindsight-api.service
systemctl --user enable hindsight-daemon.service
systemctl --user enable hindsight-rebuild.timer
printf "Services enabled.\n"

printf "\n${GREEN}✅ Hindsight installation and configuration complete!${NC}\n"
printf "\n${CYAN}--- FINAL STEPS ---${NC}\n"
printf "1. Place your 'service-account.json' file in: ${YELLOW}%s/${NC}\n" "$APP_PATH"
printf "2. Enable services to run after logout with this one-time command:\n"
printf "   ${YELLOW}loginctl enable-linger \$(whoami)${NC}\n"
printf "\n"
printf "3. ${YELLOW}REBOOT${NC} your computer to apply all changes.\n"

