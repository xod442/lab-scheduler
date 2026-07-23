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
SCHEDULER_CREATE_URL = os.getenv("SCHEDULER_CREATE_URL", "https://schedulerapi.edutl.hpe.com/v1/reservations/create")
# Join-an-existing-reservation ("add a seat") endpoint. {resId} is substituted into
# the path; the body is FORM-encoded (matches single_seat.py: requests.post(url, data=...)).
SCHEDULER_JOIN_URL = os.getenv("SCHEDULER_JOIN_URL", "https://schedulerapi.edutl.hpe.com/v1/reservations/{resId}/add-seat/")
SCHEDULER_API_KEY = os.getenv("SCHEDULER_API_KEY", "")

_SAMPLE = pathlib.Path(__file__).parent / "sample_items.json"
_CATALOG = pathlib.Path(__file__).parent / "course_catalog.json"


def load_catalog() -> list:
    """Course-code -> title 'decoder ring'. Returns [{code, title}, ...]."""
    try:
        return json.loads(_CATALOG.read_text())
    except (FileNotFoundError, ValueError):
        return []


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


def create_reservation(payload: dict, api_key: str | None = None) -> dict:
    """POST a reservation to the scheduler's create endpoint.

    payload keys: userId, courseCode, startDateTime, endDateTime, tz, numStudents, notes
    Returns a normalized result: {ok, simulated, status_code, message, raw}.
    """
    key = api_key if api_key is not None else SCHEDULER_API_KEY
    if not key:
        # Simulate mode — no live call; echo back a success so the flow is testable.
        return {"ok": True, "simulated": True, "status_code": 200,
                "message": "Reservation created (simulated — no API key configured).",
                "raw": {"submitted": payload}}
    headers = {"Content-Type": "application/json", "X-API-Key": key}
    try:
        resp = httpx.post(SCHEDULER_CREATE_URL, headers=headers, json=payload, timeout=30)
    except httpx.HTTPError as exc:
        return {"ok": False, "simulated": False, "status_code": 0,
                "message": f"Could not reach the scheduler ({type(exc).__name__}).", "raw": {}}
    try:
        body = resp.json()
    except ValueError:
        body = {"raw_text": resp.text}
    message = body.get("message", "") if isinstance(body, dict) else ""
    return {"ok": resp.is_success, "simulated": False, "status_code": resp.status_code,
            "message": message, "raw": body}


# ── Location → IANA time zone derivation ──────────────────────────────────────
# Scheduled sessions come back with a free-text location ("City, ST, Country")
# but no tz, so we resolve it: city keyword → US state / CA province → country.
_CITY_TZ = {
    "riyadh": "Asia/Riyadh", "jeddah": "Asia/Riyadh", "dammam": "Asia/Riyadh",
    "singapore": "Asia/Singapore", "espoo": "Europe/Helsinki", "helsinki": "Europe/Helsinki",
    "los angeles": "America/Los_Angeles", "cupertino": "America/Los_Angeles",
    "san jose": "America/Los_Angeles", "san francisco": "America/Los_Angeles",
    "new york": "America/New_York", "phoenix": "America/Phoenix", "toronto": "America/Toronto",
    "edmonton": "America/Edmonton", "alpharetta": "America/New_York", "atlanta": "America/New_York",
    "eastern rail": "America/New_York", "london": "Europe/London", "paris": "Europe/Paris",
    "dubai": "Asia/Dubai", "tokyo": "Asia/Tokyo", "sydney": "Australia/Sydney",
    "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata", "mumbai": "Asia/Kolkata",
}
_US_STATE_TZ = {
    "CA": "America/Los_Angeles", "WA": "America/Los_Angeles", "OR": "America/Los_Angeles",
    "NV": "America/Los_Angeles", "AZ": "America/Phoenix", "CO": "America/Denver",
    "UT": "America/Denver", "NM": "America/Denver", "MT": "America/Denver",
    "TX": "America/Chicago", "IL": "America/Chicago", "MN": "America/Chicago",
    "WI": "America/Chicago", "MO": "America/Chicago", "IA": "America/Chicago",
    "NY": "America/New_York", "GA": "America/New_York", "FL": "America/New_York",
    "NC": "America/New_York", "SC": "America/New_York", "VA": "America/New_York",
    "MA": "America/New_York", "NJ": "America/New_York", "PA": "America/New_York",
    "OH": "America/New_York", "MI": "America/Detroit", "DC": "America/New_York",
    "MD": "America/New_York", "CT": "America/New_York", "TN": "America/Chicago",
    "HI": "Pacific/Honolulu", "AK": "America/Anchorage",
}
_CA_PROVINCE_TZ = {
    "ON": "America/Toronto", "QC": "America/Toronto", "AB": "America/Edmonton",
    "BC": "America/Vancouver", "MB": "America/Winnipeg", "SK": "America/Regina",
    "NS": "America/Halifax", "NB": "America/Moncton", "NL": "America/St_Johns",
}
_COUNTRY_TZ = {
    "usa": "America/New_York", "united states": "America/New_York",
    "canada": "America/Toronto", "saudi arabia": "Asia/Riyadh", "singapore": "Asia/Singapore",
    "finland": "Europe/Helsinki", "united kingdom": "Europe/London", "uk": "Europe/London",
    "france": "Europe/Paris", "germany": "Europe/Berlin", "india": "Asia/Kolkata",
    "japan": "Asia/Tokyo", "australia": "Australia/Sydney",
    "united arab emirates": "Asia/Dubai", "uae": "Asia/Dubai",
}
DEFAULT_TZ = "America/New_York"


