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
TEMPLATE_FILE="$HINDSIGHT_PATH/resources/hindsight.conf.template"
REGEN_FLAG=0
for arg in "$@"; do
    if [[ "$arg" == "--regen-config" || "$arg" == "--rebuild-config" ]]; then
        REGEN_FLAG=1
    fi
done
source "$(dirname "$0")/helpers.sh"

# --- 1. Safe Configuration Parsing ---
get_config_value() {
    grep "^${1}=" "$CONF_FILE" | cut -d'=' -f2- | sed 's/"//g'
}

# --- 1a. (Re)Generate config from template if missing or user requested ---
generate_config_from_template() {
    local existing_conf="$1"
    local preserve=0
    [ -f "$existing_conf" ] && preserve=1

    # Defaults
    local default_terminal="konsole"
    local default_days=90
    local default_poll=5
    local default_refiner="gemini-2.5-flash"
    local default_branch="main"

    # Path defaults (may be overridden by existing file)
    local def_APP_PATH="$HINDSIGHT_PATH/app"
    local def_SCRIPTS_PATH="$def_APP_PATH/scripts"
    local def_VENV_PATH="$def_APP_PATH/venv"
    local def_DATA_DIR="$HINDSIGHT_PATH/data"
    local def_SCREENSHOT_DIR="$def_DATA_DIR/screenshots"
    local def_OCR_TEXT_DIR="$def_DATA_DIR/ocr_text"
    local def_DB_DIR="$def_DATA_DIR/db"
    local def_LOG_FILE="$def_DATA_DIR/hindsight.log"
    local def_SERVICE_ACCOUNT_JSON="$def_APP_PATH/service-account.json"
    local def_RECOLL_CONF_DIR="$def_DATA_DIR/recoll"

    # If preserving, pull current values; tolerate missing keys
    if [ $preserve -eq 1 ]; then
        cur() { grep "^$1=" "$existing_conf" | cut -d'=' -f2- | sed 's/"//g'; }
        default_terminal="$(cur TERMINAL_CMD)"; [ -z "$default_terminal" ] && default_terminal="konsole"
        default_days="$(cur DAYS_TO_KEEP)"; [ -z "$default_days" ] && default_days=90
        default_poll="$(cur POLL_INTERVAL)"; [ -z "$default_poll" ] && default_poll=5
        default_refiner="$(cur REFINER_MODEL)"; [ -z "$default_refiner" ] && default_refiner="gemini-2.5-flash"
        default_branch="$(cur GIT_BRANCH)"; [ -z "$default_branch" ] && default_branch=main
        def_APP_PATH="$(cur APP_PATH)"; [ -z "$def_APP_PATH" ] && def_APP_PATH="$HINDSIGHT_PATH/app"
        def_SCRIPTS_PATH="$(cur SCRIPTS_PATH)"; [ -z "$def_SCRIPTS_PATH" ] && def_SCRIPTS_PATH="$HINDSIGHT_PATH/app/scripts"
        def_VENV_PATH="$(cur VENV_PATH)"; [ -z "$def_VENV_PATH" ] && def_VENV_PATH="$HINDSIGHT_PATH/app/venv"
        def_DATA_DIR="$(cur DATA_DIR)"; [ -z "$def_DATA_DIR" ] && def_DATA_DIR="$HINDSIGHT_PATH/data"
        def_SCREENSHOT_DIR="$(cur SCREENSHOT_DIR)"; [ -z "$def_SCREENSHOT_DIR" ] && def_SCREENSHOT_DIR="$def_DATA_DIR/screenshots"
        def_OCR_TEXT_DIR="$(cur OCR_TEXT_DIR)"; [ -z "$def_OCR_TEXT_DIR" ] && def_OCR_TEXT_DIR="$def_DATA_DIR/ocr_text"
        def_DB_DIR="$(cur DB_DIR)"; [ -z "$def_DB_DIR" ] && def_DB_DIR="$def_DATA_DIR/db"
        def_LOG_FILE="$(cur LOG_FILE)"; [ -z "$def_LOG_FILE" ] && def_LOG_FILE="$def_DATA_DIR/hindsight.log"
        def_SERVICE_ACCOUNT_JSON="$(cur SERVICE_ACCOUNT_JSON)"; [ -z "$def_SERVICE_ACCOUNT_JSON" ] && def_SERVICE_ACCOUNT_JSON="$def_APP_PATH/service-account.json"
        def_RECOLL_CONF_DIR="$(cur RECOLL_CONF_DIR)"; [ -z "$def_RECOLL_CONF_DIR" ] && def_RECOLL_CONF_DIR="$def_DATA_DIR/recoll"
        PRESERVE_ENABLE_RECOLL="$(cur ENABLE_RECOLL)"; [ -z "$PRESERVE_ENABLE_RECOLL" ] && PRESERVE_ENABLE_RECOLL=true
        PRESERVE_ENABLE_FAISS="$(cur ENABLE_FAISS)"; [ -z "$PRESERVE_ENABLE_FAISS" ] && PRESERVE_ENABLE_FAISS=true
        PRESERVE_RECOLL_NICENESS="$(cur RECOLL_NICENESS)"; [ -z "$PRESERVE_RECOLL_NICENESS" ] && PRESERVE_RECOLL_NICENESS=10
        PRESERVE_RECOLL_MAX_SECONDS="$(cur RECOLL_MAX_SECONDS)"; [ -z "$PRESERVE_RECOLL_MAX_SECONDS" ] && PRESERVE_RECOLL_MAX_SECONDS=25
        PRESERVE_FAISS_MAX_FILES_PER_CYCLE="$(cur FAISS_MAX_FILES_PER_CYCLE)"; [ -z "$PRESERVE_FAISS_MAX_FILES_PER_CYCLE" ] && PRESERVE_FAISS_MAX_FILES_PER_CYCLE=0
        PRESERVE_FAISS_MAX_SECONDS="$(cur FAISS_MAX_SECONDS)"; [ -z "$PRESERVE_FAISS_MAX_SECONDS" ] && PRESERVE_FAISS_MAX_SECONDS=0
        PRESERVE_EXCLUDED_APPS="$(cur EXCLUDED_APPS)"
    fi

    if [ ! -f "$TEMPLATE_FILE" ]; then
        log_error "Template file not found: $TEMPLATE_FILE"; exit 1
    fi

    [ $preserve -eq 1 ] && cp "$existing_conf" "$existing_conf.bak.$(date +%s)" && log_info "Backed up existing config to $existing_conf.bak.*"

    cp "$TEMPLATE_FILE" "$existing_conf"
    sed -i "s|%%TERMINAL_CMD%%|$default_terminal|g" "$existing_conf"
    sed -i "s|%%DAYS_TO_KEEP%%|$default_days|g" "$existing_conf"
    sed -i "s|%%POLL_INTERVAL%%|$default_poll|g" "$existing_conf"
    sed -i "s|%%REFINER_MODEL%%|$default_refiner|g" "$existing_conf"
    sed -i "s|%%GIT_BRANCH%%|$default_branch|g" "$existing_conf"
    sed -i "s|%%HINDSIGHT_PATH%%|$HINDSIGHT_PATH|g" "$existing_conf"
    sed -i "s|%%APP_PATH%%|$def_APP_PATH|g" "$existing_conf"
    sed -i "s|%%SCRIPTS_PATH%%|$def_SCRIPTS_PATH|g" "$existing_conf"
    sed -i "s|%%VENV_PATH%%|$def_VENV_PATH|g" "$existing_conf"
    sed -i "s|%%DATA_DIR%%|$def_DATA_DIR|g" "$existing_conf"
    sed -i "s|%%SCREENSHOT_DIR%%|$def_SCREENSHOT_DIR|g" "$existing_conf"
    sed -i "s|%%OCR_TEXT_DIR%%|$def_OCR_TEXT_DIR|g" "$existing_conf"
    sed -i "s|%%DB_DIR%%|$def_DB_DIR|g" "$existing_conf"
    sed -i "s|%%LOG_FILE%%|$def_LOG_FILE|g" "$existing_conf"
    sed -i "s|%%SERVICE_ACCOUNT_JSON%%|$def_SERVICE_ACCOUNT_JSON|g" "$existing_conf"
    sed -i "s|%%RECOLL_CONF_DIR%%|$def_RECOLL_CONF_DIR|g" "$existing_conf"

    if [ $preserve -eq 1 ]; then
        # Reapply overrides that could differ from template defaults
        apply_override() { local k="$1"; local v="$2"; grep -q "^$k=" "$existing_conf" && sed -i "s|^$k=.*|$k=$v|" "$existing_conf" || echo "$k=$v" >> "$existing_conf"; }
        apply_override ENABLE_RECOLL "$PRESERVE_ENABLE_RECOLL"
        apply_override ENABLE_FAISS "$PRESERVE_ENABLE_FAISS"
        apply_override RECOLL_NICENESS "$PRESERVE_RECOLL_NICENESS"
        apply_override RECOLL_MAX_SECONDS "$PRESERVE_RECOLL_MAX_SECONDS"
        apply_override FAISS_MAX_FILES_PER_CYCLE "$PRESERVE_FAISS_MAX_FILES_PER_CYCLE"
        apply_override FAISS_MAX_SECONDS "$PRESERVE_FAISS_MAX_SECONDS"
        # EXCLUDED_APPS (quote if contains spaces)
        if [ -n "$PRESERVE_EXCLUDED_APPS" ]; then
            if grep -q '^EXCLUDED_APPS=' "$existing_conf"; then
                sed -i "s|^EXCLUDED_APPS=.*|EXCLUDED_APPS=\"$PRESERVE_EXCLUDED_APPS\"|" "$existing_conf"
            else
                echo "EXCLUDED_APPS=\"$PRESERVE_EXCLUDED_APPS\"" >> "$existing_conf"
            fi
        fi
        log_info "Regenerated hindsight.conf from template (preserved overrides)."
    else
        log_info "Created new hindsight.conf from template."
    fi
}

