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

# Shared helper functions for Hindsight scripts

RED="\033[0;31m"; YELLOW="\033[0;33m"; GREEN="\033[0;32m"; NC="\033[0m"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

run_command() {
    output=$( "$@" 2>&1 ); local exit_code=$?
    while [ $exit_code -ne 0 ]; do
        echo -e "\n${RED}ERROR:${NC} Command failed with exit code ${YELLOW}$exit_code${NC}"
        echo -e "  -> ${YELLOW}$*${NC}\n  Output:\n  ${output}"
        read -p "Do you want to retry or exit? (r/e): " choice
        case "$choice" in
            [Rr]* ) log_info "Retrying..."; output=$( "$@" 2>&1 ); exit_code=$?;;
            [Ee]* ) log_error "User chose to exit."; exit 1;;
            * ) echo "Invalid option.";;
        esac
    done
}
