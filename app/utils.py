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
"""Utility helpers for logging and configuration.

This module provides a small set of utilities for configuring logging that
integrates with file rotation (watched files) and for loading the
project-level configuration file.
"""


import os
import logging
from logging.handlers import WatchedFileHandler
import configparser

# --- New Config Parser Logic ---
config = configparser.ConfigParser()
config_path = os.path.expanduser('~/hindsight/hindsight.conf')
config.read(config_path)

# --- Fetching settings ---
LOG_FILE = config.get('System Paths', 'LOG_FILE')
LOG_DIR = os.path.dirname(LOG_FILE)

class UnbufferedWatchedFileHandler(WatchedFileHandler):
    """A custom WatchedFileHandler that flushes the stream after every emit.

    The handler ensures each log record is flushed and the underlying file
    descriptor is synced so logs remain durable across process restarts.
    """
    def emit(self, record):
        """Emit a log record and flush/sync the stream.

        Args:
            record: A ``logging.LogRecord`` instance.
        """
        super().emit(record)
        self.flush()
        if self.stream:
            os.fsync(self.stream.fileno())

def setup_logger(logger_name):
    """Configures and returns a logger."""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = UnbufferedWatchedFileHandler(LOG_FILE)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)

    return logger