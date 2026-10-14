"""Local paths and snapshot shared by build and serving."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import snapshot as _snapshot

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.getenv("COPILOT_DATASET", ROOT / "data/maple_collections_release")).resolve()
DB = Path(os.getenv("COPILOT_DB", ROOT / "data/copilot.duckdb")).resolve()
STATE = Path(os.getenv("COPILOT_STATE", ROOT / "data/reviews.sqlite3")).resolve()
QUALITY = ROOT / "data/quality.json"
MODEL = ROOT / "data/hardship-model.joblib"
MODEL_REPORT = ROOT / "data/model-report.json"
SNAPSHOT_FILE = DB.with_name("snapshot.json")

# The as-of point comes from the data (written by scripts/build_data.py), so a new extract
# needs no code change. COPILOT_SNAPSHOT=YYYY-MM-DD overrides it for what-if runs.
_found = _snapshot.load(SNAPSHOT_FILE, DATASET / "README.md") or {}
SNAPSHOT = os.getenv("COPILOT_SNAPSHOT") or _found.get("snapshot_date") or "2026-09-28"
AS_OF = (datetime.fromisoformat(_found["as_of_utc"]) if _found.get("snapshot_date") == SNAPSHOT and _found.get("as_of_utc")
         else datetime.fromisoformat(SNAPSHOT).replace(tzinfo=timezone.utc) + timedelta(hours=7))