if [ ! -f "$CONF_FILE" ] || [ $REGEN_FLAG -eq 1 ]; then
    generate_config_from_template "$CONF_FILE"
fi

# Now we can safely read all necessary values from the config file
# Upgrade: ensure new User Settings keys
if ! grep -q '^PAUSE_WHEN_LOCKED=' "$CONF_FILE"; then
    awk '/^\[User Settings\]/{print;print "PAUSE_WHEN_LOCKED=true";next}1' "$CONF_FILE" > "$CONF_FILE.tmp" && mv "$CONF_FILE.tmp" "$CONF_FILE"
    log_info "Injected missing PAUSE_WHEN_LOCKED=true into [User Settings] section"
fi
if ! grep -q '^PAUSE_ON_SUSPEND=' "$CONF_FILE"; then
    awk '/^\[User Settings\]/{print;print "PAUSE_ON_SUSPEND=true";next}1' "$CONF_FILE" > "$CONF_FILE.tmp" && mv "$CONF_FILE.tmp" "$CONF_FILE"
    log_info "Injected missing PAUSE_ON_SUSPEND=true into [User Settings] section"
fi
if ! grep -q '^MANAGER_COLUMNS=' "$CONF_FILE"; then
    awk '/^\[User Settings\]/{print;print "MANAGER_COLUMNS=140";next}1' "$CONF_FILE" > "$CONF_FILE.tmp" && mv "$CONF_FILE.tmp" "$CONF_FILE"
    log_info "Injected missing MANAGER_COLUMNS=140 into [User Settings] section"
