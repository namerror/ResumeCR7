# 018. Local Generation Config API

Date: 2026-07-26

## Status

Accepted

## Context

ResumeCR7 now has a local React workbench for resume evidence and generation
actions, but generation settings still lived only in
`user/resume_generation/config.yaml`. Users needed a safer local UI for common
settings and OpenAI API setup without hiding or overwriting advanced YAML
settings they may edit manually.

## Decision

Expose a file-backed `/resume-generation/config` API for local generation
configuration.

- The backend reads and validates `user/resume_generation/config.yaml`, fills
  missing default keys for new or old installs, and writes changes atomically.
- The frontend exposes only selected fields while preserving all hidden YAML
  fields during updates.
- The OpenAI API key may be stored in `openai.api_key`, but GET responses never
  return the secret.
- API-key updates require HTTPS or a local loopback request.
- Environment `OPENAI_API_KEY` remains the highest-precedence key source; the
  YAML key is a fallback for local setup.

## Consequences

### Positive

- New users can configure the local app without hand-editing YAML.
- Advanced users can continue editing hidden `config.yaml` settings directly.
- Existing partial config files are upgraded with defaults without replacing
  user-provided values.
- Secret handling avoids echoing the stored key through the frontend API.

### Negative

- YAML storage is still local file persistence, not a multi-user secret store.
- The frontend intentionally exposes only a subset of the full config schema.

### Neutral

- No database, auth system, async run lifecycle, or remote config service is
  introduced.
- Existing resume evidence CRUD and resume generation facade routes remain
  unchanged.

## Alternatives Considered

- Store the key only in environment variables: rejected because the requested
  setup flow needs to work from the local frontend.
- Return the saved key to populate the password field: rejected because the UI
  only needs configured/not-configured state.
- Add a separate config store: rejected because YAML is already the local
  source of truth for generation settings.
