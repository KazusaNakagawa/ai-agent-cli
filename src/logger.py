import logging
from datetime import datetime, timedelta
from pathlib import Path

_LOG_RETENTION_DAYS = 7


def _purge_old_logs(log_dir: Path) -> None:
    cutoff = datetime.now() - timedelta(days=_LOG_RETENTION_DAYS)
    for path in log_dir.glob("*-app.log"):
        try:
            file_date = datetime.strptime(path.stem.replace("-app", ""), "%Y%m%d")
            if file_date < cutoff:
                path.unlink()
        except (ValueError, OSError):
            pass


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    log_dir = Path(__file__).parents[1] / "log"
    log_dir.mkdir(exist_ok=True)
    _purge_old_logs(log_dir)

    log_file = log_dir / f"{datetime.now().strftime('%Y%m%d')}-app.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger
