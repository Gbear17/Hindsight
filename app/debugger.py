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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import os
import sys
import configparser
import json
import glob
import subprocess
import shutil
try:
    import requests
    HAS_REQUESTS = True
except Exception:
    requests = None
    HAS_REQUESTS = False
import tarfile
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import code
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# --- Setup: Load Configuration & Initialize Console ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

LOG_FILE = config.get('System Paths', 'LOG_FILE')
DB_DIR = config.get('System Paths', 'DB_DIR')
ID_MAP_PATH = os.path.join(DB_DIR, 'hindsight_id_map.json')
OCR_TEXT_DIR = config.get('System Paths', 'OCR_TEXT_DIR')
SCREENSHOT_DIR = config.get('System Paths', 'SCREENSHOT_DIR')

console = Console()

# --- Read-Only Functions (Available in all modes) ---

def get_last_successful_run_from_log():
    """(SAFE) Finds the timestamp of the last successful index run from the log file."""
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
    """(SAFE) Calculates the next run time based on a simple cron-like schedule."""
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
    """(SAFE) Gathers information about the search indexes."""
    info = {"items": 0, "unprocessed": 0, "last_run": "N/A", "next_run": "N/A"}
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
    info["last_run"] = get_last_successful_run_from_log()
    next_run_dt = calculate_next_run(datetime.now(), schedule="*:0/15")
    if next_run_dt:
        info["next_run"] = next_run_dt.strftime("%Y-%m-%d %H:%M:%S")
    return info

# --- NEW: Destructive Functions (Read-Write) ---

def delete_latest_record():
    """(LIVE) Finds and permanently deletes the most recent entry from the database."""
    if not require_confirmation('Permanently delete the latest record from the ID map? This cannot be undone.'):
        return "[yellow]Aborted by user. No changes made.[/yellow]"
    try:
        if not os.path.exists(ID_MAP_PATH):
            return "[yellow]ID map file not found. No action taken.[/yellow]"
        with open(ID_MAP_PATH, 'r+') as f:
            data = json.load(f)
            if not data: return "[yellow]Database is already empty.[/yellow]"
            latest_timestamp = max(float(k) for k in data.keys())
            del data[str(latest_timestamp)]
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()
        return f"[green]Successfully deleted record with timestamp: {latest_timestamp}[/green]"
    except Exception as e:
        return f"[red]An error occurred: {e}[/red]"

def clear_database():
    """(LIVE) Permanently deletes ALL records from the Hindsight database."""
    if not require_confirmation('Permanently clear the entire ID map (all records)? This will erase your database.'):
        return "[yellow]Aborted by user. No changes made.[/yellow]"
    try:
        if not os.path.exists(ID_MAP_PATH):
            return "[yellow]ID map file not found. No action taken.[/yellow]"
        with open(ID_MAP_PATH, 'w') as f:
            json.dump({}, f)
        return "[green]Successfully cleared the database.[/green]"
    except Exception as e:
        return f"[red]An error occurred: {e}[/red]"

# --- NEW: Dry Run Versions of Destructive Functions ---

def dry_run_delete_latest_record():
    """(DRY RUN) Shows which record would be deleted without changing data."""
    console.print("[cyan][DRY RUN][/cyan] Would find the latest timestamp in the database and remove that entry.")
    return "No actual data was changed."

def dry_run_clear_database():
    """(DRY RUN) Simulates clearing all records without changing data."""
    console.print("[cyan][DRY RUN][/cyan] Would overwrite the database file with an empty JSON object.")
    return "No actual data was changed."


def require_confirmation(action_desc):
    """Prompt the user for an explicit confirmation. Returns True only if user types 'yes'."""
    try:
        console.print(f"[bold red]CONFIRM:[/bold red] {action_desc}")
        resp = console.input("Type 'yes' to proceed: ")
        return resp.strip().lower() == 'yes'
    except Exception:
        # Non-interactive environment: do not proceed
        return False

# --- NEW: Helpful Debug Utilities (Dry / Live) ---