def derive_timezone(location: str) -> tuple[str, bool]:
    """Best-effort IANA tz from a free-text location. Returns (tz, confident)."""
    loc = (location or "").strip().lower()
    if not loc:
        return DEFAULT_TZ, False
    for city, tz in _CITY_TZ.items():           # 1) known city
        if city in loc:
            return tz, True
    parts = [p.strip().strip(".").upper() for p in loc.split(",")]
    country = parts[-1].lower() if parts else ""
    if country in ("usa", "united states", "us"):
        for p in parts:                          # 2) US state code
            if p in _US_STATE_TZ:
                return _US_STATE_TZ[p], True
    if "canada" in country:
        for p in parts:                          # 3) CA province code
            if p in _CA_PROVINCE_TZ:
                return _CA_PROVINCE_TZ[p], True
    if country in _COUNTRY_TZ:                   # 4) country
        return _COUNTRY_TZ[country], country not in ("usa", "united states", "canada")
    return DEFAULT_TZ, False                      # 5) fallback (flag as a guess)


def join_reservation(res_id: str, data: dict, api_key: str | None = None) -> dict:
    """Add a student to an EXISTING reservation.

    Passes two things to the scheduler, as its join script expects:
      resId  — the existing reservation's id
      data   — {userId, comment, seats}
    Returns a normalized result: {ok, simulated, status_code, message, raw}.
    """
    key = api_key if api_key is not None else SCHEDULER_API_KEY
    if not key:
        return {"ok": True, "simulated": True, "status_code": 200,
                "message": "Joined workshop (simulated — no API key configured).",
                "raw": {"resId": res_id, "data": data}}
    headers = {"X-API-Key": key}
    url = SCHEDULER_JOIN_URL
    if "{resid}" in url.lower():
        url = url.replace("{resId}", str(res_id)).replace("{resid}", str(res_id))
        form = {k: str(v) for k, v in data.items()}
    else:
        form = {"resId": str(res_id), **{k: str(v) for k, v in data.items()}}
    try:
        # Form-encoded (application/x-www-form-urlencoded), matching single_seat.py.
        resp = httpx.post(url, headers=headers, data=form, timeout=30)
    except httpx.HTTPError as exc:
        return {"ok": False, "simulated": False, "status_code": 0,
                "message": f"Could not reach the scheduler ({type(exc).__name__}).", "raw": {}}
    try:
        b = resp.json()
    except ValueError:
        b = {"raw_text": resp.text}
    message = b.get("message", "") if isinstance(b, dict) else ""
    return {"ok": resp.is_success, "simulated": False, "status_code": resp.status_code,
            "message": message, "raw": b}


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
            loc = r.get("location", "")
            tz, tz_ok = derive_timezone(loc)
            sessions.append({
                "tz": tz,
                "tz_confident": tz_ok,
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
                "location": loc,
                "status": r.get("status", ""),
            })
    sessions.sort(key=lambda s: s["start"])
    return sessions


def build_calendar(payload: dict) -> dict:
    """Turn the payload into a weeks x days calendar grid for the template."""
    sessions = parse_sessions(payload)
    if not sessions:
        return {"weeks": [], "sessions": [], "session_count": 0, "range_label": ""}

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