fi
if ! grep -q '^MANAGER_ROWS=' "$CONF_FILE"; then
    awk '/^\[User Settings\]/{print;print "MANAGER_ROWS=40";next}1' "$CONF_FILE" > "$CONF_FILE.tmp" && mv "$CONF_FILE.tmp" "$CONF_FILE"
    log_info "Injected missing MANAGER_ROWS=40 into [User Settings] section"
fi
if ! grep -q '^THEME_MODE=' "$CONF_FILE"; then
    awk '/^\[User Settings\]/{print;print "THEME_MODE=auto";next}1' "$CONF_FILE" > "$CONF_FILE.tmp" && mv "$CONF_FILE.tmp" "$CONF_FILE"
    log_info "Injected missing THEME_MODE=auto into [User Settings] section"
fi

APP_PATH=$(get_config_value "APP_PATH")
SCRIPTS_PATH=$(get_config_value "SCRIPTS_PATH")
VENV_PATH=$(get_config_value "VENV_PATH")
TERMINAL_CMD=$(get_config_value "TERMINAL_CMD")
OCR_TEXT_DIR=$(get_config_value "OCR_TEXT_DIR")
DATA_DIR=$(get_config_value "DATA_DIR")
MANAGER_COLUMNS=$(get_config_value "MANAGER_COLUMNS")
MANAGER_ROWS=$(get_config_value "MANAGER_ROWS")

