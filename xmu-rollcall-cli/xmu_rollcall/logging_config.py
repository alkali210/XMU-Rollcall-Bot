import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

from .config import CONFIG_DIR, ensure_config_dir

LOG_FILE = CONFIG_DIR / "xmu_rollcall.log"

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text):
    """Remove ANSI color codes from text before it is written to log files."""
    return _ANSI_ESCAPE.sub("", str(text))


class PlainTextFormatter(logging.Formatter):
    def format(self, record):
        original_message = record.msg
        original_args = record.args
        try:
            record.msg = strip_ansi(record.getMessage())
            record.args = ()
            return super().format(record)
        finally:
            record.msg = original_message
            record.args = original_args


def setup_logging(
    log_file: Optional[Union[str, Path]] = None,
    level: int = logging.INFO,
) -> Path:
    """Configure application logging and return the log file path."""
    ensure_config_dir()
    log_path = Path(log_file) if log_file else LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_formatter = PlainTextFormatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(level)
    file_handler._xmu_rollcall_handler = True

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [
        handler
        for handler in root_logger.handlers
        if not getattr(handler, "_xmu_rollcall_handler", False)
    ]
    root_logger.addHandler(file_handler)

    return log_path
