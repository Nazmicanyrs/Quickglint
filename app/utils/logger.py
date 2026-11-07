"""Logging utility for Quickglint application."""

import logging
import os
import sys
from pathlib import Path


def get_log_dir() -> Path:
    """Return the application log directory path in user directory."""
    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base_dir = str(Path.home() / "Library" / "Logs")
    else:
        base_dir = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    
    log_dir = Path(base_dir) / "Quickglint" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger(name: str = "Quickglint", level: int = logging.INFO) -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(module)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # File handler
    try:
        log_file = get_log_dir() / "quickglint.log"
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except Exception as exc:
        print(f"Warning: Could not create file logger: {exc}", file=sys.stderr)

    return logger


logger = setup_logger()

