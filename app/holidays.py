"""Statutory holidays on which collection contact stops (POL-COLL-001 §5.1), for any year.

The rule set reproduces the national holidays flagged in contact_history.stat_holiday_flag
(2017-2026): fixed dates are not moved for weekends. config/statutory_holidays.csv can add
dates (for example a provincial holiday or a one-off closure).
"""
import csv
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _easter(year):
    """Meeus/Jones/Butcher Gregorian algorithm."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def national(year):
    victoria = date(year, 5, 24) - timedelta(days=date(year, 5, 24).weekday())  # Monday on or before 24 May
    days = {
        date(year, 1, 1): "New Year's Day",
        _nth_weekday(year, 2, 0, 3): 'Family Day',
        _easter(year) - timedelta(days=2): 'Good Friday',
        victoria: 'Victoria Day',
        date(year, 7, 1): 'Canada Day',
        _nth_weekday(year, 8, 0, 1): 'Civic Holiday',
        _nth_weekday(year, 9, 0, 1): 'Labour Day',
        _nth_weekday(year, 10, 0, 2): 'Thanksgiving Day',
        date(year, 12, 25): 'Christmas Day',
        date(year, 12, 26): 'Boxing Day',
    }
    if year >= 2021:
        days[date(year, 9, 30)] = 'National Day for Truth and Reconciliation'
    return days


@lru_cache(maxsize=1)
def _extra():
    path = ROOT / 'config/statutory_holidays.csv'
    if not path.exists():
        return {}
    with path.open(encoding='utf-8') as f:
        return {date.fromisoformat(r['date']): r['name'] for r in csv.DictReader(f) if r.get('date')}


def between(start, end):
    """Holidays from start to end inclusive, as {date: name}."""
    found = {}
    for year in range(start.year, end.year + 1):
        found.update(national(year))
    found.update(_extra())
    return {d: n for d, n in found.items() if start <= d <= end}
