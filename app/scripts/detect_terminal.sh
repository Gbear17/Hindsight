#!/bin/bash
# Hindsight: A Personal Memory Archive
# Copyright (C) 2025 gcwyrick
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Hindsight: Terminal Detection & Configuration Script
# This script detects an available terminal, prompts the user if needed,
# and updates the hindsight.conf file with the chosen command.

# Set paths and source helpers
HINDSIGHT_PATH=$(eval echo ~$USER)/hindsight
CONF_FILE="$HINDSIGHT_PATH/hindsight.conf"
# Note: This assumes helpers.sh is in the same directory.
source "$(dirname "$0")/helpers.sh"

detect_terminal() {
    log_info "Detecting available terminal emulators..."
    local found_terminals=()
    # A list of common terminals to search for
    local common_terminals=("gnome-terminal" "konsole" "xfce4-terminal" "terminator" "xterm")

    # Populate the list of found terminals
    for term in "${common_terminals[@]}"; do
        if command -v "$term" &> /dev/null; then
            found_terminals+=("$term")
        fi
    done

    local TERMINAL_CMD=""
    # Case 1: Exactly one terminal was found
    if [ ${#found_terminals[@]} -eq 1 ]; then
        TERMINAL_CMD="${found_terminals[0]}"
        log_info "Automatically selected terminal: $TERMINAL_CMD"
    # Case 2: Multiple terminals were found, so we ask the user
    elif [ ${#found_terminals[@]} -gt 1 ]; then
        echo -e "${YELLOW}Found multiple terminals. Please choose one:${NC}"
        # 'select' is a bash feature that creates a menu
        select term_choice in "${found_terminals[@]}"; do
            if [ -n "$term_choice" ]; then
                TERMINAL_CMD="$term_choice"
                log_info "User selected: $TERMINAL_CMD"
                break
            else
                echo "Invalid selection. Please try again."
            fi
        done
    # Case 3: No common terminals were found
    else
        echo -e "${YELLOW}Could not find a common terminal.${NC}"
        read -p "Please enter the command for your preferred terminal (e.g., alacritty): " TERMINAL_CMD
    fi

    # Update the config file directly if a command was chosen
    if [ -n "$TERMINAL_CMD" ]; then
        # This 'sed' command finds the line starting with TERMINAL_CMD and replaces it.
        # It's safer than relying on placeholders.
        # Inside detect_terminal() in detect_terminal.sh
    sed -i.bak "s|^TERMINAL_CMD=.*|TERMINAL_CMD=$TERMINAL_CMD|g" "$CONF_FILE"
        log_info "Configuration updated with new terminal: $TERMINAL_CMD"
    else
        log_error "No terminal was selected. Configuration not updated."
    fi
}

# Run the main function
detect_terminal