# --- 1b. Ensure new config sections/keys (non-destructive upgrade) ---
ensure_search_section() {
    if ! grep -q "^\[Search\]" "$CONF_FILE"; then
        cat >> "$CONF_FILE" <<EOF

[Search]
ENABLE_RECOLL=true
ENABLE_FAISS=true
RECOLL_CONF_DIR=$DATA_DIR/recoll
RECOLL_NICENESS=10
RECOLL_MAX_SECONDS=25
FAISS_MAX_FILES_PER_CYCLE=0
FAISS_MAX_SECONDS=0
EOF
        log_info "Added missing [Search] section to hindsight.conf"
    else
        # Append any missing keys with defaults
        add_key_if_missing() {
            local key="$1"; shift
            local val="$1"
            if ! grep -q "^$key=" "$CONF_FILE"; then
                # Insert right after [Search] section header for cleanliness
                awk -v k="$key" -v v="$val" 'BEGIN{added=0} {print $0; if ($0 ~ /^\[Search\]/ && added==0){print k"="v; added=1}}' "$CONF_FILE" > "$CONF_FILE.tmp" && mv "$CONF_FILE.tmp" "$CONF_FILE"
                log_info "Injected missing key $key into [Search] section"
            fi
        }
        add_key_if_missing ENABLE_RECOLL true
        add_key_if_missing ENABLE_FAISS true
        add_key_if_missing RECOLL_CONF_DIR "$DATA_DIR/recoll"
        add_key_if_missing RECOLL_NICENESS 10
        add_key_if_missing RECOLL_MAX_SECONDS 25
        add_key_if_missing FAISS_MAX_FILES_PER_CYCLE 0
        add_key_if_missing FAISS_MAX_SECONDS 0
    fi
}

ensure_search_section
RECOLL_CONF_DIR=$(get_config_value "RECOLL_CONF_DIR")

# --- FINAL FIX: Build a direct, robust execution command ---
PYTHON_EXEC="'$VENV_PATH/bin/python'"
MANAGER_SCRIPT="'$APP_PATH/manager.py'"
EXEC_COMMAND=""

SIZE_ARGS=""
if [[ -n "$MANAGER_COLUMNS" && -n "$MANAGER_ROWS" ]]; then
    case "$TERMINAL_CMD" in
                konsole)
                    # Use Konsole property flags in character cells (case sensitive: TerminalColumns/TerminalRows)
                    if [[ -n "$MANAGER_COLUMNS" && -n "$MANAGER_ROWS" ]]; then
                        SIZE_ARGS="-p TerminalColumns=$MANAGER_COLUMNS -p TerminalRows=$MANAGER_ROWS"
                    fi
                ;;
        gnome-terminal|kgx)
            SIZE_ARGS="--geometry=${MANAGER_COLUMNS}x${MANAGER_ROWS}"
            ;;
        xfce4-terminal)
            SIZE_ARGS="--geometry=${MANAGER_COLUMNS}x${MANAGER_ROWS}"
            ;;
        xterm|alacritty)
            SIZE_ARGS="-geometry ${MANAGER_COLUMNS}x${MANAGER_ROWS}"
            ;;
        kitty)
            SIZE_ARGS="--override initial_window_width=${MANAGER_COLUMNS}c --override initial_window_height=${MANAGER_ROWS}c"
            ;;
        *)
            SIZE_ARGS=""
            ;;
    esac
fi

if [[ "$TERMINAL_CMD" == "konsole" ]]; then
        EXEC_COMMAND="$TERMINAL_CMD $SIZE_ARGS -e $PYTHON_EXEC $MANAGER_SCRIPT"
else
        EXEC_COMMAND="$TERMINAL_CMD $SIZE_ARGS -- $PYTHON_EXEC $MANAGER_SCRIPT"
fi

SYSTEMD_PATH="$HOME/.config/systemd/user"
DESKTOP_APPS_PATH="$HOME/.local/share/applications"
AUTOSTART_PATH="$HOME/.config/autostart"
mkdir -p "$SYSTEMD_PATH" "$DESKTOP_APPS_PATH" "$AUTOSTART_PATH"

# --- Stop Services ---
log_info "Stopping all Hindsight services..."
"$SCRIPTS_PATH/stop_hindsight.sh"

# Ensure Recoll config exists (user may have deleted data directory)
if command -v recollindex &>/dev/null; then
    if [ -n "$RECOLL_CONF_DIR" ]; then
        mkdir -p "$RECOLL_CONF_DIR"
        if [ ! -f "$RECOLL_CONF_DIR/recoll.conf" ]; then
            OCR_TEXT_DIR=$(get_config_value "OCR_TEXT_DIR")
            cat > "$RECOLL_CONF_DIR/recoll.conf" <<EOF
topdirs = $OCR_TEXT_DIR
indexedmimetypes = text/plain
noaspell = 1
loglevel = 2
EOF
            log_info "Generated missing Recoll config at $RECOLL_CONF_DIR/recoll.conf"
        fi
    fi
fi

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