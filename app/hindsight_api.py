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

# /home/gcwyrick/hindsight/app/hindsight_api.py (Refactored)
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# --- Imports from new modules ---
from hindsight_search import hybrid_search
from utils import setup_logger

# --- Setup logger ---
logger = setup_logger("HindsightAPI")

app = Flask(__name__)
CORS(app)

@app.route('/openapi.json', methods=['GET'])
def get_openapi_json():
    """Route to serve the OpenAPI specification file."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'openapi.json')

@app.route('/search', methods=['POST'])
def search_endpoint():
    """Route to handle search queries from Open WebUI."""
    try:
        data = request.get_json()
        query = data.get('query')
        
        logger.info(f"Received search request from {request.remote_addr} with query: '{query}'")

        if not query:
            logger.warning("Search request received with no query.")
            return jsonify({'error': 'No query provided'}), 400

        results = hybrid_search(query)
        logger.info(f"Returning {len(results)} results for query: '{query}'")
        return jsonify(results)

    except Exception as e:
        logger.exception("An unhandled exception occurred in the /search endpoint.")
        return jsonify({'error': 'An internal server error occurred.'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
