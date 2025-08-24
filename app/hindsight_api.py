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

from flask import Flask, request, jsonify
import configparser
import os
import subprocess
import psutil
import json
import glob
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# --- Configuration Loading ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

# --- Fetching settings for helper functions ---
ID_MAP_PATH = os.path.join(config.get('System Paths', 'DB_DIR'), 'hindsight_id_map.json')
OCR_TEXT_DIR = config.get('System Paths', 'OCR_TEXT_DIR')

# --- Data Gathering Helper Functions ---
def format_status(state):
    mapping = {
        "active": "[green]● Running[/green]",
        "activating": "[yellow]● Starting[/yellow]",
        "deactivating": "[yellow]● Stopping[/yellow]",
        "inactive": "[yellow]○ Inactive[/yellow]",
        "failed": "[red]● Failed[/red]",
    }
    return mapping.get(state, "[red]● Unknown[/red]")

def get_service_status(unit_name):
    """Uses systemd to get unit active state (no PID file dependency)."""
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "is-active", unit_name],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
        return format_status(out)
    except subprocess.CalledProcessError:
        return "[red]○ Not Found[/red]"

def get_timer_status(timer_name):
    """Checks the status of a systemd timer."""
    try:
        # Timers must be checked with systemctl
        output = subprocess.check_output(["systemctl", "--user", "is-active", timer_name], text=True, stderr=subprocess.DEVNULL).strip()
        if output == "active":
            return "[green]● Waiting[/green]" # "active" for a timer means it's enabled and waiting
        else:
            return "[yellow]○ Inactive[/yellow]"
    except subprocess.CalledProcessError:
        return "[red]○ Not Found[/red]"

def get_resource_usage():
    """Calculates resource usage for all Hindsight-related python scripts."""
    cpu_total = 0.0
    mem_total = 0.0
    io_read_total = 0
    io_write_total = 0

    # Find all running hindsight processes
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = " ".join(proc.info['cmdline']) if proc.info['cmdline'] else ""
            if 'hindsight' in cmdline or 'memory_daemon.py' in cmdline or 'hindsight_api.py' in cmdline:
                p = psutil.Process(proc.info['pid'])
                cpu_total += p.cpu_percent(interval=None)
                mem_total += p.memory_info().rss
                io = p.io_counters()
                io_read_total += io.read_bytes
                io_write_total += io.write_bytes
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return f"{cpu_total:.1f}%", f"{mem_total / (1024*1024):.1f} MB", f"R/W: {io_read_total / 1024:.1f}/{io_write_total / 1024:.1f} KB"

def get_index_schedule():
    """Calculates the approximate next run time for the indexer."""
    now = datetime.now()
    next_minute = ((now.minute // 15) + 1) * 15
    if next_minute >= 60:
        next_hour = (now.hour + 1) % 24
        next_minute = 0
        return f"~ {next_hour:02d}:{next_minute:02d}"
    return f"~ {now.hour:02d}:{next_minute:02d}"

def get_last_update_time():
    """Gets the timestamp of the last index update."""
    try:
        if not os.path.exists(ID_MAP_PATH) or os.path.getsize(ID_MAP_PATH) == 0:
            return "N/A"
        with open(ID_MAP_PATH, 'r') as f: data = json.load(f)
        if not data: return "N/A"
        latest_timestamp = max(float(k) for k in data.keys())
        return datetime.fromtimestamp(latest_timestamp).strftime('%H:%M:%S')
    except (json.JSONDecodeError, ValueError, FileNotFoundError):
        return "N/A"

def get_db_stats():
    """Calculates database size and record count."""
    try:
        file_list = glob.glob(os.path.join(OCR_TEXT_DIR, '*.txt'))
        num_records = len(file_list)
        total_size = sum(os.path.getsize(f) for f in file_list)
        return f"{total_size / (1024 * 1024):.2f} MB", f"{num_records:,}"
    except Exception:
        return "N/A", "N/A"

# --- Existing /query Endpoint (No changes needed) ---
@app.route('/query', methods=['POST'])
def query():
    # ... (your existing query logic remains here) ...
    return jsonify({"error": "Query logic not shown"}), 500

# --- NEW: The /status Endpoint ---
@app.route('/status', methods=['GET'])
def get_status():
    """Gathers all system and application metrics and returns them as a single JSON object."""
    cpu, mem, io = get_resource_usage()
    db_size, total_records = get_db_stats()

    status_data = {
        # Service Status
        "api_status": get_service_status("hindsight-api.service"),
        "daemon_status": get_service_status("hindsight-daemon.service"),
        "timer_status": get_timer_status("hindsight-rebuild.timer"),
        # Resource Usage
        "cpu_usage": cpu,
        "mem_usage": mem,
        "io_usage": io,
        # Index Stats
        "db_size": db_size,
        "total_records": total_records,
        "last_update": get_last_update_time(),
        "next_update": get_index_schedule()
    }
    return jsonify(status_data)

# --- Main Application Runner ---
if __name__ == '__main__':
    # Initialize CPU usage calculation
    psutil.cpu_percent(interval=None)
    # Get host and port from config, with defaults
    host = config.get('API', 'Host', fallback='127.0.0.1')
    port = config.getint('API', 'Port', fallback=5000)
    app.run(host=host, port=port)
    host = config.get('API', 'Host', fallback='127.0.0.1')
    port = config.getint('API', 'Port', fallback=5000)
    app.run(host=host, port=port)
