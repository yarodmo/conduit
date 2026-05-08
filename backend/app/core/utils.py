"""
Conduit Backend — Core Utilities
Dialect-agnostic datetime helpers for SQLite/PostgreSQL compatibility.

Problem: SQLite returns naive datetimes (no timezone info).
         PostgreSQL returns tz-aware datetimes (UTC).
         Comparing naive vs aware raises TypeError at runtime.

Solution: ensure_utc() normalizes any datetime to UTC-aware before comparison.
          Call it whenever reading a datetime value FROM the database.

Bliss Systems LLC — APEX Standard
"""

from datetime import datetime, timezone


def ensure_utc(dt: datetime | None) -> datetime | None:
    """
    Ensure a datetime is timezone-aware (UTC).

    - If dt is None, returns None.
    - If dt is already aware, returns it unchanged.
    - If dt is naive (e.g. from SQLite), assumes UTC and attaches tzinfo.

    Usage:
        remaining = (ensure_utc(session.expires_at) - datetime.now(timezone.utc)).total_seconds()
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
