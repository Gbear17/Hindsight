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
"""Manager UI and terminal-based dashboard for Hindsight.

This module implements the curses-like Rich-based terminal dashboard used to
control Hindsight services, view status, and run management actions.
"""


import subprocess
import time
import os
import sys
import configparser
import shutil
import select
import termios
import tty
import threading
import queue
import requests
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# --- Configuration Loading ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
if not os.path.exists(config_path):
    print(f"Error: Configuration file not found at {config_path}")
    sys.exit(1)
config.read(config_path)

# --- Pre-Flight Check for Terminal Configuration ---
def pre_flight_check():
    """
    Verifies the configured terminal is valid before launching the main UI.
    If it's invalid, it runs the detection script to let the user fix it.
    """
    try:
        terminal_cmd = config.get('User Settings', 'TERMINAL_CMD').strip('\'"')
        scripts_path = config.get('System Paths', 'SCRIPTS_PATH')
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        missing_item = f"section '[{e.section}]'" if isinstance(e, configparser.NoSectionError) else f"option '{e.option}'"
        print(f"Error: Your hindsight.conf file is incomplete. Missing {missing_item}.")
        sys.exit(1)
    if not shutil.which(terminal_cmd):
        print(f"\n[ERROR] The configured terminal '{terminal_cmd}' was not found.")
        detector_script = os.path.join(scripts_path, "detect_terminal.sh")
        if os.path.exists(detector_script):
            subprocess.run([detector_script])
            print("\nConfiguration updated. Please start the Hindsight Manager again.")
        else:
            print(f"[FATAL] Cannot find the detection script at {detector_script}")
        sys.exit(0)

pre_flight_check()

# --- Fetching settings ---
TERMINAL_CMD = config.get('User Settings', 'TERMINAL_CMD').strip('\'"')
SCRIPTS_PATH = config.get('System Paths', 'SCRIPTS_PATH')
VENV_PATH = config.get('System Paths', 'VENV_PATH')
APP_PATH = config.get('System Paths', 'APP_PATH')
LOG_FILE = config.get('System Paths', 'LOG_FILE')
API_URL = config.get('API', 'URL', fallback='http://127.0.0.1:5000').strip('\'"')
THEME_MODE = config.get('User Settings', 'THEME_MODE', fallback='auto').lower()

# --- Theme / Contrast Handling (improved) ---
def _detect_from_colorfgbg():
    """Parse COLORFGBG env (fg;bg or fg:bg). bg 7/15 -> light typically."""
    val = os.environ.get('COLORFGBG')
    if not val:
        return None
    parts = [p for chunk in val.split(':') for p in chunk.split(';') if p]
    if not parts:
        return None
    try:
        bg = int(parts[-1])
    except ValueError:
        return None
    return 'light' if bg in (7, 15) else 'dark'

def _detect_from_profile():
    profile = os.environ.get('KONSOLE_PROFILE_NAME', '').lower()
    if any(x in profile for x in ('light', 'solarized-light', 'day', 'paper', 'bright')):
        return 'light'
    if any(x in profile for x in ('dark', 'night', 'solarized-dark', 'dracula', 'one-dark')):
        return 'dark'
    return None

def detect_theme_auto():
    for detector in (_detect_from_colorfgbg, _detect_from_profile):
        result = detector()
        if result:
            return result
    return 'dark'

def get_active_theme(app_state):
    override = app_state.get('theme_override')
    # Config value takes precedence when user hasn't toggled in-session
    if override is None or override == 'auto':
        if THEME_MODE in ('light', 'dark'):
            return THEME_MODE
        return detect_theme_auto()
    if override in ('light', 'dark'):
        return override
    return detect_theme_auto()

def color_token(name, theme):
    light = (theme == 'light')
    palette = {
        'accent': 'blue' if light else 'cyan',
        'ok': 'green',
        'warn': 'orange3' if light else 'yellow',
        'bad': 'red',
        'pending_low': 'green',
        'pending_mid': 'dark_orange' if light else 'yellow',
        'pending_high': 'red',
        'flash': 'bold magenta' if light else 'bold yellow'
    }
    return palette.get(name, 'white')

# --- Helper Functions ---
def get_hindsight_status_from_api():
    """Makes a single API call to get the status of all Hindsight components."""
    try:
        response = requests.get(f"{API_URL}/status", timeout=0.9)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return {
            "api_status": "[red]● Down[/red]", "daemon_status": "[red]● Unknown[/red]", "timer_status": "[red]● Unknown[/red]",
            "cpu_usage": "N/A", "mem_usage": "N/A", "io_usage": "N/A",
            "db_size": "N/A", "total_records": "N/A", "last_update": "N/A", "next_update": "N/A"
        }

