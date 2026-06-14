---
description: how the automatic version tagging and deployment pipeline works
---

# Automatic Version Tagging

Every push to `main` triggers a GitHub Actions workflow that:
1. Bumps the semantic version tag based on conventional commit prefixes
2. Builds Docker images (linux/arm64) with the version injected via build-args
3. Pushes to `ghcr.io/saavuori/e-display/backend` and `ghcr.io/saavuori/e-display/web-ui`
4. Watchtower on the Raspberry Pi auto-pulls the new images within ~5 minutes

## Commit Message Rules

Use conventional commit prefixes — they control the version bump:

- `fix:` → patch bump (v0.0.1 → v0.0.2)
- `feat:` → minor bump (v0.0.2 → v0.1.0)
- `feat!:` or `BREAKING CHANGE:` → major bump (v0.1.0 → v1.0.0)
- anything else → patch bump

## Do NOT

- Manually create git tags — GitHub Actions does this
- Hardcode version strings anywhere — they are injected via build-args

## Key Files

- `.github/workflows/docker-build.yml` — CI/CD pipeline (tag → build → push)
- `Dockerfile` — accepts `VERSION`, `BUILD_DATE`, `GIT_SHA` build-args as `APP_*` env vars
- `api.py` — `GET /api/version` returns the injected version info
- `web-ui/components/Dashboard.tsx` — footer displays version fetched from `/api/version`

## How Version is Surfaced

At Docker build time CI passes:
```
VERSION=v1.2.3
BUILD_DATE=2026-06-14T18:00:00Z
GIT_SHA=abc1234...
```

These become `APP_VERSION`, `APP_BUILD_DATE`, `APP_GIT_SHA` environment variables.
`GET /api/version` returns them as JSON; the web UI footer displays them with links to
the GitHub release tag and commit.

## Checking the Current Version

```bash
git describe --tags --abbrev=0
```
