# Architectural Decision Records

This directory contains records of significant architectural and design decisions made during development.

## Format

Each ADR follows this structure:

```markdown
# [Number]. [Title]

Date: YYYY-MM-DD

## Status

[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]

## Context

What is the issue we're trying to solve? What constraints exist?

## Decision

What did we decide to do and why?

## Consequences

### Positive
- What improves?
- What does this enable?

### Negative
- What trade-offs are we accepting?
- What complexity does this add?

### Neutral
- What are we committing to?

## Alternatives Considered

What other options were evaluated and why were they rejected?
```

## Naming Convention

Files are named: `NNN-short-kebab-case-title.md`

- `001-embedding-cache-persistence.md`
- `002-baseline-filter-selection.md`
- `003-grounded-resume-evidence-pipeline.md`

## Current ADRs

- `001-embedding-cache-persistence.md`
- `002-baseline-filter-selection.md`
- `003-grounded-resume-evidence-pipeline.md`
- `004-user-resume-evidence-root-and-projects-milestone.md`
- `005-subsystem-package-organization.md`
- `006-scoped-selection-runtime-config.md`
- `007-modern-cli-selection-ui.md`
- `008-standalone-resume-evidence-and-generation-layers.md`
- `009-bullet-point-generation-api-boundary.md`
- `010-resume-generation-stage-cache.md`
- `011-modular-bullet-generation-cache-config.md`
- `012-fastapi-resume-service-transition.md`
- `013-app-owned-resume-evidence-crud-api.md`
- `014-canonical-link-evidence-enrichment-endpoint.md`
- `015-app-owned-resume-generation-api.md`
- `016-local-first-web-workbench-desktop-distribution.md`
- `017-desktop-packaging-and-release-workflow.md`
- `018-local-generation-config-api.md`