def run_command(command):
    """Runs a shell command in the background without blocking."""
    subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def create_terminal_command(command_to_run, graceful=True):
    """Builds a full command string to launch a process in the user's configured terminal.

    If graceful is True, wraps the command to neutralize Ctrl-C (SIGINT) so some terminals
    don't display a scary 'bash crashed' notification when tail is interrupted.
    """
    if graceful:
        # trap INT/TERM so tail exit looks clean; ensure non-zero exits don't propagate as crash
        wrapped = (
            "bash -c 'trap ':' SIGINT SIGTERM; "
            f"{command_to_run} || true; rc=$?; echo -e \"\\n\\n(Exit code $rc) Press Enter to close.\"; read'"
        )
    else:
        wrapped = f"bash -c \"{command_to_run}; echo -e '\n\nPress Enter to close.'; read\""
    if 'konsole' in TERMINAL_CMD:
        return f"{TERMINAL_CMD} -e {wrapped}"
    else:
        return f"{TERMINAL_CMD} -- {wrapped}"

def read_keyboard_input(input_queue):
    """
    A robust, blocking function to read a single character from stdin.
    This will run in a separate thread.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while True:
            # This is a blocking read, it will wait for a key press
            char = sys.stdin.read(1)
            if char:
                input_queue.put(char)
            else: # EOF
                time.sleep(0.1) # Prevent high CPU usage on unexpected EOF
    finally:
        # Restore terminal settings when the thread exits
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def flash(app_state, msg, duration=3):
    """Set a transient flash message in the application state.

    Args:
        app_state: The shared application state dictionary.
        msg: Message string to display.
        duration: Number of seconds the message should remain visible.
    """
    app_state["flash"] = msg
    app_state["flash_until"] = time.time() + duration

# --- UI Rendering ---
def make_layout():
    """Defines the full Rich layout structure ONE time."""
    layout = Layout(name="root")
    layout.split(Layout(name="header", size=3), Layout(name="main", ratio=1), Layout(name="footer", size=5))
    layout["main"].split(Layout(name="top_row", size=5), Layout(name="index_status", ratio=1))
    layout["top_row"].split_row(Layout(name="system_status"), Layout(name="resources"))
    return layout

def update_dashboard_layout(layout, status_data, app_state):
    """Renders the dashboard using data received from the API."""
    layout["header"].update(Text("Hindsight Manager", style="bold blue", justify="center"))

    if app_state["mode"] == "normal":
        # --- Service Status Panel ---
        status_grid = Table.grid(expand=True, padding=(0, 1))
        status_grid.add_column(justify="right"); status_grid.add_column(justify="left")
        status_grid.add_row("[bold]API Service:[/bold]", status_data.get('api_status', 'Error'))
        status_grid.add_row("[bold]Memory Daemon:[/bold]", status_data.get('daemon_status', 'Error'))
        status_grid.add_row("[bold]Rebuild Timer:[/bold]", status_data.get('timer_status', 'Error'))
        layout["system_status"].update(Panel(status_grid, title="[bold]Service Status[/bold]"))

        # --- Live Resources Panel ---
        resource_table = Table.grid(expand=True, padding=(0, 1))
        resource_table.add_column(justify="right"); resource_table.add_column(justify="left")
        resource_table.add_row("[bold]CPU Usage:[/bold]", status_data.get('cpu_usage', 'Error'))
        resource_table.add_row("[bold]Memory Usage:[/bold]", status_data.get('mem_usage', 'Error'))
        resource_table.add_row("[bold]File I/O:[/bold]", status_data.get('io_usage', 'Error'))
        layout["resources"].update(Panel(resource_table, title="[bold]Live Resources[/bold]"))

        # --- Index Status Panel (Two-column compact layout) ---
        active_theme = get_active_theme(app_state)

        def style_pending(raw):
            val = str(raw)
            try:
                num = int(val)
            except ValueError:
                return val
            if num == 0:
                c = color_token('pending_low', active_theme)
                return f"[{c}]{num}[/{c}]"
            if num < 50:
                c = color_token('pending_mid', active_theme)
                return f"[{c}]{num}[/{c}]"
            c = color_token('pending_high', active_theme)
            return f"[{c}]{num}[/{c}]"

        recoll_proc = status_data.get('recoll_processed','?')
        recoll_pending = style_pending(status_data.get('recoll_unprocessed','?'))
        recoll_last = status_data.get('recoll_last_run','N/A')
        faiss_proc = status_data.get('faiss_processed','?')
        faiss_pending = style_pending(status_data.get('faiss_unprocessed','?'))
        faiss_last = status_data.get('faiss_last_run','N/A')

        grid = Table.grid(expand=True, padding=(0,1))
        # Left pair (Recoll) and Right pair (FAISS)
        grid.add_column(justify="right", no_wrap=True)
        grid.add_column(justify="left")
        grid.add_column(justify="right", no_wrap=True)
        grid.add_column(justify="left")

        grid.add_row("[bold]Database Size:[/bold]", status_data.get('db_size','N/A'),
                     "[bold]FAISS Proc:[/bold]", f"{faiss_proc} vectors")
        grid.add_row("[bold]Next Run:[/bold]", status_data.get('next_update','N/A'),
                     "[bold]FAISS Pending:[/bold]", faiss_pending)
        grid.add_row("[bold]Recoll Proc:[/bold]", f"{recoll_proc} files",
                     "[bold]FAISS Last:[/bold]", faiss_last)
        grid.add_row("[bold]Recoll Pending:[/bold]", recoll_pending,
                     "[bold]Recoll Last:[/bold]", recoll_last)

        layout["index_status"].update(Panel(grid, title="[bold]Index Status[/bold]"))

    # --- Footer Panel ---
    menu = ("(1) Start/Restart All | (2) Stop All | (3) View Logs | (4) Edit Config\n"
        "(5) Reconfigure | (6) Debugger | (7) Force Index Now | (t) Theme | (q) Quit")
    if app_state.get("flash") and time.time() < app_state.get("flash_until", 0):
        flash_color = color_token('flash', get_active_theme(app_state))
        menu += f"\n[{flash_color}]{app_state['flash']}[/{flash_color}]"
    # Use from_markup so color/style tags in flash message render properly
    layout["footer"].update(Panel(Text.from_markup(menu, justify="center"), title="[bold]Actions[/bold]", border_style="blue"))

# --- Main Application ---
if __name__ == "__main__":
    console = Console()
    layout = make_layout()
    app_state = {"mode": "normal", "theme_override": None}

    input_queue = queue.Queue()
    input_thread = threading.Thread(target=read_keyboard_input, args=(input_queue,), daemon=True)
    input_thread.start()
    
    # The termios/tty logic is now handled by the input thread.
    # The main thread just focuses on the UI.
    try:
        with Live(layout, screen=True, redirect_stderr=False, refresh_per_second=2) as live:
            while True:
                status_data = get_hindsight_status_from_api()
                update_dashboard_layout(layout, status_data, app_state)
                
                if not input_queue.empty():
                    key = input_queue.get().lower()
                    if key == 'q':
                        break
                    if key in "1234567t":
                        if key == '1':
                            start_script = os.path.join(SCRIPTS_PATH, "start_hindsight.sh")
                            if os.path.isfile(start_script) and os.access(start_script, os.X_OK):
                                run_command(f"'{start_script}'")
                                flash(app_state, "Starting services...")
                            else:
                                flash(app_state, "start_hindsight.sh missing/not executable.")
                        elif key == '2':
                            stop_script = os.path.join(SCRIPTS_PATH, "stop_hindsight.sh")
                            if os.path.exists(stop_script) and os.access(stop_script, os.X_OK):
                                run_command(f"'{stop_script}'")
                                flash(app_state, "Stopping services...")
                            else:
                                flash(app_state, "stop_hindsight.sh missing or not executable.")
                        elif key == '3':
                            # Use graceful wrapper to avoid 'bash crashed' dialog on Ctrl-C
                            run_command(create_terminal_command(f"tail -n 200 -f {LOG_FILE}", graceful=True))
                        elif key == '4':
                            editor = os.environ.get('EDITOR', 'nano')
                            run_command(create_terminal_command(f"'{editor}' '{config_path}'"))
                        elif key == '5':
                            run_command(create_terminal_command(f"'{os.path.join(SCRIPTS_PATH, 'configure.sh')}'"))
                        elif key == '6':
                            python_exec = os.path.join(VENV_PATH, "bin", "python")
                            debugger_script = os.path.join(APP_PATH, "debugger.py")
                            run_command(create_terminal_command(f"'{python_exec}' '{debugger_script}'"))
                        elif key == '7':
                            run_command("systemctl --user start hindsight-rebuild.service")
                            flash(app_state, "Index cycle triggered.")
                        elif key == 't':
                            current = app_state.get('theme_override') or 'auto'
                            nxt = {'auto': 'light', 'light': 'dark', 'dark': 'auto'}[current]
                            app_state['theme_override'] = nxt
                            flash(app_state, f"Theme: {nxt}")
                time.sleep(0.5)
    finally:
        # The input thread's finally block will handle restoring terminal settings.
        console.print("[bold blue]Exiting Hindsight Manager.[/bold blue]")
