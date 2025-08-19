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
import glob
import json
import numpy as np
import faiss
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

logger = setup_logger("HindsightRebuildIndex")

def get_unprocessed_files(id_map):
    """Finds all .txt files that are not yet in the ID map."""
    indexed_files = set(id_map)
    all_files = set(glob.glob(os.path.join(OCR_TEXT_DIR, "*.txt")))
    return sorted(list(all_files - indexed_files))

def incremental_rebuild_faiss(dry_run=False):
    """
    Incrementally updates the FAISS index and ID map with new text files.
    If the index does not exist, it performs a full build.
    """
    logger.info("Starting index update cycle.")
    start_time = time.time()

    # Load existing index and map, or initialize new ones
    if os.path.exists(FAISS_INDEX_PATH) and os.path.exists(ID_MAP_PATH):
        logger.info("Loading existing FAISS index and ID map.")
        faiss_index = faiss.read_index(FAISS_INDEX_PATH)
        with open(ID_MAP_PATH, 'r', encoding='utf-8') as f:
            id_to_filepath_map = json.load(f)
    else:
        logger.info("No existing index found. Initializing a new one.")
        # Using a standard 768 dimension for sentence-transformers models
        faiss_index = faiss.IndexFlatL2(768)
        faiss_index = faiss.IndexIDMap(faiss_index)
        id_to_filepath_map = []

    unprocessed_files = get_unprocessed_files(id_to_filepath_map)

    if not unprocessed_files:
        logger.info("No new files to process. Index is up to date.")
        return

    if dry_run:
        logger.info(f"[DRY RUN] Would process {len(unprocessed_files)} new files.")
        return

    logger.info(f"Loading sentence embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    logger.info(f"Processing {len(unprocessed_files)} new text files...")
    new_embeddings = []
    new_filepaths = []
    for file_path in unprocessed_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if content.strip():
                embedding = model.encode(content)
                new_embeddings.append(embedding)
                new_filepaths.append(file_path)
        except Exception:
            logger.exception(f"Failed to read or process file: {file_path}")

    if new_embeddings:
        logger.info(f"Adding {len(new_embeddings)} new vectors to the FAISS index.")
        new_indices = np.arange(len(id_to_filepath_map), len(id_to_filepath_map) + len(new_embeddings))
        faiss_index.add_with_ids(np.array(new_embeddings).astype('float32'), new_indices)
        id_to_filepath_map.extend(new_filepaths)

        # Save the updated index and map
        faiss.write_index(faiss_index, FAISS_INDEX_PATH)
        with open(ID_MAP_PATH, 'w', encoding='utf-8') as f:
            json.dump(id_to_filepath_map, f)
        logger.info("FAISS index and ID map have been updated and saved.")

    end_time = time.time()
    logger.info(f"Index update cycle completed in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    incremental_rebuild_faiss()
