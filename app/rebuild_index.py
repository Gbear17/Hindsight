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
"""Index rebuild utilities for Hindsight.

This module provides routines to build and incrementally update the FAISS
semantic index used by Hindsight. The primary entrypoint is
:func:`incremental_rebuild_faiss` which can run in dry-run mode for testing.
"""


import os
import glob
import json
import numpy as np
import faiss
import subprocess
import shutil
import signal
import time
from sentence_transformers import SentenceTransformer
import configparser
from utils import setup_logger

# --- New Config Parser Logic ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

# --- Fetching settings ---
DB_DIR = config.get('System Paths', 'DB_DIR')
OCR_TEXT_DIR = config.get('System Paths', 'OCR_TEXT_DIR')
FAISS_INDEX_PATH = os.path.join(DB_DIR, 'hindsight_faiss.index')
ID_MAP_PATH = os.path.join(DB_DIR, 'hindsight_id_map.json')
# The embedding model is a core component, not a user setting, so it's defined here.
EMBEDDING_MODEL = 'all-mpnet-base-v2'
ENABLE_RECOLL = config.getboolean('Search', 'ENABLE_RECOLL', fallback=True)
ENABLE_FAISS = config.getboolean('Search', 'ENABLE_FAISS', fallback=True)
RECOLL_CONF_DIR = config.get('Search', 'RECOLL_CONF_DIR', fallback=os.path.join(DB_DIR, 'recoll'))
RECOLL_NICENESS = config.get('Search', 'RECOLL_NICENESS', fallback='10')
RECOLL_MAX_SECONDS = config.getint('Search', 'RECOLL_MAX_SECONDS', fallback=25)
FAISS_MAX_FILES_PER_CYCLE = config.getint('Search', 'FAISS_MAX_FILES_PER_CYCLE', fallback=0)
FAISS_MAX_SECONDS = config.getint('Search', 'FAISS_MAX_SECONDS', fallback=0)

logger = setup_logger("HindsightRebuildIndex")

# --- Tunable constants (could be promoted to config later) ---
BATCH_SIZE = 64  # Number of documents to embed per batch
EMBED_BATCH_SIZE = 32  # Internal batch size for model.encode
LOG_EVERY = 500  # Log a progress update every N processed files

def get_unprocessed_files(id_map):
    """Return .txt files that are not present in the supplied ID map.

    Args:
        id_map: An iterable (typically a list) of file paths already indexed.

    Returns:
        A sorted list of filesystem paths (strings) for .txt files that are
        present in ``OCR_TEXT_DIR`` but missing from ``id_map``.
    """
    indexed_files = set(id_map)
    all_files = set(glob.glob(os.path.join(OCR_TEXT_DIR, "*.txt")))
    return sorted(list(all_files - indexed_files))

def run_recoll_incremental():
    """Run an incremental Recoll update if enabled.

    Uses recollindex -m to add new/changed docs. Applies a soft time cap: if the
    process exceeds RECOLL_MAX_SECONDS it will be terminated (best effort).
    """
    if not ENABLE_RECOLL:
        logger.info("Recoll disabled via config; skipping.")
        return
    if not shutil.which("recollindex"):
        logger.warning("recollindex executable not found; skipping Recoll update.")
        return
    recoll_conf = RECOLL_CONF_DIR
    if not os.path.isdir(recoll_conf):
        logger.warning(f"Recoll config dir '{recoll_conf}' missing; skipping Recoll update.")
        return
    logger.info("Recoll: starting incremental update (-m)...")
    start = time.time()
    # Build command with niceness if available
    cmd = ["recollindex", "-c", recoll_conf, "-m"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=lambda: os.nice(int(RECOLL_NICENESS)) if RECOLL_NICENESS.isdigit() else None)
        while True:
            if proc.poll() is not None:
                break
            if RECOLL_MAX_SECONDS > 0 and (time.time() - start) > RECOLL_MAX_SECONDS:
                logger.warning(f"Recoll: time limit {RECOLL_MAX_SECONDS}s exceeded; terminating.")
                try:
                    proc.send_signal(signal.SIGTERM)
                except Exception:
                    pass
                break
            time.sleep(0.5)
        stdout, stderr = proc.communicate(timeout=5)
        if stdout:
            logger.info("Recoll stdout: " + stdout.strip().split('\n')[-1])
        if stderr:
            logger.debug("Recoll stderr: " + stderr.strip().split('\n')[-1])
        rc = proc.returncode
        duration = time.time() - start
        if rc == 0:
            logger.info(f"Recoll: completed in {duration:.1f}s (rc=0).")
        else:
            logger.warning(f"Recoll: exited with code {rc} after {duration:.1f}s.")
    except FileNotFoundError:
        logger.warning("recollindex not installed; skipping.")
    except Exception:
        logger.exception("Recoll: unexpected failure.")

