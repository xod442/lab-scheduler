# Lab Scheduler (lab-portal) — working notes for Claude

Public, no-login reservation portal over the vLab scheduler API. HPE Networking / TRIG.
Repo dir is `lab-portal`; GitHub repo is `xod442/lab-scheduler`.

## Stack & layout
- FastAPI (`app.py`) + `vlab_client.py` (API client + `build_calendar`) + Jinja2 + SQLite + Docker.
- Templates: welcome, schedule (calendar + day modal), reserve (join/create form), reserve_result, admin*.
- Vendored flatpickr in `static/vendor/` (HPE network blocks CDNs — do NOT switch to a CDN).
- Two flows off one calendar: **Join** (`/schedule`) and **New** (`/schedule?mode=new`); both
  open a day-detail modal. Join rows link to the join form; New continues to the create form.

## Config (env)
`SECRET_KEY`, `LABPORTAL_FERNET_KEY`, `COOKIE_SECURE`, `ROOT_PATH` (path prefix, must match
proxy, no trailing slash), `SCHEDULER_API_KEY` (blank = simulated sample data), `ADMIN_PATH`
(obscure shadow admin — **keep out of the README/docs**), `DEFAULT_TZ`, `OWN_DURATION_HOURS` (8).

## Local dev / verify
- No dedicated venv; reuse `/Users/rick/Projects/opal/venv` (has fastapi/jinja/uvicorn/etc.).
- Run: `COOKIE_SECURE=false uvicorn app:app --port 8088` (http locally). Docker maps 8088→8000.
- Cheap verification (default): Jinja parse + `py_compile`; hit routes with urllib for status.
  **Screenshots only when Rick asks** (token-heavy). To shoot the JS modal, inject an
  auto-`openDay()` on load and screenshot the file.

## Git
- Remote `origin` → github.com/xod442/lab-scheduler (branch `main`). **PUBLIC repo.**
- Commit only when Rick asks. Author `Rick Kauffman <rick@rickkauffman.com>`, trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Never stage** `.env`, `data/`, `*.db`, `secret.key`. Prefer explicit `git add <files>`.

## Gotchas
- README images load from `raw.githubusercontent.com` → blocked on HPE VPN; fine off-VPN. Not a repo bug.
- Login bounces to start with no error → suspect proxy/session policy, not the app.
