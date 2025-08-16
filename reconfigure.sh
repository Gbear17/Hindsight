#!/bin/bash
#
# Hindsight Reconfiguration Script
#
# This script automates the setup of systemd services and desktop application
# shortcuts for the Hindsight project. It reads from .template files,
# replaces path placeholders with the current user's information, and
# copies the final configuration files to the appropriate system directories.
#
# This version includes interactive error handling and all necessary setup steps.
#

# --- Helper Functions for Error Handling ---

# This function will be called when any command fails.
# It prints the failed command and its exit code, then asks the user for action.
handle_error() {
    local exit_code=$1
    local failed_command=$2
    echo ""
    echo "❌ ERROR: Command failed with exit code $exit_code."
    echo "   Failed command: $failed_command"
    echo ""
    
    # Loop until the user provides a valid response (y or n).
    while true; do
        # SC2162 FIX: Added -r to read to prevent mangling backslashes.
        read -r -p "Do you want to retry this step? (y/n): " choice
        case "$choice" in
            [Yy]* ) return 0;; # Return 0 to signal a retry.
            [Nn]* ) echo "Aborting script."; exit 1;; # Exit the script.
            * ) echo "Please answer 'y' or 'n'.";;
        esac
    done
}

# A wrapper function to execute commands and catch errors.
# It calls handle_error if a command fails.
run_command() {
    # Execute all arguments passed to this function as a single command.
    # The loop allows for retrying the command if the user chooses 'y'.
    while ! "$@"; do
        local exit_code=$?
        # Pass the exit code and the failed command to the error handler.
        handle_error $exit_code "$*"
    done
}


# --- Variable Initialization ---
# Get the absolute path to the user's home directory.
USER_HOME=$(eval echo ~"$USER")

# Define the base path for the Hindsight project.
PROJECT_PATH="$USER_HOME/hindsight"
RESOURCES_PATH="$PROJECT_PATH/resources" # Define the path to the resources directory.

# Define system directories for user-specific files.
SYSTEMD_PATH="$USER_HOME/.config/systemd/user"
DESKTOP_APPS_PATH="$USER_HOME/.local/share/applications"
AUTOSTART_PATH="$USER_HOME/.config/autostart"

# An array of all systemd services to be managed.
SERVICES=(
    "hindsight-api.service"
    "hindsight-daemon.service"
    "hindsight-rebuild.timer"
)

# Create the system directories if they don't already exist.
mkdir -p "$SYSTEMD_PATH" "$DESKTOP_APPS_PATH" "$AUTOSTART_PATH"

# --- Stop Services Before Reconfiguration ---
echo "----------------------------------------"
echo "Stopping all Hindsight services for safety..."
for service in "${SERVICES[@]}"; do
    # Use 'stop' command. It doesn't fail if the service is already stopped.
    run_command systemctl --user stop "$service"
done
echo "All services stopped."

# --- Main Processing Loop ---
# An array of all template files that need to be processed.
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
    # Define the full path to the source template file.
    source_template_path="$RESOURCES_PATH/$template_file"

    echo "----------------------------------------"
    echo "Processing: $source_template_path -> $final_filename"

    # Create a temporary copy of the template to work with in the current directory.
    run_command cp "$source_template_path" "$final_filename"
    
    # --- Placeholder Replacement Logic ---
    case "$final_filename" in
        "hindsight-manager.desktop")
            # UPDATED: Set the terminal geometry to 75x17.
            run_command sed -i "s#Exec=.*#Exec=gnome-terminal --geometry=75x17 -- \"$PROJECT_PATH/app/scripts/launch_manager.sh\"#" "$final_filename"
            run_command sed -i "s#Icon=.*#Icon=$PROJECT_PATH/resources/hindsight.png#" "$final_filename"
            echo "  -> Replaced icon and exec paths."
            ;;
        "hindsight-api.service")
            run_command sed -i "s#ExecStart=.*#ExecStart=$PROJECT_PATH/app/venv/bin/gunicorn --chdir $PROJECT_PATH/app --enable-stdio-inheritance --bind localhost:5000 hindsight_api:app#" "$final_filename"
            run_command sed -i "s#Environment=.*#Environment=\"GOOGLE_APPLICATION_CREDENTIALS=$PROJECT_PATH/app/service-account.json\"#" "$final_filename"
            echo "  -> Replaced ExecStart and Environment paths."
            ;;
        "hindsight-daemon.service")
            run_command sed -i "s#ExecStart=.*#ExecStart=$PROJECT_PATH/app/scripts/start_daemon.sh#" "$final_filename"
            run_command sed -i "s#WorkingDirectory=.*#WorkingDirectory=$PROJECT_PATH/app#" "$final_filename"
            echo "  -> Replaced ExecStart and WorkingDirectory paths."
            ;;
        "hindsight-rebuild.service")
            run_command sed -i "s#ExecStart=.*#ExecStart=$PROJECT_PATH/app/venv/bin/python $PROJECT_PATH/app/rebuild_index.py#" "$final_filename"
            echo "  -> Replaced ExecStart path."
            ;;
        *)
            echo "  -> No placeholders to replace."
            ;;
    esac

    # --- File Installation Logic ---
    destination_path=""
    if [[ "$final_filename" == "recoll-hindsight.desktop" ]]; then
        destination_path="$AUTOSTART_PATH/$final_filename"
    elif [[ "$final_filename" == *.desktop ]]; then
        destination_path="$DESKTOP_APPS_PATH/$final_filename"
    elif [[ "$final_filename" == *.service ]] || [[ "$final_filename" == *.timer ]]; then
        destination_path="$SYSTEMD_PATH/$final_filename"
    fi

    if [ -n "$destination_path" ]; then
        echo "  -> Removing old file (if any): $destination_path"
        run_command rm -f "$destination_path"
        echo "  -> Pausing for 1 second..."
        run_command sleep 1
        echo "  -> Copying to: $destination_path"
        run_command cp "$final_filename" "$destination_path"
    else
        echo "  -> [WARNING] Unknown file type for $final_filename. Not installed."
    fi
    
    # --- Cleanup Step ---
    # Remove the temporary file from the project's root directory.
    echo "  -> Cleaning up temporary file: $final_filename"
    run_command rm -f "$final_filename"
done

# --- Finalization ---
echo "----------------------------------------"
echo "Reloading systemd user daemon..."
run_command systemctl --user daemon-reload

echo "Updating desktop application database..."
run_command update-desktop-database "$DESKTOP_APPS_PATH"

echo ""
echo "✅ Reconfiguration complete!"

# --- Restart Services After Reconfiguration ---
while true; do
    read -r -p "Do you want to start the Hindsight services now? (y/n): " choice
    case "$choice" in
        [Yy]* )
            echo "Starting all Hindsight services..."
            for service in "${SERVICES[@]}"; do
                run_command systemctl --user start "$service"
            done
            echo "All services started."
            break
            ;;
        [Nn]* )
            echo "Services not started. You can start them manually later."
            break
            ;;
        * ) echo "Please answer 'y' or 'n'.";;
    esac
done

echo "Script finished."
