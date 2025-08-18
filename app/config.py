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

from pathlib import Path

# The absolute path to the 'app' directory (where this config.py file lives)
BASE_PATH = Path(__file__).resolve().parent

# --- All other paths are now defined relative to BASE_PATH ---
DATA_DIR = BASE_PATH.parent / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
OCR_TEXT_DIR = DATA_DIR / "ocr_text"
DB_DIR = DATA_DIR / "db"
LOG_FILE = DATA_DIR / "hindsight.log"
LOG_DIR = DATA_DIR
RECOLL_CONF_DIR = DB_DIR / "recoll_conf"
FAISS_INDEX_PATH = str(DB_DIR / "hindsight_faiss.index")
ID_MAP_PATH = str(DB_DIR / "hindsight_id_map.json")

# --- Application Settings ---

# Polling interval in seconds for the memory daemon to wait between screenshots.
POLL_INTERVAL = 5

# --- ADDED: Data retention period in days ---
# Set the number of days to keep data for. Files older than this will be deleted by the cleanup script.
DAYS_TO_KEEP = 90

# List of window titles (case-insensitive) to exclude from screenshots.
EXCLUDED_APPS = [
    'keepassxc'
]

# --- AI Model Settings ---
EMBEDDING_MODEL = 'all-mpnet-base-v2'
REFINER_MODEL = 'gemini-2.5-flash'