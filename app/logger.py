import logging
import sys
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "data" / "vozmeet.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = logging.FileHandler(str(LOG_PATH), encoding="utf-8")
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler(sys.stderr)
_console_handler.setFormatter(_fmt)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_file_handler)
        logger.addHandler(_console_handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger
