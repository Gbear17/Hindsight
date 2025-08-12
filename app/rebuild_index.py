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

import config
from utils import setup_logger

logger = setup_logger("HindsightRebuildIndex")

# --- Load the open-source embedding model ---
try:
    logger.info(f"Loading open-source embedding model: {config.EMBEDDING_MODEL}...")
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
    logger.info("Model loaded successfully.")
except Exception as e:
    logger.critical(f"Failed to load SentenceTransformer model. Error: {e}")
    embedding_model = None

def incremental_rebuild_faiss():
    if not embedding_model:
        logger.error("Cannot rebuild index because the embedding model failed to load.")
        return

    logger.info("Starting FAISS index update cycle.")
    os.makedirs(config.INDEX_DIR, exist_ok=True)

    if os.path.exists(config.FAISS_INDEX_PATH):
        try:
            index = faiss.read_index(config.FAISS_INDEX_PATH)
            with open(config.ID_MAP_PATH, 'r', encoding='utf-8') as f:
                id_to_filepath_map = json.load(f)
            logger.info(f"Loaded existing FAISS index with {index.ntotal} items.")
        except Exception:
            logger.exception("Failed to load existing FAISS index or map. Creating new ones.")
            index = faiss.IndexFlatIP(config.EMBEDDING_SIZE)
            id_to_filepath_map = []
    else:
        index = faiss.IndexFlatIP(config.EMBEDDING_SIZE)
        id_to_filepath_map = []
        logger.info("No existing index found. Creating a new one.")

    all_files = set(glob.glob(os.path.join(config.OCR_TEXT_DIR, "*.txt")))
    processed_files = set(id_to_filepath_map)
    new_files_to_process = sorted(list(all_files - processed_files))

    if not new_files_to_process:
        logger.info("No new files to index. Index is up to date.")
        return

    logger.info(f"Found {len(new_files_to_process)} new file(s) to index.")

    new_embeddings = []
    new_filepaths = []
    for i, file_path in enumerate(new_files_to_process):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
                if not text.strip():
                    continue

            # Generate embedding using the local open-source model
            embedding = embedding_model.encode(text)

            new_embeddings.append(embedding)
            new_filepaths.append(file_path)

        except Exception:
            logger.exception(f"Failed to process and embed {file_path}. Skipping file.")
        
        # We can use a smaller sleep time as this is a local process
        time.sleep(0.05)

    if new_embeddings:
        try:
            embeddings_array = np.array(new_embeddings).astype('float32')
            index.add(embeddings_array)
            id_to_filepath_map.extend(new_filepaths)

            faiss.write_index(index, config.FAISS_INDEX_PATH)
            with open(config.ID_MAP_PATH, 'w', encoding='utf-8') as f:
                json.dump(id_to_filepath_map, f)
            logger.info(f"Successfully added {len(new_embeddings)} new items. Index now contains {index.ntotal} total items.")
        except Exception:
            logger.exception("A critical error occurred while saving the updated FAISS index or map file.")

if __name__ == "__main__":
    incremental_rebuild_faiss()
