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
"""Hindsight API helpers and Flask endpoint utilities.

This module exposes helper functions and the Flask ``app`` used by the
Hindsight HTTP API. It contains utility functions for formatting responses,
query helpers and small wrappers used by the API endpoints.
"""


from flask import Flask, request, jsonify
import configparser
import os
import subprocess
import psutil
import json
import glob
from datetime import datetime, timezone, timedelta
import stat

app = Flask(__name__)

# --- Configuration Loading ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

# --- Fetching settings for helper functions ---
DB_DIR = config.get('System Paths', 'DB_DIR')
ID_MAP_PATH = os.path.join(DB_DIR, 'hindsight_id_map.json')
FAISS_INDEX_PATH = os.path.join(DB_DIR, 'hindsight_faiss.index')
OCR_TEXT_DIR = config.get('System Paths', 'OCR_TEXT_DIR')
RECOLL_CONF_DIR = config.get('Search', 'RECOLL_CONF_DIR', fallback=os.path.join(DB_DIR, 'recoll'))
ENABLE_RECOLL = config.getboolean('Search', 'ENABLE_RECOLL', fallback=True)
ENABLE_FAISS = config.getboolean('Search', 'ENABLE_FAISS', fallback=True)

# --- Data Gathering Helper Functions ---
def format_status(state):
    """Map a raw service state string to a colored human-readable label.

    Args:
        state: The raw state string returned by systemctl (e.g. "active").

    Returns:
        A colored label string appropriate for terminal display.
    """
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

def format_time(ts):
    try:
        return datetime.fromtimestamp(ts).strftime('%H:%M:%S')
    except Exception:
        return "N/A"

def get_faiss_stats():
    """Return FAISS processed/unprocessed counts and last run time."""
    if not ENABLE_FAISS:
        return {"faiss_processed": "Disabled", "faiss_unprocessed": "Disabled", "faiss_last_run": "-"}
    total_txt = len(glob.glob(os.path.join(OCR_TEXT_DIR, '*.txt')))
    processed = 0
    if os.path.exists(ID_MAP_PATH):
        try:
            with open(ID_MAP_PATH, 'r', encoding='utf-8') as f:
                id_map = json.load(f)
            if isinstance(id_map, list):
                processed = len(id_map)
        except Exception:
            processed = 0
    unprocessed = max(total_txt - processed, 0)
    # last run = mtime of FAISS index or id map (latest)
    mtimes = []
    for p in (FAISS_INDEX_PATH, ID_MAP_PATH):
        if os.path.exists(p):
            try:
                mtimes.append(os.path.getmtime(p))
            except Exception:
                pass
    last_run = format_time(max(mtimes)) if mtimes else "N/A"
    return {
        "faiss_processed": f"{processed}",
        "faiss_unprocessed": f"{unprocessed}",
        "faiss_last_run": last_run
    }

def get_recoll_stats():
    """Approximate Recoll indexing stats based on xapiandb mtime."""
    if not ENABLE_RECOLL:
        return {"recoll_processed": "Disabled", "recoll_unprocessed": "Disabled", "recoll_last_run": "-"}
    xapiandb = os.path.join(RECOLL_CONF_DIR, 'xapiandb')
    total_txt = len(glob.glob(os.path.join(OCR_TEXT_DIR, '*.txt')))
    if not os.path.isdir(xapiandb):
        return {"recoll_processed": "0", "recoll_unprocessed": f"{total_txt}", "recoll_last_run": "N/A"}
    # Determine index last update time by newest file in xapiandb
    latest = 0
    try:
        for root, dirs, files in os.walk(xapiandb):
            for name in files:
                path = os.path.join(root, name)
                try:
                    mt = os.path.getmtime(path)
                    if mt > latest:
                        latest = mt
                except Exception:
                    continue
    except Exception:
        latest = 0
    # Count unprocessed = OCR files newer than latest mtime
    unprocessed = 0
    if latest:
        for fpath in glob.glob(os.path.join(OCR_TEXT_DIR, '*.txt')):
            try:
                if os.path.getmtime(fpath) > latest:
                    unprocessed += 1
            except Exception:
                continue
    else:
        unprocessed = total_txt
    processed = max(total_txt - unprocessed, 0)
    return {
        "recoll_processed": f"{processed}",
        "recoll_unprocessed": f"{unprocessed}",
        "recoll_last_run": format_time(latest) if latest else "N/A"
    }

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
    """Handle POST /query requests from clients.

    The endpoint expects JSON with a query payload and returns search
    results in JSON format. Implementation-specific logic is contained
    in the main application and plugged into this handler.
    """
    # ... (your existing query logic remains here) ...
    return jsonify({"error": "Query logic not shown"}), 500

# --- NEW: The /status Endpoint ---
@app.route('/status', methods=['GET'])
def get_status():
    """Gathers all system and application metrics and returns them as a single JSON object."""
    cpu, mem, io = get_resource_usage()
    db_size, total_records = get_db_stats()

    faiss_stats = get_faiss_stats()
    recoll_stats = get_recoll_stats()

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
        # Recoll details
        **recoll_stats,
        # FAISS details
        **faiss_stats,
        # Shared schedule (timer drives both phases)
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