def incremental_rebuild_faiss(dry_run=False):
    """Incrementally update or build the FAISS index from OCR text files.

    Optimizations added:
      * Batch embedding (reduces per-call overhead & speeds up large updates).
      * Incremental flush: write index + id map after each batch for resilience.
      * Progress logging every LOG_EVERY files.
      * Memory friendly: do not hold all embeddings simultaneously.
    """
    start_time = time.time()
    logger.info("Starting index update cycle.")

    # Ensure DB directory exists early to avoid FAISS write failures
    try:
        os.makedirs(DB_DIR, exist_ok=True)
    except Exception:
        logger.exception(f"Failed to ensure DB directory exists at {DB_DIR}")

    # Step 1: Always try Recoll first (fast keyword availability)
    try:
        run_recoll_incremental()
    except Exception:
        logger.exception("Recoll update step failed; continuing to FAISS.")

    if not ENABLE_FAISS:
        logger.info("FAISS disabled via config; ending cycle after Recoll phase.")
        return

    # Load existing index and map, or initialize new ones
    if os.path.exists(FAISS_INDEX_PATH) and os.path.exists(ID_MAP_PATH):
        try:
            faiss_index = faiss.read_index(FAISS_INDEX_PATH)
            with open(ID_MAP_PATH, 'r', encoding='utf-8') as f:
                id_to_filepath_map = json.load(f)
            if not isinstance(id_to_filepath_map, list):  # safety
                logger.warning("ID map was not a list; reinitializing.")
                id_to_filepath_map = []
            logger.info(f"Loaded existing index with {faiss_index.ntotal} vectors and ID map size {len(id_to_filepath_map)}.")
        except Exception:
            logger.exception("Failed loading existing index; starting fresh.")
            faiss_index = faiss.IndexIDMap(faiss.IndexFlatL2(768))
            id_to_filepath_map = []
    else:
        logger.info("No existing index found. Initializing a new one.")
        faiss_index = faiss.IndexIDMap(faiss.IndexFlatL2(768))
        id_to_filepath_map = []

    unprocessed_files = get_unprocessed_files(id_to_filepath_map)
    total_unfiltered = len(unprocessed_files)
    # Apply per-cycle cap if configured
    if FAISS_MAX_FILES_PER_CYCLE and total_unfiltered > FAISS_MAX_FILES_PER_CYCLE:
        unprocessed_files = unprocessed_files[:FAISS_MAX_FILES_PER_CYCLE]
        logger.info(f"Applying FAISS_MAX_FILES_PER_CYCLE cap: {len(unprocessed_files)} of {total_unfiltered} will be embedded.")
    total_new = len(unprocessed_files)
    if total_new == 0:
        logger.info("No new files to process. Index is up to date.")
        return

    logger.info(f"Discovered {total_new} unprocessed text files in {OCR_TEXT_DIR} (pre-cap {total_unfiltered}).")
    if dry_run:
        logger.info("[DRY RUN] Exiting before processing.")
        return

    # Initialize embedding model once
    logger.info(f"Loading sentence embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    processed = 0  # number of non-empty files encountered (queued)
    added_files_count = 0  # number of files actually flushed into the index
    time_budget_start = time.time()
    batch_texts = []
    batch_paths = []

    def flush_batch(texts, paths):
        nonlocal faiss_index, id_to_filepath_map
        nonlocal added_files_count
        if not texts:
            return
        try:
            embeddings = model.encode(texts, batch_size=min(EMBED_BATCH_SIZE, len(texts)))
            vectors = np.array(embeddings).astype('float32')
            start_id = len(id_to_filepath_map)
            new_ids = np.arange(start_id, start_id + len(paths))
            try:
                faiss_index.add_with_ids(vectors, new_ids)  # type: ignore
            except TypeError:
                try:
                    faiss_index.add_with_ids(vectors, ids=new_ids)  # type: ignore
                except TypeError:
                    logger.warning("Falling back to add() without IDs; ID mapping may become inconsistent.")
                    faiss_index.add(vectors)  # type: ignore
            id_to_filepath_map.extend(paths)
            # Persist after each batch for durability
            try:
                os.makedirs(os.path.dirname(FAISS_INDEX_PATH), exist_ok=True)
            except Exception:
                logger.exception(f"Could not create directory for FAISS index: {FAISS_INDEX_PATH}")
            faiss.write_index(faiss_index, FAISS_INDEX_PATH)
            with open(ID_MAP_PATH, 'w', encoding='utf-8') as f:
                json.dump(id_to_filepath_map, f)
            added_files_count += len(paths)
            logger.info(f"Flushed batch of {len(paths)} files. Total indexed now {len(id_to_filepath_map)}.")
        except Exception:
            logger.exception("Failed to flush a batch; continuing with next batch.")

    for file_path in unprocessed_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if not content.strip():
                continue
            batch_texts.append(content)
            batch_paths.append(file_path)
            processed += 1
            if len(batch_texts) >= BATCH_SIZE:
                flush_batch(batch_texts, batch_paths)
                batch_texts.clear()
                batch_paths.clear()
            if processed % LOG_EVERY == 0:
                elapsed = time.time() - start_time
                logger.info(f"Progress: {processed}/{total_new} ({processed/total_new*100:.1f}%) in {elapsed:.1f}s")
            if FAISS_MAX_SECONDS and (time.time() - time_budget_start) > FAISS_MAX_SECONDS:
                logger.warning(f"FAISS time budget {FAISS_MAX_SECONDS}s exceeded; stopping early at {processed} files.")
                break
        except Exception:
            logger.exception(f"Failed to process file: {file_path}")

    # Flush any residual batch
    flush_batch(batch_texts, batch_paths)

    elapsed = time.time() - start_time
    if added_files_count != total_new:
        logger.info(f"Index update cycle completed. Added {added_files_count} non-empty files (out of {total_new} discovered) in {elapsed:.1f} seconds. Index size: {faiss_index.ntotal} vectors.")
    else:
        logger.info(f"Index update cycle completed. Added {added_files_count} files in {elapsed:.1f} seconds. Index size: {faiss_index.ntotal} vectors.")

if __name__ == "__main__":
    incremental_rebuild_faiss()
