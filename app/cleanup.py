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
import time
import glob
import configparser
from utils import setup_logger

# --- New Config Parser Logic ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

# --- Fetching settings ---
DAYS_TO_KEEP = config.getint('User Settings', 'DAYS_TO_KEEP')
SCREENSHOT_DIR = config.get('System Paths', 'SCREENSHOT_DIR')
OCR_TEXT_DIR = config.get('System Paths', 'OCR_TEXT_DIR')
FAISS_INDEX_PATH = config.get('System Paths', 'DB_DIR') + '/hindsight_faiss.index'
ID_MAP_PATH = config.get('System Paths', 'DB_DIR') + '/hindsight_id_map.json'

logger = setup_logger("HindsightCleanup")

def delete_old_data(dry_run=False):
    """Finds and deletes data files older than DAYS_TO_KEEP."""
    logger.info(f"Starting data cleanup process. Retention period: {DAYS_TO_KEEP} days.")
    now = time.time()
    cutoff = now - (DAYS_TO_KEEP * 86400)
    files_to_delete = []

    for dir_path in [SCREENSHOT_DIR, OCR_TEXT_DIR]:
        try:
            files = glob.glob(os.path.join(dir_path, "*"))
            for f in files:
                if os.path.getmtime(f) < cutoff:
                    files_to_delete.append(f)
        except FileNotFoundError:
            logger.warning(f"Directory not found, skipping: {dir_path}")
            continue

    if not files_to_delete:
        logger.info("No old files found to delete. Data is within retention period.")
        return

    if dry_run:
        logger.info(f"[DRY RUN] Would delete {len(files_to_delete)} files older than {DAYS_TO_KEEP} days.")
        for f in files_to_delete[:5]:
             logger.info(f"[DRY RUN] ... {os.path.basename(f)}")
        if len(files_to_delete) > 5:
             logger.info(f"[DRY RUN] ... and {len(files_to_delete) - 5} more.")
        return

    logger.info(f"Deleting {len(files_to_delete)} files...")
    deleted_count = 0
    for f in files_to_delete:
        try:
            os.remove(f)
            deleted_count += 1
        except OSError as e:
            logger.error(f"Failed to delete {f}: {e}")

    logger.info(f"Successfully deleted {deleted_count} files.")
    if deleted_count > 0:
        logger.warning("Data files have been deleted. The FAISS index is now inconsistent.")
        logger.warning("It is recommended to run 'Clean FAISS Index' to force a full rebuild.")

def clean_faiss_index(dry_run=False):
    """Deletes the FAISS index and map files to force a full rebuild."""
    index_files = [FAISS_INDEX_PATH, ID_MAP_PATH]
    files_exist = [f for f in index_files if os.path.exists(f)]

    if not files_exist:
        logger.info("FAISS index files do not exist. No cleanup needed.")
        return

    if dry_run:
        logger.info("[DRY RUN] Would delete the following FAISS index files to force a rebuild:")
        for f in files_exist:
            logger.info(f"[DRY RUN] ... {f}")
        return

    logger.info("Deleting FAISS index files to force a full rebuild...")
    for f in files_exist:
        try:
            os.remove(f)
            logger.info(f"Deleted {f}")
        except OSError as e:
            logger.error(f"Failed to delete {f}: {e}")