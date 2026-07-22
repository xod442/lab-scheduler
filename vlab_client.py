"""
Client for the vLab scheduler API.

Real call (when SCHEDULER_API_KEY is set):
    GET https://schedulerapi.edutl.hpe.com/v1/items
    header: X-API-KEY: <key>

If no API key is configured, we fall back to the bundled sample_items.json so the
UI can be built and demoed without access to the live system.
"""
from __future__ import annotations

import json
import os
import pathlib
from datetime import date, datetime, timedelta

import httpx

SCHEDULER_API_URL = os.getenv("SCHEDULER_API_URL", "https://schedulerapi.edutl.hpe.com/v1/items")
SCHEDULER_API_KEY = os.getenv("SCHEDULER_API_KEY", "")

_SAMPLE = pathlib.Path(__file__).parent / "sample_items.json"


def fetch_items(api_key: str | None = None) -> dict:
    """Return the raw scheduler payload. Uses the live API when a key is given
    (the app passes the stored/encrypted key, falling back to env), otherwise the
    bundled sample (simulate mode)."""
    key = api_key if api_key is not None else SCHEDULER_API_KEY
    if not key:
        return json.loads(_SAMPLE.read_text())
    resp = httpx.get(SCHEDULER_API_URL, headers={"X-API-KEY": key}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _time_label(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _is_maintenance(code: str, title: str) -> bool:
    blob = f"{code} {title}".lower()
    return "maintenance" in blob


def parse_sessions(payload: dict) -> list[dict]:
    """Flatten the grouped payload into a flat list of bookable sessions."""
    sessions = []
    for code, info in (payload.get("data") or {}).items():
        for r in info.get("reservations", []):
            title = r.get("course_title") or code
            if _is_maintenance(code, title):
                continue
            try:
                start = datetime.strptime(r["start_datetime"], "%Y-%m-%d %H:%M")
            except (KeyError, ValueError):
                continue
            try:
                end = datetime.strptime(r["end_datetime"], "%Y-%m-%d %H:%M")
            except (KeyError, ValueError):
                end = None
            max_seats = int(r.get("max_seats") or 0)
            attendees = int(r.get("attendees") or 0)
            seats_left = max(0, max_seats - attendees)
            sessions.append({
                "reservation_id": r.get("reservation_id"),
                "code": code,
                "title": title,
                "date": start.date(),
                "start": start,
                "end": end,
                "time_label": _time_label(start),
                "end_label": _time_label(end) if end else "",
                "attendees": attendees,
                "max_seats": max_seats,
                "seats_left": seats_left,
                "is_full": seats_left == 0,
                "location": r.get("location", ""),
                "status": r.get("status", ""),
            })
    sessions.sort(key=lambda s: s["start"])
    return sessions


def build_calendar(payload: dict) -> dict:
    """Turn the payload into a weeks x days calendar grid for the template."""
    sessions = parse_sessions(payload)
    if not sessions:
        return {"weeks": [], "sessions": [], "session_count": 0}

    by_date: dict[date, list] = {}
    for s in sessions:
        by_date.setdefault(s["date"], []).append(s)

    min_d = min(by_date)
    max_d = max(by_date)
    start_monday = min_d - timedelta(days=min_d.weekday())
    end_sunday = max_d + timedelta(days=(6 - max_d.weekday()))
    today = date.today()

    weeks = []
    d = start_monday
    while d <= end_sunday:
        row = []
        for i in range(7):
            day = d + timedelta(days=i)
            row.append({
                "date": day,
                "day_num": day.day,
                "dow": day.strftime("%a"),
                "month": day.strftime("%b"),
                "is_today": day == today,
                "in_past": day < today,
                "is_weekend": day.weekday() >= 5,
                "sessions": by_date.get(day, []),
            })
        weeks.append(row)
        d += timedelta(days=7)

    # Human month/year range label for the header.
    if start_monday.year == end_sunday.year:
        if start_monday.month == end_sunday.month:
            range_label = start_monday.strftime("%B %Y")
        else:
            range_label = f"{start_monday.strftime('%B')} – {end_sunday.strftime('%B %Y')}"
    else:
        range_label = f"{start_monday.strftime('%B %Y')} – {end_sunday.strftime('%B %Y')}"

    return {"weeks": weeks, "sessions": sessions,
            "session_count": len(sessions), "range_label": range_label}
