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
"""Background daemon that captures screenshots and runs OCR.

This module implements the memory_daemon process which periodically captures
the active window, runs OCR (Tesseract) and writes OCR text files used by the
indexing pipeline.
"""


import time
import subprocess
import threading
import os
import shutil
from PIL import Image
import configparser
from utils import setup_logger
import datetime

# --- New Config Parser Logic ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

# --- Fetching settings ---
POLL_INTERVAL = config.getint('User Settings', 'POLL_INTERVAL')
PAUSE_WHEN_LOCKED = config.getboolean('User Settings', 'PAUSE_WHEN_LOCKED', fallback=True)
PAUSE_ON_SUSPEND = config.getboolean('User Settings', 'PAUSE_ON_SUSPEND', fallback=True)
EXCLUDED_APPS_STR = config.get('User Settings', 'EXCLUDED_APPS', fallback='')
EXCLUDED_APPS = [app.strip() for app in EXCLUDED_APPS_STR.split(',') if app.strip()]
SCREENSHOT_DIR = config.get('System Paths', 'SCREENSHOT_DIR')
OCR_TEXT_DIR = config.get('System Paths', 'OCR_TEXT_DIR')

logger = setup_logger("HindsightDaemon")

# --- State Management ---
processing_lock = threading.Lock()
last_screenshot_paths = {}
_last_lock_check = 0.0
_LOCK_CHECK_INTERVAL = 5  # seconds
_last_lock_log = 0.0
_LOCK_LOG_INTERVAL = 60  # seconds
_suspend_state = False
_last_suspend_log = 0.0
_SUSPEND_LOG_INTERVAL = 60  # seconds

def _resolve_session_id():
    sid = os.environ.get("XDG_SESSION_ID")
    if sid:
        return sid
    # Fallback: parse loginctl list-sessions
    try:
        out = subprocess.check_output(["loginctl", "list-sessions", "--no-legend"], text=True)
        user = os.environ.get("USER")
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] == user:
                return parts[0]
    except Exception:
        pass
    return None

def session_locked():
    """Best-effort detection of desktop lock state.

    Uses `loginctl show-session <id> -p LockedHint`. Returns False if undetectable.
    Cached for _LOCK_CHECK_INTERVAL seconds to reduce overhead.
    """
    global _last_lock_check, _cached_locked
    now = time.time()
    if ' _cached_locked' not in globals():
        _cached_locked = False  # type: ignore
    if now - _last_lock_check < _LOCK_CHECK_INTERVAL:
        return _cached_locked  # type: ignore
    _last_lock_check = now
    sid = _resolve_session_id()
    if not sid:
        return False
    try:
        out = subprocess.check_output(["loginctl", "show-session", sid, "-p", "LockedHint"], text=True)
        _cached_locked = ("LockedHint=yes" in out)
        return _cached_locked  # type: ignore
    except Exception:
        return False

def get_active_window_info():
    """Return the active window ID and title, or (None, None) on failure.

    Returns:
        A tuple of (window_id, window_title) or (None, None) when the active
        window could not be determined.
    """
    try:
        env = os.environ.copy()
        env['DISPLAY'] = ':0'
        window_id = subprocess.check_output(["xdotool", "getactivewindow"], env=env).strip().decode()
        window_title_raw = subprocess.check_output(["xprop", "-id", window_id, "WM_NAME"], env=env).strip().decode()
        window_title = window_title_raw.split(' = ')[1].strip('"')
        return window_id, window_title
    except (subprocess.CalledProcessError, IndexError) as e:
        logger.error(f"Failed to get active window info: {e}")
        return None, None

def extract_text_with_tesseract(screenshot_path, text_output_path):
    """Run Tesseract OCR on an image and write the extracted text to a file.

    Args:
        screenshot_path: Path to the input image file.
        text_output_path: Destination path for the OCR text output.
    """
    try:
        ocr_text = subprocess.check_output(
            ["tesseract", screenshot_path, "stdout"], stderr=subprocess.DEVNULL
        ).decode()
        with open(text_output_path, "w", encoding='utf-8') as f:
            f.write(ocr_text)
    except subprocess.CalledProcessError as e:
        logger.warning(f"Tesseract OCR failed with exit code {e.returncode} for {screenshot_path}.")
    except Exception:
        logger.exception(f"An unexpected Tesseract OCR error occurred for {screenshot_path}")

def process_active_window():
    """Capture the active window and produce OCR text for it.

    This function is the core processing step used by the daemon loop. It
    captures the active window, compares it against the last captured frame to
    avoid duplicates, and runs OCR to produce a text file.
    """
    if not processing_lock.acquire(blocking=False):
        return
    try:
        
        window_id, window_title = get_active_window_info()
        if not window_id or not window_title:
            return
        if any(excluded in window_title.lower() for excluded in EXCLUDED_APPS):
            return

        timestamp = int(time.time())
        new_screenshot_path = os.path.join(SCREENSHOT_DIR, f"{window_id}_{timestamp}.png")

        print(f"Attempting to save screenshot to: {new_screenshot_path}") # More debugging

        env = os.environ.copy()
        env['DISPLAY'] = ':0'
        subprocess.run(["maim", "--window", window_id, new_screenshot_path], check=True, capture_output=True, env=env)

        last_screenshot_path = last_screenshot_paths.get(window_id)
        if last_screenshot_path and os.path.exists(last_screenshot_path):
            try:
                img_new = Image.open(new_screenshot_path)
                img_old = Image.open(last_screenshot_path)
                if list(img_new.getdata()) == list(img_old.getdata()):
                    os.remove(new_screenshot_path)
                    return
            except Exception:
                logger.exception("Image comparison failed. Processing file anyway.")

        last_screenshot_paths[window_id] = new_screenshot_path
        ocr_filename = os.path.join(OCR_TEXT_DIR, f"{window_id}_{timestamp}.txt")
        extract_text_with_tesseract(new_screenshot_path, ocr_filename)

        logger.info(f"Screenshot captured and processed for window: {window_title}")

    except subprocess.CalledProcessError:
        logger.warning("maim failed, likely because the window closed.")
    except Exception:
        logger.exception("An unexpected error occurred within a processing cycle")
    finally:
        processing_lock.release()

def main():
    """Daemon entrypoint: ensure directories exist and start the loop.

    This entrypoint creates necessary directories, then repeatedly calls
    :func:`process_active_window` according to the configured polling
    interval until interrupted.
    """
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(OCR_TEXT_DIR, exist_ok=True)
    logger.info("Hindsight Daemon started. Monitoring activity...")

    # Start background thread to watch for system suspend/resume (DBus) if desired
    def suspend_watcher():
        global _suspend_state, _last_suspend_log
        if not PAUSE_ON_SUSPEND:
            return
        if not shutil.which("dbus-monitor"):
            logger.debug("dbus-monitor not found; suspend detection disabled.")
            return
        cmd = ["dbus-monitor", "--system", "type='signal',interface='org.freedesktop.login1.Manager',member='PrepareForSleep'"]
        try:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as proc:
                if proc.stdout is None:
                    return
                for line in proc.stdout:
                    if 'boolean true' in line:
                        if not _suspend_state:
                            _suspend_state = True
                            logger.info("System preparing for suspend; pausing capture.")
                    elif 'boolean false' in line:
                        if _suspend_state:
                            _suspend_state = False
                            logger.info("System resumed from suspend; resuming capture.")
        except Exception:
            logger.debug("Suspend watcher terminated or failed.")

    threading.Thread(target=suspend_watcher, name="SuspendWatcher", daemon=True).start()
    try:
        while True:
            if PAUSE_ON_SUSPEND and _suspend_state:
                global _last_suspend_log
                now = time.time()
                if now - _last_suspend_log > _SUSPEND_LOG_INTERVAL:
                    logger.info("Suspended state active; capture paused.")
                    _last_suspend_log = now
                time.sleep(POLL_INTERVAL)
                continue
            if PAUSE_WHEN_LOCKED and session_locked():
                global _last_lock_log
                now = time.time()
                if now - _last_lock_log > _LOCK_LOG_INTERVAL:
                    logger.info("System locked; pausing capture.")
                    _last_lock_log = now
                time.sleep(POLL_INTERVAL)
                continue
            process_active_window()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Hindsight Daemon shutting down.")
    except Exception:
        logger.critical("Hindsight Daemon encountered a fatal error and is stopping.", exc_info=True)

if __name__ == "__main__":
    main()