def list_recent_screenshots(limit=10):
    """(SAFE) Lists the most recent screenshots with basic metadata."""
    try:
        files = sorted(glob.glob(os.path.join(SCREENSHOT_DIR, "*.png")), key=os.path.getmtime, reverse=True)
        files = files[:limit]
        rows = []
        for p in files:
            mtime = datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M:%S')
            size_kb = os.path.getsize(p) / 1024
            rows.append({'path': p, 'mtime': mtime, 'size_kb': f"{size_kb:.1f}"})
        table = Table(show_header=True)
        table.add_column("Path")
        table.add_column("Modified")
        table.add_column("Size (KB)")
        for r in rows:
            table.add_row(r['path'], r['mtime'], r['size_kb'])
        console.print(table)
        return rows
    except Exception as e:
        return f"[red]Error listing screenshots: {e}[/red]"

def dry_run_list_recent_screenshots(limit=10):
    console.print("[cyan][DRY RUN][/cyan] Would list recent screenshots and show metadata.")
    return list_recent_screenshots(limit)

def simulate_capture():
    """(LIVE) Attempt a single capture+OCR cycle by calling the daemon's processor (best-effort).
    This may fail if DISPLAY or maim/tesseract are unavailable. Use only for debugging."""
    if not require_confirmation('Attempt a live capture+OCR cycle now? This may write files to disk.'):
        return "[yellow]Aborted by user. No capture performed.[/yellow]"
    try:
        import memory_daemon
        # Call the function directly; it is safe (best-effort) and returns None or logs
        memory_daemon.process_active_window()
        return "[green]Capture cycle attempted (check logs for details).[/green]"
    except Exception as e:
        return f"[red]Capture attempt failed: {e}[/red]"

def dry_run_simulate_capture():
    console.print("[cyan][DRY RUN][/cyan] Would run a single capture+OCR cycle (no files will be written).")
    return "No actual capture performed."

def rebuild_index():
    """(LIVE) Trigger the index rebuild. This may take time and use CPU/GPU resources."""
    if not require_confirmation('Trigger an index rebuild now? This may be resource intensive.'):
        return "[yellow]Aborted by user. No rebuild triggered.[/yellow]"
    try:
        import rebuild_index as ri
        ri.incremental_rebuild_faiss(dry_run=False)
        return "[green]Index rebuild triggered (check logs for progress).[/green]"
    except Exception as e:
        return f"[red]Index rebuild failed: {e}[/red]"

def dry_run_rebuild_index():
    try:
        import rebuild_index as ri
        ri.incremental_rebuild_faiss(dry_run=True)
        return "[cyan][DRY RUN][/cyan] Simulated index rebuild logged above."
    except Exception as e:
        return f"[red]Dry-run rebuild failed: {e}[/red]"

