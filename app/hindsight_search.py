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

import subprocess
import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

import config
from utils import setup_logger

logger = setup_logger("HindsightSearch")

# --- Globals ---
faiss_index = None
id_to_filepath_map = []
embedding_model = None
refiner_model = None

# --- Load the open-source embedding model ---
try:
    logger.info(f"Loading open-source embedding model: {config.EMBEDDING_MODEL}...")
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
    logger.info("Embedding model loaded successfully.")
except Exception as e:
    logger.critical(f"Failed to load SentenceTransformer model. Semantic search will be unavailable. Error: {e}")

# --- Configure the Google refiner model ---
try:
    # This uses the service account credentials we set up
    refiner_model = genai.GenerativeModel(config.REFINER_MODEL)
    logger.info("Successfully configured Gemini API for query refinement.")
except Exception as e:
    logger.critical(f"Failed to configure Gemini refiner model. Refinement will be unavailable. Error: {e}")

def init_search_components():
    global faiss_index, id_to_filepath_map
    if faiss_index is None and os.path.exists(config.FAISS_INDEX_PATH):
        try:
            logger.info("Loading FAISS index and file map into memory...")
            faiss_index = faiss.read_index(config.FAISS_INDEX_PATH)
            with open(config.ID_MAP_PATH, 'r', encoding='utf-8') as f:
                id_to_filepath_map = json.load(f)
            logger.info(f"FAISS index and file map loaded successfully ({faiss_index.ntotal} items).")
        except Exception:
            logger.exception("Failed to load FAISS index or file map. Semantic search will be unavailable.")

def get_recoll_matches(query):
    try:
        recoll_command = ["recoll", "-d", "-t", "-q", query]
        search_results_raw = subprocess.check_output(recoll_command).decode().strip()
        results = [{"source": "recoll", "content": res} for res in (search_results_raw.split('\n') if search_results_raw else [])]
        return results
    except subprocess.CalledProcessError:
        logger.error("Recoll query failed. Is Recoll installed and the index configured?")
        return []

def get_faiss_matches(query, num_results=5):
    if faiss_index is None or not id_to_filepath_map or not embedding_model:
        logger.warning("FAISS index or embedding model not loaded, skipping semantic search.")
        return []
    try:
        # Generate embedding using the local open-source model
        query_embedding = embedding_model.encode(query)

        query_vector = np.array([query_embedding]).astype('float32')
        distances, indices = faiss_index.search(query_vector, num_results)

        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx == -1: continue

            file_path = id_to_filepath_map[idx]
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            results.append({"source": "faiss (open-source)", "content": content, "distance": float(distances[0][i])})
        return results
    except Exception:
        logger.exception("FAISS/SentenceTransformer semantic search failed.")
        return []

def refine_query_with_gemini(query):
    if not refiner_model:
        logger.error("Refiner model not initialized, skipping refinement.")
        return query
    try:
        prompt = f"Analyze the following user search query to understand the user's intent. Refine the query by adding relevant synonyms, related concepts, or context-aware keywords that would improve a search across text documents. Do not hallucinate information. Respond with only the refined search query string.\nOriginal Query: \"{query}\"\nRefined Query:"
        response = refiner_model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        logger.exception("Gemini query refinement failed. Falling back to original query.")
        return query

def hybrid_search(query):
    refined_query = refine_query_with_gemini(query)
    recoll_results = get_recoll_matches(refined_query)
    faiss_results = get_faiss_matches(query)
    return recoll_results + faiss_results

init_search_components()
