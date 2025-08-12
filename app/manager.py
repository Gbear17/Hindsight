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

import subprocess
import time
import os
import sys
import psutil
import threading
import queue
import json
import glob
from pynput import keyboard

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import config
from utils import setup_logger

console = Console()
logger = setup_logger("HindsightManager")

# --- Application State ---
app_state = {"mode": "normal"}

# --- Helper Functions ---


def run_command(command, capture=False):
    """Runs a command, returns True/False or captured output."""
    try:
        if capture:
            return subprocess.check_output(command, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        else:
            subprocess.Popen(
                command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def manage_service(action, service_name):
    """Starts a systemd command in the background without blocking."""
    command = f"systemctl --user {action} {service_name}"
    subprocess.Popen(command, shell=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)


def get_service_status(service_name):
    """Checks if a systemd service is active, returns a rich string."""
    is_active = subprocess.run(
        f"systemctl --user is-active --quiet {service_name}",
        shell=True,
        capture_output=True
    ).returncode == 0
    return "[green]● Active[/green]" if is_active else "[red]● Inactive[/red]"


def get_resource_usage():
    """Calculates resource usage for all Hindsight-related python scripts."""
    hindsight_scripts = ['memory_daemon.py',
                         'rebuild_index.py', 'hindsight_api.py', 'manager.py']
    hindsight_processes = []
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline_str = ' '.join(proc.info.get('cmdline', []))
            if 'python' in proc.info['name'] and any(script in cmdline_str for script in hindsight_scripts):
                hindsight_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue
    cpu, mem = 0.0, 0.0
    for proc in hindsight_processes:
        try:
            cpu += proc.cpu_percent(interval=0.1)
            mem += proc.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return cpu, mem, len(hindsight_processes)


def get_latest_logs(num_lines=10):
    """Retrieves the last N lines from the main log file."""
    try:
        with open(config.LOG_FILE, 'r') as f:
            lines = f.readlines()
        return "".join(lines[-num_lines:])
    except (IOError, FileNotFoundError):
        return "[red]Log file not found.[/red]"


def get_last_successful_run_from_log():
    """Finds the timestamp of the last successful index run from the log."""
    try:
        with open(config.LOG_FILE, 'r') as f:
            lines = f.readlines()
        for line in reversed(lines):
            if "Successfully added" in line and "HindsightRebuildIndex" in line:
                return line.split(',')[0]
    except (IOError, FileNotFoundError):
        return "Log file not found."
    return "Pending first run..."


def get_index_info():
    """Gathers and returns a dictionary of information about the search indexes."""
    info = {"state": "[red]Unknown[/red]", "last_run": "N/A",
            "next_run": "N/A", "items": 0, "unprocessed": 0}
    if os.path.exists(config.ID_MAP_PATH):
        try:
            with open(config.ID_MAP_PATH, 'r') as f:
                info["items"] = len(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    try:
        total_files = len(
            glob.glob(os.path.join(config.OCR_TEXT_DIR, "*.txt")))
        info["unprocessed"] = max(0, total_files - info["items"])
    except IOError:
        pass

    if subprocess.run(f"systemctl --user is-active --quiet hindsight-rebuild.service", shell=True).returncode == 0:
        info["state"] = "[bold yellow]Actively Indexing[/bold yellow]"
    else:
        info["state"] = "[cyan]Idle / Waiting[/cyan]"

    info["last_run"] = get_last_successful_run_from_log()
    timer_status = run_command(
        "systemctl --user status hindsight-rebuild.timer", capture=True)
    if timer_status and "inactive" not in timer_status.lower():
        for line in timer_status.split('\n'):
            if "Trigger:" in line:
                full_trigger_str = line.split(
                    "Trigger:")[1].strip().split(';')[0]
                parts = full_trigger_str.split()
                if len(parts) >= 3:
                    info["next_run"] = " ".join(parts[1:3])
                else:
                    info["next_run"] = full_trigger_str
    else:
        info["next_run"] = "Timer Inactive"
    return info

# --- UI Rendering ---


def make_layout() -> Layout:
    """Defines the Rich layout structure."""
    layout = Layout(name="root")
    layout.split(Layout(name="header", size=3), Layout(
        name="body", ratio=1), Layout(name="footer", size=5))
    top_row = Layout(name="top_row", size=5)
    top_row.split_row(Layout(name="status"), Layout(name="resources"))
    layout["body"].split(top_row, Layout(
        name="index_status", size=6), Layout(name="log_viewer"))
    return layout


def update_dashboard_layout(layout: Layout) -> None:
    """Renders all the content for the dashboard UI."""
    header_grid = Table.grid(expand=True)
    header_grid.add_column(justify="center")
    header_grid.add_column(justify="right")
    header_grid.add_row("[b]Hindsight v5 Service Manager[/b]",
                        f"[cyan]{time.ctime()}[/cyan]")
    layout["header"].update(
        Panel(header_grid, style="white on dark_violet", padding=(0, 1)))

    status_table = Table(box=None, expand=True, show_header=False, padding=0)
    status_table.add_column(ratio=1, justify="right", no_wrap=True)
    status_table.add_column(ratio=1, justify="left")
    status_table.add_row("[bold magenta]API Service: ",
                         get_service_status("hindsight-api.service"))
    status_table.add_row("[bold magenta]Indexing Timer: ",
                         get_service_status("hindsight-rebuild.timer"))
    status_table.add_row("[bold magenta]Memory Daemon: ",
                         get_service_status("hindsight-daemon.service"))
    layout["status"].update(Panel(
        status_table, title="[bold]Service Status[/bold]", border_style="magenta", padding=(0, 2)))

    resource_table = Table(box=None, expand=True, show_header=False, padding=0)
    resource_table.add_column(ratio=1, justify="right", no_wrap=True)
    resource_table.add_column(ratio=1, justify="left")
    cpu, mem, p_count = get_resource_usage()
    resource_table.add_row("[bold cyan]CPU Usage: ", f"{cpu:.2f} %")
    resource_table.add_row("[bold cyan]Memory: ", f"{mem:.2f} MB")
    resource_table.add_row("[bold cyan]Processes: ", str(p_count))
    layout["resources"].update(Panel(
        resource_table, title="[bold]Live Resources[/bold]", border_style="cyan", padding=(0, 2)))

    index_info = get_index_info()
    left_index_table = Table(box=None, expand=True,
                             show_header=False, padding=0)
    left_index_table.add_column(ratio=1, justify="right", no_wrap=True)
    left_index_table.add_column(ratio=1, justify="left")
    left_index_table.add_row(
        "[bold yellow]Indexed Items: ", str(index_info["items"]))
    left_index_table.add_row(
        "[bold yellow]Unprocessed Files: ", str(index_info["unprocessed"]))
    right_index_table = Table(box=None, expand=True,
                              show_header=False, padding=0)
    right_index_table.add_column(ratio=1, justify="right", no_wrap=True)
    right_index_table.add_column(ratio=1, justify="left")
    right_index_table.add_row(
        "[bold yellow]Last Run: ", index_info["last_run"])
    right_index_table.add_row(
        "[bold yellow]Next Run: ", index_info["next_run"])
    index_grid = Table.grid(expand=True)
    index_grid.add_column()
    index_grid.add_column()
    index_grid.add_row(left_index_table, right_index_table)
    layout["index_status"].update(Panel(
        index_grid, title=f"[bold]Index Status: {index_info['state']}[/bold]", border_style="yellow", padding=(0, 1)))

    log_content = Text(get_latest_logs(), no_wrap=False)
    layout["log_viewer"].update(
        Panel(log_content, title="[bold]Real-time Log[/bold]", border_style="green"))

    if app_state["mode"] == "normal":
        # --- MODIFIED: Added (6) Reconfigure option ---
        menu = ("(1) Start All | (2) Stop All | (3) Restart All | (4) View Logs\n"
                "(5) Edit Config | (6) Reconfigure | (Ctrl+C to Quit)")
        footer_panel = Panel(Text(menu, justify="center"),
                             title="[bold]Interactive Menu[/bold]", style="white on dark_violet")
    else:
        action_text = app_state["mode"].split('_')[1]
        menu = f"Are you sure you want to {action_text} all services? ([bold]y[/bold]/[bold]n[/bold])"
        footer_panel = Panel(Text.from_markup(menu, justify="center"),
                             title="[bold red]Confirmation Required[/bold red]", style="bold white on red", border_style="red")
    layout["footer"].update(footer_panel)


# --- Main Application Logic ---
if __name__ == "__main__":
    input_queue = queue.Queue()

    def on_press(key):
        try:
            input_queue.put(key.char)
        except AttributeError:
            pass  # Ignore special keys

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    layout = make_layout()
    try:
        with Live(layout, screen=True, redirect_stderr=False, refresh_per_second=4) as live:
            while True:
                if not input_queue.empty():
                    action = input_queue.get().lower()

                    if app_state["mode"] == "normal":
                        if action == '1':
                            manage_service("start", "hindsight-api.service")
                            manage_service("start", "hindsight-rebuild.timer")
                            manage_service("start", "hindsight-daemon.service")
                        elif action == '2':
                            app_state["mode"] = "confirm_stop"
                        elif action == '3':
                            app_state["mode"] = "confirm_restart"
                        elif action == '4':
                            run_command(
                                f"gnome-terminal -- bash -c 'tail -n 200 -f {config.LOG_FILE}; exec bash'")
                        elif action == '5':
                            editor = os.environ.get('EDITOR', 'nano')
                            config_file = os.path.join(
                                config.BASE_PATH, "config.py")
                            run_command(
                                f"gnome-terminal -- bash -c '{editor} {config_file}; exec bash'")
                        # --- ADDED: Handler for Reconfigure option ---
                        elif action == '6':
                            # config.BASE_PATH is the 'app' dir, so we go up one level for the project root
                            reconfigure_script = os.path.join(
                                config.BASE_PATH.parent, "reconfigure.sh")
                            command = f"gnome-terminal -- bash -c '\"{reconfigure_script}\"; echo \"\nReconfiguration finished. Press Enter to close.\"; read'"
                            run_command(command)

                    elif app_state["mode"] == "confirm_stop":
                        if action == 'y':
                            manage_service("stop", "hindsight-api.service")
                            manage_service("stop", "hindsight-rebuild.timer")
                            manage_service("stop", "hindsight-daemon.service")
                        app_state["mode"] = "normal"
                    elif app_state["mode"] == "confirm_restart":
                        if action == 'y':
                            manage_service("restart", "hindsight-api.service")
                            manage_service(
                                "restart", "hindsight-daemon.service")
                            manage_service("stop", "hindsight-rebuild.timer")
                            manage_service("start", "hindsight-rebuild.timer")
                        app_state["mode"] = "normal"

                    if action == 'n' and app_state["mode"] != "normal":
                        app_state["mode"] = "normal"

                update_dashboard_layout(layout)
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print_exception()
    finally:
        listener.stop()
        console.print(
            "[bold magenta]Exiting Hindsight Manager.[/bold magenta]")
