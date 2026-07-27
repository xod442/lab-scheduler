# Lab Scheduler — Production Deploy Punch List

## 0. Prerequisites (on the prod host)
- [ ] Docker + Docker Compose installed and running
- [ ] Git access to `github.com/xod442/lab-scheduler`
- [ ] The reverse proxy (e.g. `theedge`) can route to the container, over HTTPS
- [ ] The real scheduler **X-API-Key** in hand

## 1. Get the code
```bash
git clone https://github.com/xod442/lab-scheduler.git
cd lab-scheduler
```

## 2. Generate secrets
```bash
# session signing key
python3 -c "import secrets; print('SECRET_KEY='+secrets.token_urlsafe(48))"
# encryption key for the stored API key
python3 -c "from cryptography.fernet import Fernet; print('LABPORTAL_FERNET_KEY='+Fernet.generate_key().decode())"
```

## 3. Create `.env` (gitignored — never commit)
```
SECRET_KEY=<paste from step 2>
LABPORTAL_FERNET_KEY=<paste from step 2>
ADMIN_PATH=<obscure, e.g. ops-7f3a>     # the hidden admin route
COOKIE_SECURE=true                       # prod is HTTPS
# ROOT_PATH=/lab-scheduler               # ONLY if served under a path prefix by the proxy
# SCHEDULER_API_KEY=                      # leave blank; set it in the admin console instead
```
Defaults that are usually fine (override only if the scheduler differs):
`SCHEDULER_API_URL`, `SCHEDULER_CREATE_URL`, `SCHEDULER_JOIN_URL`, `OWN_DURATION_HOURS` (8), `DEFAULT_TZ`.

## 4. Persistence & backups (CRITICAL)
- [ ] `./data` is on **persistent storage** — it holds `labportal.db` (admin creds, settings,
      transaction log) **and** `secret.key` (the Fernet key)
- [ ] **Back up the Fernet key.** If `LABPORTAL_FERNET_KEY` is set in `.env`, the key lives there
      (independent of the volume). If left blank, it auto-generates to `data/secret.key` — losing
      that file makes the stored API key unrecoverable (you'd just re-enter it)
- [ ] Include `./data` in whatever backup routine the box uses

## 5. Reverse proxy
- [ ] Point the proxy at the container's host port (compose maps `8088 -> 8000`; change if needed)
- [ ] If served under a path prefix (like Opal's `/opal-central`), set **`ROOT_PATH`** to match and
      configure the proxy location block
- [ ] Terminate TLS at the proxy; the app cookie is already `Secure` + `HttpOnly` and named
      `labportal_session` (won't collide with the Opal cookies on the same host)

## 6. Build & run
```bash
docker compose up -d --build
docker compose ps           # container Up
docker compose logs --tail=30   # clean startup, no traceback
```

## 7. First-run setup
- [ ] Browse to `https://<host>[/ROOT_PATH]/<ADMIN_PATH>/login`
- [ ] Sign in **admin / admin** → it forces a password change → set a strong admin password
- [ ] Admin console → **Scheduler API** → paste the real **X-API-Key** → badge flips
      **SIMULATED → LIVE** (one key drives all calls: items, add-seat, create)

## 8. Smoke test
- [ ] Welcome page: HPE logo + "HPE Networking · TRIG" branding, two buttons
- [ ] **Join a Workshop** → calendar shows **real** sessions (not simulated) → pick one → join →
      confirmation; **Transaction log** shows `action=join`
- [ ] **Schedule Your Own Workshop** → course dropdown + flatpickr date/time picker (pop-up calendar
      must appear — confirms vendored assets load) → submit → confirmation; log shows `action=create`
- [ ] Admin → **Transaction log** lists both; **Download CSV** works
- [ ] Decoder-ring legend shows on the calendar

## 9. Prod hygiene
- [ ] Admin password changed from `admin/admin`
- [ ] `ADMIN_PATH` is obscure and not linked from any page
- [ ] `.env` is gitignored (confirm `git status` shows it untracked)
- [ ] `COOKIE_SECURE=true`

## 10. If login won't stick (bounces back to /login)
Same signature as the Opal incident — suspect the **edge/session policy first**, not the app.
The cookie is already `Secure` + named `labportal_session`. See the Opal prod-edge notes.

## Updating later
```bash
git pull && docker compose up -d --build     # --build is required to pick up code changes
```
Rotate the API key anytime in the admin console — it takes effect on the next request, no restart.
