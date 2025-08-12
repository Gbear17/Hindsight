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
GREEN="\033[0;32m"; YELLOW="\033[0;33m"; CYAN="\033[0;36m"; NC="\033[0m"

printf "${GREEN}--- Regenerating Hindsight System Configuration Files ---${NC}\n"

# --- Automatically detect the project path ---
HINDSIGHT_PATH=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
APP_PATH="$HINDSIGHT_PATH/app"

printf "Project Path Detected: %s\n" "$HINDSIGHT_PATH"
mkdir -p "$HOME/.config/systemd/user" "$HOME/.local/share/applications" "$HOME/.config/autostart"

# --- Write Systemd Service Files ---
cat > "$HOME/.config/systemd/user/hindsight-api.service" << EOL
[Unit]
Description=Hindsight Search API Service
[Service]
ExecStart=$APP_PATH/venv/bin/gunicorn --enable-stdio-inheritance --bind localhost:5000 hindsight_api:app
WorkingDirectory=$APP_PATH
Restart=always
Environment="GOOGLE_APPLICATION_CREDENTIALS=$APP_PATH/service-account.json"
[Install]
WantedBy=default.target
EOL
cat > "$HOME/.config/systemd/user/hindsight-rebuild.service" << EOL
[Unit]
Description=Hindsight FAISS Index Rebuild
[Service]
ExecStart=$APP_PATH/venv/bin/python $APP_PATH/rebuild_index.py
Environment="GOOGLE_APPLICATION_CREDENTIALS=$APP_PATH/service-account.json"
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
WorkingDirectory=$APP_PATH
ExecStart=$APP_PATH/scripts/start_daemon.sh
Restart=always
RestartSec=3
Environment=DISPLAY=:0
[Install]
WantedBy=default.target
EOL

# --- Write Desktop & Autostart Files ---
cat > "$HOME/.local/share/applications/hindsight-manager.desktop" << EOL
[Desktop Entry]
Type=Application
Name=Hindsight Manager
Comment=Manage and monitor Hindsight backend services
Exec=gnome-terminal --geometry=90x24 -- "$APP_PATH/scripts/launch_manager.sh"
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

printf "Configuration files have been rewritten.\n"

# --- Automatically reload services ---
printf "\n${CYAN}--- Reloading system services and application database... ---${NC}\n"
systemctl --user daemon-reload
update-desktop-database "$HOME/.local/share/applications"
printf "${GREEN}✅ Reconfiguration complete!${NC}\n"
