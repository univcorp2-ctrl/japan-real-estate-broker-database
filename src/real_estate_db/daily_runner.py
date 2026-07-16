from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "daily-run.log"


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def run(command: list[str]) -> None:
    logging.info("Running: %s", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    configure_logging()
    logging.info("Daily refresh started at %s", datetime.now().isoformat(timespec="seconds"))
    try:
        run([sys.executable, "-m", "real_estate_db.build_excel"])
        run([sys.executable, "-m", "pytest", "-q"])
    except subprocess.CalledProcessError as exc:
        logging.exception("Daily refresh failed with exit code %s", exc.returncode)
        return exc.returncode
    logging.info("Daily refresh completed successfully")
    return 0
