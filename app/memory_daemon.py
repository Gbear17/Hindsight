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

# Hindsight Polling Daemon (Refactored)
import time
import subprocess
import threading
import os
from PIL import Image

# --- Imports from new modules ---
import config
from utils import setup_logger

# --- Setup logger ---
logger = setup_logger("HindsightDaemon")

# --- State Management ---
processing_lock = threading.Lock()
last_screenshot_paths = {}

def get_active_window_info():
    """Gets the ID and title of the currently active window."""
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
    """Runs Tesseract OCR on a screenshot and saves the text."""
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
    """The main processing function for capturing and analyzing a window."""
    if not processing_lock.acquire(blocking=False):
        return
    try:
        window_id, window_title = get_active_window_info()
        if not window_id or not window_title:
            return
        if any(excluded in window_title.lower() for excluded in config.EXCLUDED_APPS):
            return

        timestamp = int(time.time())
        new_screenshot_path = os.path.join(config.SCREENSHOT_DIR, f"{window_id}_{timestamp}.png")
        
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
        ocr_filename = os.path.join(config.OCR_TEXT_DIR, f"{window_id}_{timestamp}.txt")
        extract_text_with_tesseract(new_screenshot_path, ocr_filename)
        
        logger.info(f"Screenshot captured and processed for window: {window_title}")

    except subprocess.CalledProcessError:
        logger.warning("maim failed, likely because the window closed.")
    except Exception:
        logger.exception("An unexpected error occurred within a processing cycle")
    finally:
        processing_lock.release()

def main():
    os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(config.OCR_TEXT_DIR, exist_ok=True)
    logger.info("Hindsight Daemon started. Monitoring activity...")
    try:
        while True:
            process_active_window()
            time.sleep(config.POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Hindsight Daemon shutting down.")
    except Exception:
        logger.critical("Hindsight Daemon encountered a fatal error and is stopping.", exc_info=True)

if __name__ == "__main__":
    main()
