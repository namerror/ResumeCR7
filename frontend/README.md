# ResumeCR7 Frontend

Local-first resume evidence workbench for the FastAPI backend.

## Development

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000` by default.
Set `VITE_BACKEND_PROXY_TARGET` to point the proxy at another local backend.

The app reads from `GET /resume-evidence`, stages changes in browser state, and
only calls write endpoints after `Apply` is clicked.

## Desktop

From this directory:

```bash
npm run sidecar:build
npm run desktop:dev
```

The Tauri shell launches the packaged FastAPI sidecar on an available loopback
port and exposes that URL to the frontend before rendering the workbench.

On Ubuntu, install the native Tauri WebView/GTK build dependencies before
running `desktop:dev` or `desktop:build`.
