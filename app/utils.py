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

# /home/gcwyrick/hindsight/app/utils.py
# Utility functions for the Hindsight application.

import os
import logging
from logging.handlers import RotatingFileHandler
import config

def setup_logger(logger_name):
    """Configures and returns a logger."""
    os.makedirs(config.LOG_DIR, exist_ok=True)
    
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO) # Default to INFO, can be changed in specific scripts if needed
    logger.propagate = False

    # Add handler only if it hasn't been added before
    if not logger.handlers:
        # Create a rotating file handler
        handler = RotatingFileHandler(config.LOG_FILE, maxBytes=5*1024*1024, backupCount=5)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Also log to console
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)

    return logger
