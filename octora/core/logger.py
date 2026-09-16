"""App logger: writes to rotating file AND the SQLite app_logs table (shown in Logs screen)."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import data_dir

_initialized = False


def get_logger(name: str = "octora") -> logging.Logger:
    global _initialized
    logger = logging.getLogger(name)
    if _initialized:
        return logger
    _initialized = True
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%H:%M:%S")
    logfile = Path(data_dir()) / "octora.log"
    fh = RotatingFileHandler(str(logfile), maxBytes=1_000_000, backupCount=3,
                             encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # DB handler (lazy import to avoid cycles)
    class DBHandler(logging.Handler):
        def emit(self, record):
            try:
                from .database import Database
                db = Database()
                db.add_log(record.levelname,
                           record.name.split(".")[-1],
                           record.getMessage())
            except Exception:
                pass

    dh = DBHandler()
    dh.setLevel(logging.INFO)
    logger.addHandler(dh)
    return logger
