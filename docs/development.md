# Development Guide

This guide covers the durable project workflow for contributors.

## Local Setup

Install backend dependencies:

```bash
uv sync --extra dev
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

Run the backend:

```bash
uv run resumecr7-api --reload
```

Run the frontend:

```bash
cd frontend
npm run dev
```

## Runtime Data

Local development writes runtime data under `user/` by default. That directory
is ignored by git because it contains personal evidence, generated artifacts,
caches, and logs.

Safe fictional starter data lives under `examples/`. To seed a local data
directory manually, copy the example file contents into the matching files under
`user/`, or let the backend bootstrap empty defaults and edit them through the
workbench.

## Tests

Run the backend test suite:

```bash
uv run pytest
```

Run focused release checks:

```bash
uv run pytest tests/test_packaging.py tests/test_runtime_data.py tests/test_release_validation.py -q
```

Run frontend checks:

```bash
cd frontend
npm test
npm run build
```

Run desktop Rust checks:

```bash
cd frontend/src-tauri
cargo test
cargo fmt --check
```

Validate Linux PDF dependency scripts:

```bash
bash -n packaging/linux/*.sh
bash packaging/linux/check-pdf-dependencies.sh
```

Validate the Windows PDF dependency checker syntax from PowerShell:

```powershell
$errors = $null
[System.Management.Automation.PSParser]::Tokenize((Get-Content packaging/windows/check-pdf-dependencies.ps1 -Raw), [ref]$errors) | Out-Null
if ($errors.Count -gt 0) { $errors | Format-List; exit 1 }
```

On Ubuntu/Debian, install the PDF runtime dependencies used by the released
AppImage:

```bash
bash packaging/linux/install-pdf-dependencies.sh
```

On Windows, install MiKTeX or TeX Live only when PDF rendering is needed, then
verify the toolchain:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/check-pdf-dependencies.ps1
```

Build platform desktop bundles from `frontend/`:

```bash
npm run desktop:build:linux
```

```powershell
npm run desktop:build:windows
```

Windows release signing requires GitHub secrets `WINDOWS_CERTIFICATE` containing
a base64-encoded PFX and `WINDOWS_CERTIFICATE_PASSWORD` containing its export
password. The Windows release workflow imports the certificate into
`Cert:\CurrentUser\My`, writes a temporary Tauri signing overlay, and builds the
signed NSIS installer on `windows-latest`.

## Documentation

- Update `README.md` for user-facing setup, product behavior, and contributor
  entrypoints.
- Update `docs/architecture-overview.md` when subsystem ownership, data flow, or
  runtime boundaries change.
- Update `docs/CHANGELOG.md` only for significant user-facing additions or
  breaking changes.

## Release Check

Validate release metadata with:

```bash
uv run python scripts/validate_release.py --tag vX.Y.Z
```

The validator checks the Python package version, Tauri version, Cargo package
version, and matching changelog section.
