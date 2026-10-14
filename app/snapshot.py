"""The extract's own as-of point, derived from the data instead of hard-coded.

snapshot_date: the extract date of the collections cases (collections_cases.extract_ts).
as_of_utc: the planning instant, just after the latest recorded contact, rounded up to
the hour. Contact rules count attempts up to this instant.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def detect(conn):
    extract, contact = conn.execute('''SELECT (SELECT max(extract_ts) FROM curated.collections_cases),
        (SELECT max(contact_ts_utc) FROM curated.contact_history)''').fetchone()
    if extract is None and contact is None:
        raise ValueError('Cannot detect the snapshot: collections_cases and contact_history are empty.')
    latest = max(t for t in (extract, contact) if t is not None)
    as_of = latest.replace(minute=0, second=0, microsecond=0) + (timedelta(hours=1) if (latest.minute, latest.second, latest.microsecond) != (0, 0, 0) else timedelta())
    return {'snapshot_date': (extract or contact).date().isoformat(), 'as_of_utc': as_of.replace(tzinfo=timezone.utc).isoformat(),
            'source': 'max(collections_cases.extract_ts); as_of = latest contact or extract, rounded up to the hour'}


def write(conn, path):
    found = detect(conn)
    Path(path).write_text(json.dumps(found, indent=2), encoding='utf-8')
    return found


def load(path, dataset_readme=None):
    """Snapshot file from the build; else the release README; else None."""
    try:
        found = json.loads(Path(path).read_text(encoding='utf-8'))
        date.fromisoformat(found['snapshot_date'])
        datetime.fromisoformat(found['as_of_utc'])
        return found
    except (OSError, ValueError, KeyError):
        pass
    try:
        text = Path(dataset_readme).read_text(encoding='utf-8')
        day = re.search(r'Snapshot date:\s*\**(\d{4}-\d{2}-\d{2})', text).group(1)
        start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(hours=7)
        return {'snapshot_date': day, 'as_of_utc': start.isoformat(), 'source': 'release README'}
    except (OSError, TypeError, AttributeError, ValueError):
        return None
