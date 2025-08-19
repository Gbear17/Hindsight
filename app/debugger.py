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

import os
import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Ensure the app's root directory is in the Python path to allow module imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import config # Import config to access file paths
from utils import setup_logger
from rebuild_index import incremental_rebuild_faiss
from memory_daemon import process_active_window
from cleanup import delete_old_data, clean_faiss_index

console = Console()
logger = setup_logger("HindsightDebugger")

# --- Self-Contained Helper Functions ---

def get_first_successful_run_from_log():
    """Finds the timestamp of the first successful index run by reading the log file."""
    try:
        with open(config.LOG_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if "Index update cycle completed" in line and "HindsightRebuildIndex" in line:
                    return line.split(',')[0].strip()
    except (IOError, FileNotFoundError, IndexError):
        return "Pending"
    return "Pending"

def check_first_run(dry_run=True):
    """Wrapper to display the first successful run from the log."""
    first_run_time = get_first_successful_run_from_log()
    console.print(f"First successful run detected: {first_run_time}")

# --- Debugger Configuration ---

DEBUG_FUNCTIONS = {
    '1': {
        'name': 'Run Incremental Index',
        'func': incremental_rebuild_faiss,
        'warning': 'This will read all unprocessed text files and add them to the FAISS index.'
    },
    '2': {
        'name': 'Capture Active Window',
        'func': process_active_window,
        'warning': 'This will take a screenshot of your currently active window and run OCR on it.'
    },
    '3': {
        'name': 'Delete Old Data',
        'func': delete_old_data,
        'warning': 'This will permanently delete all screenshot and text files older than the configured retention period.'
    },
    '4': {
        'name': 'Clean FAISS Index',
        'func': clean_faiss_index,
        'warning': 'This will permanently delete the FAISS index files, forcing a full rebuild on the next cycle.'
    },
    '5': {
        'name': 'Check First Successful Run',
        'func': check_first_run,
        'warning': 'This will read the log file to find the timestamp of the first completed index run.'
    }
}

def print_header(mode):
    color = "yellow" if mode == "safe" else "red"
    console.clear()
    console.print(Panel(
        Text(f"Hindsight Debugger - {mode.upper()} MODE", justify="center"),
        style=f"bold white on {color}",
        border_style=color
    ))

def choose_mode():
    """Prompts user to select safe or advanced mode."""
    print_header("Mode Selection")
    console.print("\n[bold yellow]SAFE MODE[/bold yellow] will perform a 'dry run' of functions, showing what would happen without making changes.")
    # CORRECTED: The typo was here.
    console.print("[bold red]ADVANCED MODE[/bold red] will execute functions live, making permanent changes to your data.\n")
    
    while True:
        # CORRECTED: The second typo was here.
        choice = console.input("Choose mode: ([bold yellow]S[/bold yellow]afe / [bold red]A[/bold red]dvanced): ").lower()
        if choice in ['s', 'a']:
            return "safe" if choice == 's' else "advanced"
        console.print("[red]Invalid choice. Please enter 's' or 'a'.[/red]")

def run_debugger(mode):
    """Main loop for the debugger."""
    is_dry_run = (mode == "safe")
    
    while True:
        print_header(mode)
        console.print("\n[bold]Available Functions:[/bold]")
        for key, info in DEBUG_FUNCTIONS.items():
            console.print(f"  ({key}) {info['name']}")
        console.print("  (q) Quit")

        choice = console.input("\nSelect a function to run: ").lower()

        if choice == 'q':
            break

        if choice in DEBUG_FUNCTIONS:
            selected_func_info = DEBUG_FUNCTIONS[choice]
            console.print(f"\n[bold yellow]WARNING:[/bold yellow] {selected_func_info['warning']}")
            
            confirm = console.input(f"Are you sure you want to run '{selected_func_info['name']}' in {mode.upper()} mode? (y/n): ").lower()
            if confirm == 'y':
                console.print(f"\n--- Running {selected_func_info['name']} ---")
                try:
                    # All debuggable functions must accept a 'dry_run' keyword argument.
                    selected_func_info['func'](dry_run=is_dry_run)
                    console.print(f"--- Finished {selected_func_info['name']} ---\n")
                except Exception as e:
                    logger.error(f"An error occurred while running {selected_func_info['name']}: {e}", exc_info=True)
                    console.print(f"[bold red]An error occurred. Check the log for details.[/bold red]\n")
                
                console.input("Press Enter to continue...")
        else:
            console.print("[red]Invalid selection.[/red]")
            time.sleep(1)

def main():
    """Entry point for the debugger script."""
    try:
        mode = choose_mode()
        run_debugger(mode)
    except (KeyboardInterrupt, EOFError):
        console.print("\n\n[bold magenta]Exiting debugger.[/bold magenta]")
    finally:
        print("\nDebugger session finished. You can close this terminal.")
        time.sleep(3)

if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    main()
