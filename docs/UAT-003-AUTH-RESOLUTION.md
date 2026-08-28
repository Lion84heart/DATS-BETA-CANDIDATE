# UAT-003 — Authentication Failure: Root Cause Analysis & Resolution

**Date:** 2026-08-26
**Status:** RESOLVED — verified end-to-end
**Severity:** Release blocker (frontend authentication non-functional)

---

## 1. Root Cause

The login form had **no JavaScript event handler**. The `doLogin()` function existed in `app.js` and the backend `/auth/login` endpoint was fully functional, but nothing ever connected the two:

- `index.html` defines `<form id="login-form">` with `<button type="submit" id="login-btn">Sign In</button>`.
- `app.js`'s `DOMContentLoaded` initializer registered listeners for navigation, logout, demo toggle, paper-trading buttons, and tabs — **but never for `login-form`**.
- Result: clicking "Sign In" triggered the browser's **default form submission** (a GET navigation with query parameters), which reloaded the page. No `POST /auth/login` request was ever sent, no token was stored, and the app never transitioned out of the login screen.

The backend was exonerated by direct API testing: `POST /auth/login` with `{"username":"admin","password":"admin"}` returned HTTP 200 with a valid token before any frontend change.

A secondary gap was found during verification: `portfolio.py` and `positions.py` routers did not enforce authentication, despite the README documenting them as ANALYST+ protected endpoints. All other data routers (`orders`, `decisions`, `execution`, `config`) already called `get_current_user(request)`.

---

## 2. Files Modified

| File | Change |
|------|--------|
| `src/api/static/app.js` | Added `submit` listener on `#login-form` (preventDefault → `doLogin()` → `enterApp()` on success, inline error on failure, button loading state). Added `enterApp()` helper (hides login container, activates app container, sets user name/role/avatar, shows dashboard, starts refresh). Rewrote `doLogout()` to correctly toggle `.login-container` / `.app-container` visibility and stop the refresh timer (previously called non-existent `show('login')`). Session restore path now calls `enterApp()`. |
| `src/api/routers/portfolio.py` | Added `get_current_user(request)` enforcement to `GET /`, `GET /positions`, `GET /summary`. |
| `src/api/routers/positions.py` | Added `get_current_user(request)` enforcement to `GET /`, `GET /{symbol}`, `GET /summary/overview`; added `get_current_user` import. |

No changes were required to the authentication controller (`api/routers/auth.py`), authentication service (`api/auth.py`), password hashing, token generation, or user store — all verified working.

---

## 3. Why It Failed

A wiring omission during frontend assembly. The login UI, the `doLogin()` API call, the token storage logic, and the session-restore logic were all written — but the form's `submit` event was never bound to `doLogin()`. Because Demo Mode (`demo.html`) is a separate static page that requires no authentication, it masked the defect: everything visible in UAT passed except the one path that required the missing handler.

---

## 4. Why the Fix Is Correct

- **Minimal and surgical:** the only code added is the missing event binding and its success/failure handling. No backend changes to the auth path were needed because the backend was already correct (proven by direct API tests).
- **Uses existing primitives:** `doLogin()`, `localStorage` keys (`dats_token`, `dats_user`), `show()`, and `startRefresh()` are reused unchanged. `enterApp()` consolidates the previously duplicated "enter application" logic that was inline in the session-restore path.
- **Standard SPA pattern:** `preventDefault()` + async fetch + conditional view transition. Errors render into the existing `#login-error` element styled by the existing `.error-msg` CSS class.
- **Route protection matches documented RBAC:** `portfolio`/`positions` now enforce `get_current_user()` exactly as `orders`, `decisions`, `execution`, and `config` already did — identical pattern, no new dependency mechanism, no duplicated logic.
- **No demo bypass, no hacks:** Demo Mode remains a separate explicit static page; the authenticated path is a real end-to-end flow through `/auth/login`.
- **Note on user store:** users (including `admin`) live in the application-layer store in `api/auth.py`, populated at module import — admin is always available in every environment, including Docker with an empty PostgreSQL. No migration or bootstrap seeding is required for beta; database-backed users remain a documented production upgrade path.

---

## 5. Evidence

### Backend (direct API)

```
[1] POST /auth/login — all roles
  admin     : HTTP 200 role=admin
  operator  : HTTP 200 role=operator
  analyst   : HTTP 200 role=analyst
  viewer    : HTTP 200 role=viewer

[2] POST /auth/login — wrong password
  HTTP 401 {"detail":"Invalid username or password"}

[3] Route protection — NO token (all correctly rejected)
  /portfolio/ /portfolio/summary /portfolio/positions
  /positions/ /orders/ /decisions/ /config/   →  HTTP 401

[4] Route protection — WITH admin token
  All of the above                           →  HTTP 200

[5] GET /auth/me (Bearer)                    →  HTTP 200 username=admin role=admin

[6] Public endpoints unchanged
  /health/ /docs /static/index.html          →  HTTP 200
```

### Frontend (browser E2E)

1. Login page → enter `admin` / `admin` → click **Sign In** → Dashboard loads; sidebar shows `admin / ADMIN`, avatar `A`; live API data renders (AI Engine ONLINE, Market OPEN). Screenshot: `docs/uat-003-auth-success.png`.
2. Wrong password → red inline error "Invalid username or password"; remains on login screen.
3. **Logout** → returns to login screen; app container hidden; password field cleared.
4. Reload after login → session restored from `localStorage`; dashboard renders without re-login.

### Regression

Demo Mode, all static assets, Swagger, health checks (5/5 passing), and all 30 importable modules remain green.

---

*UAT-003 closed. Authentication flow is production-quality and fully verified.*
