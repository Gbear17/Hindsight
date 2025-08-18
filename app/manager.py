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

import subprocess
import time
import os
import sys
import psutil
import threading
import queue
import json
import glob
from datetime import datetime, timezone, timedelta
import termios
import tty
import configparser

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# --- New Config Parser Logic ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

# --- Fetching settings ---
LOG_FILE = config.get('System Paths', 'LOG_FILE')
DB_DIR = config.get('System Paths', 'DB_DIR')
ID_MAP_PATH = os.path.join(DB_DIR, 'hindsight_id_map.json')
OCR_TEXT_DIR = config.get('System Paths', 'OCR_TEXT_DIR')
APP_PATH = config.get('System Paths', 'APP_PATH')
SCRIPTS_PATH = config.get('System Paths', 'SCRIPTS_PATH')
VENV_PATH = config.get('System Paths', 'VENV_PATH')

from utils import setup_logger

console = Console()
logger = setup_logger("HindsightManager")

# --- Application State ---
app_state = {"mode": "normal"}
SERVICES = ["hindsight-api.service", "hindsight-daemon.service", "hindsight-rebuild.timer"]

# --- Helper Functions (No changes needed here) ---
def run_command(command, capture=False):
    """Runs a command, returns True/False or captured output."""
    try:
        if capture:
            return subprocess.check_output(command, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        else:
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Command '{command}' failed with exit code {e.returncode}.")
        return False
    except (FileNotFoundError, Exception) as e:
        logger.error(f"Failed to execute command '{command}': {e}")
        return False

def manage_service(action, service_name):
    """Starts a systemd command in the background without blocking."""
    command = f"systemctl --user {action} {service_name}"
    subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def manage_all_services(action):
    """Runs an action on all Hindsight services."""
    # Special handling for restart to ensure the timer is properly re-enabled.
    if action == "restart":
        manage_service("restart", "hindsight-api.service")
        manage_service("restart", "hindsight-daemon.service")
        # To properly restart a timer, it must be stopped and then started again.
        manage_service("stop", "hindsight-rebuild.timer")
        manage_service("start", "hindsight-rebuild.timer")
    else:
        for service in SERVICES:
            manage_service(action, service)

def get_service_status(service_name):
    """Checks if a systemd service is active, returns a rich string."""
    is_active = subprocess.run(f"systemctl --user is-active --quiet {service_name}", shell=True).returncode == 0
    return "[green]● Active[/green]" if is_active else "[red]● Inactive[/red]"

def get_resource_usage():
    """Calculates resource usage for all Hindsight-related python scripts."""
    hindsight_scripts = ['memory_daemon.py', 'rebuild_index.py', 'hindsight_api.py', 'manager.py', 'reconfigure.sh']
    hindsight_processes = []
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline_str = ' '.join(proc.info.get('cmdline', []))
            if any(script in cmdline_str for script in hindsight_scripts):
                hindsight_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue
    cpu, mem = 0.0, 0.0
    for proc in hindsight_processes:
        try:
            cpu += proc.cpu_percent(interval=None)
            mem += proc.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return cpu, mem, len(hindsight_processes)

# --- Functions using new config variables ---
def get_last_successful_run_from_log():
    """Efficiently finds the timestamp of the last successful index run using pure Python."""
    try:
        with open(LOG_FILE, 'rb') as f:
            f.seek(0, os.SEEK_END)
            buffer = bytearray()
            while f.tell() > 0:
                chunk_size = min(f.tell(), 4096)
                f.seek(-chunk_size, os.SEEK_CUR)
                buffer = f.read(chunk_size) + buffer
                f.seek(-chunk_size, os.SEEK_CUR)
                lines = buffer.decode('utf-8', errors='ignore').split('\n')
                for i in range(len(lines) - 1, -1, -1):
                    line = lines[i]
                    if "Index update cycle completed" in line and "HindsightRebuildIndex" in line:
                        return line.split(',')[0].strip()
                buffer = bytearray(lines[0], 'utf-8', errors='ignore')
    except (IOError, FileNotFoundError, IndexError):
        return "Pending"
    return "Pending"
            
def calculate_next_run(now, schedule="*:0/15"):
    """Calculates the next run time based on a simple cron-like schedule."""
    try:
        parts = schedule.split(':')
        minute_part = parts[1]
        base, step = map(int, minute_part.split('/'))
        next_minute = -1
        for i in range(base, 60, step):
            if i > now.minute:
                next_minute = i
                break
        if next_minute != -1:
            return now.replace(minute=next_minute, second=0, microsecond=0)
        else:
            return (now + timedelta(hours=1)).replace(minute=base, second=0, microsecond=0)
    except (IndexError, ValueError):
        return None
    
def get_index_info():
    """Gathers and returns a dictionary of information about the search indexes."""
    info = {"state": "[red]Unknown[/red]", "last_run": "N/A",
            "next_run": "N/A", "items": 0, "unprocessed": 0}
    if os.path.exists(ID_MAP_PATH):
        try:
            with open(ID_MAP_PATH, 'r') as f:
                info["items"] = len(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    try:
        total_files = len(glob.glob(os.path.join(OCR_TEXT_DIR, "*.txt")))
        info["unprocessed"] = max(0, total_files - info["items"])
    except IOError:
        pass
    if subprocess.run(f"systemctl --user is-active --quiet hindsight-rebuild.service", shell=True).returncode == 0:
        info["state"] = "[bold yellow]Actively Indexing[/bold yellow]"
    else:
        info["state"] = "[cyan]Idle / Waiting[/cyan]"
    info["last_run"] = get_last_successful_run_from_log()
    next_run_dt = calculate_next_run(datetime.now(), schedule="*:0/15")
    if next_run_dt:
        info["next_run"] = next_run_dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        info["next_run"] = "Manual schedule"
    return info

# --- UI Rendering ---
def make_layout() -> Layout:
    """Defines the Rich layout structure."""
    layout = Layout(name="root")
    layout.split(Layout(name="header", size=3), Layout(name="body", ratio=1), Layout(name="footer", size=5))
    top_row = Layout(name="top_row", size=5)
    top_row.split_row(Layout(name="status"), Layout(name="resources"))
    layout["body"].split(top_row, Layout(name="index_status"))
    return layout
    
def update_dashboard_layout(layout: Layout) -> None:
    """Renders all the content for the dashboard UI."""
    header_grid = Table.grid(expand=True)
    header_grid.add_column(justify="center")
    header_grid.add_column(justify="right")
    header_grid.add_row("[b]Hindsight v5 Service Manager[/b]", f"[cyan]{time.ctime()}[/cyan]")
    layout["header"].update(Panel(header_grid, style="white on dark_violet", padding=(0, 1)))

    status_table = Table(box=None, expand=True, show_header=False, padding=0)
    status_table.add_column(ratio=1, justify="right", no_wrap=True)
    status_table.add_column(ratio=1, justify="left")
    status_table.add_row("[bold magenta]API Service: [/bold magenta]", get_service_status("hindsight-api.service"))
    status_table.add_row("[bold magenta]Indexing Timer: [/bold magenta]", get_service_status("hindsight-rebuild.timer"))
    status_table.add_row("[bold magenta]Memory Daemon: [/bold magenta]", get_service_status("hindsight-daemon.service"))
    layout["status"].update(Panel(status_table, title="[bold]Service Status[/bold]", border_style="magenta", padding=(0, 2)))

    resource_table = Table(box=None, expand=True, show_header=False, padding=0)
    resource_table.add_column(ratio=1, justify="right", no_wrap=True)
    resource_table.add_column(ratio=1, justify="left")
    cpu, mem, p_count = get_resource_usage()
    resource_table.add_row("[bold cyan]CPU Usage: [bold cyan]", f"{cpu:.2f} %")
    resource_table.add_row("[bold cyan]Memory: [bold cyan]", f"{mem:.2f} MB")
    resource_table.add_row("[bold cyan]Processes: [bold cyan]", str(p_count))
    layout["resources"].update(Panel(resource_table, title="[bold]Live Resources[/bold]", border_style="cyan", padding=(0, 2)))

    index_info = get_index_info()
    
    # UPDATED: Use a single 4-column grid for better alignment in small terminals.
    index_grid = Table.grid(expand=True, padding=(0, 1))
    index_grid.add_column(justify="right", no_wrap=True)
    index_grid.add_column(justify="left")
    index_grid.add_column(justify="right", no_wrap=True)
    index_grid.add_column(justify="left")

    index_grid.add_row(
        "[bold yellow]Indexed Items: [/bold yellow]",
        str(index_info["items"]),
        "[bold yellow]Last Run: [/bold yellow]",
        index_info["last_run"]
    )
    index_grid.add_row(
        "[bold yellow]Unprocessed Files: [/bold yellow]",
        str(index_info["unprocessed"]),
        "[bold yellow]Next Run: [/bold yellow]",
        index_info["next_run"]
    )

    layout["index_status"].update(Panel(index_grid, title=f"[bold]Index Status: {index_info['state']}[/bold]", border_style="yellow", padding=(0, 2)))

    if app_state["mode"] == "normal":
        menu = ("(1) Start/Restart All | (2) Stop All | (3) View Logs | (4) Edit Config\n"
                "(5) Reconfigure | (6) Debugger | (Ctrl+C to Quit)")
        footer_panel = Panel(Text(menu, justify="center"), title="[bold]Interactive Menu[/bold]", style="white on dark_violet")
    else:
        action_text = app_state["mode"].split('_')[1]
        menu = f"Are you sure you want to {action_text} all services? ([bold]y[/bold]/[bold]n[/bold])"
        footer_panel = Panel(Text.from_markup(menu, justify="center"), title="[bold red]Confirmation Required[/bold red]", style="bold white on red", border_style="red")
    layout["footer"].update(footer_panel)

def read_keyboard_input(queue):
    """Reads single characters from stdin and puts them in a queue."""
    while True:
        try:
            char = sys.stdin.read(1)
            if char:
                queue.put(char)
            else:
                break
        except Exception:
            break

# --- Main Application Logic ---
if __name__ == "__main__":
    input_queue = queue.Queue()
    input_thread = threading.Thread(target=read_keyboard_input, args=(input_queue,), daemon=True)
    input_thread.start()
    layout = make_layout()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        with Live(layout, screen=True, redirect_stderr=False, refresh_per_second=4) as live:
            while True:
                if not input_queue.empty():
                    action = input_queue.get().lower()
                    if app_state["mode"].startswith("confirm_"):
                        mode_action = app_state["mode"].split('_')[1]
                        if action == 'y':
                            manage_all_services(mode_action)
                        app_state["mode"] = "normal"
                    elif app_state["mode"] == "normal":
                        if action == '1':
                            app_state["mode"] = "confirm_restart"
                        elif action == '2':
                            app_state["mode"] = "confirm_stop"
                        elif action == '3':
                            run_command(f"gnome-terminal -- bash -c 'tail -n 200 -f {LOG_FILE}; exec bash'")
                        elif action == '4':
                            editor = os.environ.get('EDITOR', 'nano')
                            # The config path is now the source of truth
                            run_command(f"gnome-terminal -- bash -c '{editor} {config_path}; exec bash'")
                        elif action == '5':
                            reconfigure_script = os.path.join(SCRIPTS_PATH, "configure.sh")
                            command = f"gnome-terminal -- bash -c '\"{reconfigure_script}\"; echo \"\nReconfiguration finished. Press Enter to close.\"; read'"
                            run_command(command)
                        elif action == '6':
                            python_executable = os.path.join(VENV_PATH, "bin", "python")
                            debugger_script = os.path.join(APP_PATH, "debugger.py")
                            command = f"gnome-terminal -- bash -c '\"{python_executable}\" \"{debugger_script}\"; exec bash'"
                            run_command(command)
                
                update_dashboard_layout(layout)
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    except Exception:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        console.print_exception()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        console.print("[bold magenta]Exiting Hindsight Manager.[/bold magenta]")