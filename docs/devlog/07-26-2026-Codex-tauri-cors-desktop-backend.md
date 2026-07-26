### 2026-07-26 - Allow Tauri desktop backend CORS

**Agent:** Codex (GPT-5)

**Changes:**
- `app/main.py` - Added FastAPI CORS middleware for the Vite desktop development origins, preview origins, and expected Tauri packaged webview origins.
- `tests/test_health.py` - Added a regression test proving `/health` returns `Access-Control-Allow-Origin` for `http://127.0.0.1:5173`.

**Rationale:**
The Tauri shell starts the backend sidecar on a random loopback port, while desktop dev serves the frontend from Vite at `http://127.0.0.1:5173`. The backend was healthy, but browser access checks blocked direct sidecar calls because the FastAPI app did not emit CORS headers for that origin.

**Tests:**
- `test_health_allows_tauri_vite_origin`: validates the desktop dev origin receives the expected CORS response header from `/health`.

**Impact:**
The Tauri desktop dev app can call the sidecar backend directly instead of displaying the backend as offline due to browser CORS enforcement.