def export_database(dest_path=None):
    """(LIVE) Create a tar.gz archive of the DB directory. Returns path to archive."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_name = f"hindsight_db_export_{timestamp}.tar.gz"
        if not dest_path:
            dest_path = os.path.join(tempfile.gettempdir(), default_name)
        with tarfile.open(dest_path, "w:gz") as tar:
            tar.add(DB_DIR, arcname=os.path.basename(DB_DIR))
        return f"[green]Database exported to {dest_path}[/green]"
    except Exception as e:
        return f"[red]Export failed: {e}[/red]"

def dry_run_export_database(dest_path=None):
    console.print("[cyan][DRY RUN][/cyan] Would create a tar.gz archive of the DB directory.")
    return f"Would archive: {DB_DIR}"

def import_database(archive_path):
    """(LIVE) Safely import a DB archive by extracting into DB_DIR after making a timestamped backup."""
    if not require_confirmation(f'Import archive {archive_path} into DB_DIR ({DB_DIR})? Existing DB will be backed up.'):
        return "[yellow]Aborted by user. No import performed.[/yellow]"
    try:
        if not os.path.exists(archive_path):
            return "[yellow]Archive not found. No action taken.[/yellow]"
        # Backup existing DB_DIR
        backup_path = f"{DB_DIR}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if os.path.exists(DB_DIR):
            shutil.move(DB_DIR, backup_path)
        os.makedirs(DB_DIR, exist_ok=True)
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(path=os.path.dirname(DB_DIR))
        return f"[green]Database imported. Previous DB moved to: {backup_path}[/green]"
    except Exception as e:
        return f"[red]Import failed: {e}[/red]"

def dry_run_import_database(archive_path):
    console.print(f"[cyan][DRY RUN][/cyan] Would extract {archive_path} into {DB_DIR} after backing up the existing DB.")
    return "No changes made."

def tail_log(n=200):
    try:
        out = subprocess.check_output(["tail", "-n", str(n), LOG_FILE], text=True, stderr=subprocess.DEVNULL)
        return out
    except subprocess.CalledProcessError:
        return "[red]Failed to read log file.[/red]"

def dry_run_tail_log(n=200):
    console.print(f"[cyan][DRY RUN][/cyan] Would run: tail -n {n} {LOG_FILE}")
    return "No live tail performed."

def _systemd_check(unit_name):
    try:
        out = subprocess.check_output(["systemctl", "--user", "is-active", unit_name], text=True, stderr=subprocess.DEVNULL).strip()
        return out
    except subprocess.CalledProcessError:
        return "not-found"

def show_service_status():
    services = {
        'api': _systemd_check('hindsight-api.service'),
        'daemon': _systemd_check('hindsight-daemon.service'),
        'rebuild_timer': _systemd_check('hindsight-rebuild.timer'),
    }
    return services

def dry_run_show_service_status():
    console.print("[cyan][DRY RUN][/cyan] Would query systemd user services for api, daemon and rebuild timer.")
    return show_service_status()

def run_health_check():
    return {
        'services': show_service_status(),
        'index': get_index_info(),
        'last_run': get_last_successful_run_from_log(),
        'disk': disk_usage_report()
    }

def dry_run_run_health_check():
    console.print("[cyan][DRY RUN][/cyan] Would run a composite health check (services, index, disk).")
    return run_health_check()

def run_sample_query(q='test'):
    try:
        if not HAS_REQUESTS:
            return "[yellow]requests library not installed; cannot perform live query.[/yellow]"
        api_url = config.get('API', 'URL', fallback='http://127.0.0.1:5000').strip('\'"')
        resp = requests.post(f"{api_url}/query", json={'q': q}, timeout=2)
        try:
            return resp.json()
        except Exception:
            return resp.text
    except Exception as e:
        return f"[red]Sample query failed: {e}[/red]"

def dry_run_run_sample_query(q='test'):
    console.print(f"[cyan][DRY RUN][/cyan] Would POST a test query to the local API: '{q}'")
    return {'would_post': q}

def permission_check():
    checks = {}
    for p in [DB_DIR, OCR_TEXT_DIR, SCREENSHOT_DIR, LOG_FILE]:
        checks[p] = {
            'exists': os.path.exists(p),
            'readable': os.access(p, os.R_OK),
            'writable': os.access(p, os.W_OK)
        }
    return checks

def dry_run_permission_check():
    console.print("[cyan][DRY RUN][/cyan] Would check file ownership and read/write permissions for DB and data dirs.")
    return permission_check()

def disk_usage_report():
    try:
        def dir_size(path):
            total = 0
            for root, _, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except Exception:
                        pass
            return total

        ocr_size = dir_size(OCR_TEXT_DIR) / (1024*1024)
        db_size = dir_size(DB_DIR) / (1024*1024)
        screenshot_size = dir_size(SCREENSHOT_DIR) / (1024*1024)
        return {'ocr_mb': f"{ocr_size:.2f}", 'db_mb': f"{db_size:.2f}", 'screenshots_mb': f"{screenshot_size:.2f}"}
    except Exception as e:
        return f"[red]Disk usage check failed: {e}[/red]"

def dry_run_disk_usage_report():
    console.print("[cyan][DRY RUN][/cyan] Would report sizes for OCR, DB and screenshots directories.")
    return disk_usage_report()

def run_unit_tests():
    """(LIVE) Run pytest in the project root if available and return output."""
    if not require_confirmation('Run unit tests now? Tests will be executed in the project root.'):
        return "[yellow]Aborted by user. No tests executed.[/yellow]"
    try:
        result = subprocess.run([shutil.which('pytest') or 'pytest', '-q'], cwd=os.path.dirname(os.path.dirname(__file__)), capture_output=True, text=True, timeout=120)
        return result.stdout + '\n' + result.stderr
    except Exception as e:
        return f"[red]Running tests failed: {e}[/red]"

def dry_run_run_unit_tests():
    console.print("[cyan][DRY RUN][/cyan] Would run: pytest -q in the project root.")
    return "No tests executed." 

# --- NEW: Main Debugger Logic ---

def run_debugger():
    # Map all available functions
    FUNCTION_MAP = {
        "get_index_info": {"live": get_index_info, "dry": get_index_info},
        "get_last_successful_run_from_log": {"live": get_last_successful_run_from_log, "dry": get_last_successful_run_from_log},
        "delete_latest_record": {"live": delete_latest_record, "dry": dry_run_delete_latest_record},
        "clear_database": {"live": clear_database, "dry": dry_run_clear_database},
        "list_recent_screenshots": {"live": list_recent_screenshots, "dry": dry_run_list_recent_screenshots},
        "simulate_capture": {"live": simulate_capture, "dry": dry_run_simulate_capture},
        "rebuild_index": {"live": rebuild_index, "dry": dry_run_rebuild_index},
        "export_database": {"live": export_database, "dry": dry_run_export_database},
        "import_database": {"live": import_database, "dry": dry_run_import_database},
        "tail_log": {"live": tail_log, "dry": dry_run_tail_log},
        "show_service_status": {"live": show_service_status, "dry": dry_run_show_service_status},
        "run_health_check": {"live": run_health_check, "dry": dry_run_run_health_check},
        "run_sample_query": {"live": run_sample_query, "dry": dry_run_run_sample_query},
        "permission_check": {"live": permission_check, "dry": dry_run_permission_check},
        "disk_usage_report": {"live": disk_usage_report, "dry": dry_run_disk_usage_report},
        "run_unit_tests": {"live": run_unit_tests, "dry": dry_run_run_unit_tests},
    }

    # Mode Selection
    console.print(Panel("[bold magenta]Hindsight Interactive Debugger[/bold magenta]", expand=False, border_style="magenta"))
    console.print("\nChoose an execution mode:")
    console.print("  [bold]1) Dry Run[/bold]  - Simulate function calls, no data will be changed.")
    console.print("  [bold]2) Live[/bold]     - [red]Execute functions with real data.[/red]")

    mode = ""
    while mode not in ["1", "2"]:
        mode = console.input("\nEnter your choice (1 or 2): ")

    is_dry_run = (mode == "1")
    mode_name = "Dry Run" if is_dry_run else "Live"
    mode_color = "cyan" if is_dry_run else "bold red"

    namespace = {}

    table = Table(title=f"Available Functions in {mode_name} Mode", title_style=mode_color, show_header=True, header_style="bold blue")
    table.add_column("Function", style="bold")
    table.add_column("Description")

    for name, funcs in FUNCTION_MAP.items():
        func_to_load = funcs["dry"] if is_dry_run else funcs["live"]
        namespace[name] = func_to_load
        # Use the docstring from the live function for display
        table.add_row(f"{name}()", funcs.get("live", funcs["dry"]).__doc__)

    console.print("\n")
    console.print(table)

    banner = (
        f"\n--- Starting Hindsight Debugger in [{mode_color}]{mode_name}[/{mode_color}] Mode ---\n"
        "Type a function name like 'get_index_info()' and press Enter.\n"
        "Type 'exit()' or press Ctrl+D to quit."
    )
    code.interact(banner=banner, local=namespace, exitmsg="--- Exiting Hindsight Debugger ---")

if __name__ == "__main__":
    run_debugger()
