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
from logging.handlers import WatchedFileHandler
import config

# --- MODIFIED: Use WatchedFileHandler for process-safe logging ---
class UnbufferedWatchedFileHandler(WatchedFileHandler):
    """
    A custom WatchedFileHandler that flushes the stream after every emit.
    This is process-safe and ensures log messages are written to disk immediately,
    which is crucial for real-time monitoring by other processes like the manager.
    """
    def emit(self, record):
        super().emit(record)
        # Flush the stream to ensure the log record is passed from the
        # application's buffer to the operating system.
        self.flush()
        # Force the operating system to write its buffer to disk immediately.
        # This is the key to eliminating the lag.
        if self.stream:
            os.fsync(self.stream.fileno())

def setup_logger(logger_name):
    """Configures and returns a logger."""
    os.makedirs(config.LOG_DIR, exist_ok=True)
    
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Add handler only if it hasn't been added before
    if not logger.handlers:
        # Use the correct, unbuffered, process-safe handler.
        handler = UnbufferedWatchedFileHandler(config.LOG_FILE)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)

    return logger
