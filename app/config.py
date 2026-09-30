"""Pfad- und Umgebungskonfiguration."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("SL_DATA_DIR", "data")).resolve()
DB_PATH = DATA_DIR / "softlabel.db"
ASSET_DIR = DATA_DIR / "assets"
EXPORT_DIR = DATA_DIR / "exports"
BASE_PATH = os.environ.get("SL_BASE_PATH", "").rstrip("/")

for _d in (DATA_DIR, ASSET_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
