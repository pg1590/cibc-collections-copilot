"""Local paths and snapshot shared by build and serving."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.getenv("COPILOT_DATASET", ROOT / "data/maple_collections_release")).resolve()
DB = Path(os.getenv("COPILOT_DB", ROOT / "data/copilot.duckdb")).resolve()
STATE = Path(os.getenv("COPILOT_STATE", ROOT / "data/reviews.sqlite3")).resolve()
QUALITY = ROOT / "data/quality.json"
MODEL = ROOT / "data/hardship-model.joblib"
MODEL_REPORT = ROOT / "data/model-report.json"
SNAPSHOT = "2026-09-28"
