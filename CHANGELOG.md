# Changelog

All notable changes to E-Display are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions are **not** tagged by hand. Every push to `main` runs
`.github/workflows/docker-build.yml`, which derives the next tag from the
conventional-commit prefixes in the pushed commits. See
[.agents/workflows/versioning.md](.agents/workflows/versioning.md).

## [Unreleased]

### Added

- `CHANGELOG.md` — this file.
- `CLAUDE.md` — project instructions for Claude Code.
- CI builds the backend Docker image on every pull request, so a base-image or
  dependency bump that no longer builds is caught before it is auto-merged.

### Fixed

- The backend image builds again. The Python 3.14 base image had broken every
  backend release since August (Pillow 10.2.0 has no 3.14 wheel); the image is
  back on Python 3.11, the version CI tests and the lockfile targets.
- Departures around midnight: times are now computed from HSL's service day,
  so after-midnight trips no longer vanish, sort last, or show as "24:10".
- Saving settings in the web UI no longer reverts layout-editor changes made
  since the page was opened.
- Stop search in the web UI now calls the backend the page talks to, instead
  of `localhost:8000` on the viewer's own machine.
- Stop search handles addresses containing `&` or `#`, and weather locations
  are URL-encoded.
- The layout editor picks up a changed "Max Items" without a page reload, and
  its row boxes line up with the rendered rows (they sat 5 px high).
- A `config.json` with a partial `display` block loads instead of crashing,
  and `HSL_API_KEY` is honoured even when there is no `config.json` yet.
- `weather.cache_minutes` changes take effect without restarting the display.
- The weather overlay uses the most recent forecast step when all steps are in
  the past, and keeps the last good reading when FMI returns nothing usable.
- The burn-in clear runs once a night, just before a redraw, instead of on
  every refresh for the whole 03:00 hour, which left the panel blank.
- The same HSL alert is no longer repeated for every departure of a route.
- `python api.py` starts the dev server instead of exiting at once
  (uvicorn's reload mode needs the app as an import string).
- The API no longer blocks every request while one preview or HSL call is in
  flight, and concurrent previews can't read each other's half-written image.
- The display loop no longer reads its frame back from `pic/`, which the API
  container's previews also write to.
- The display finds its Waveshare driver when started from any directory.

### Removed

- `GET /api/layout/elements`: unused by the web UI, and its geometry had
  drifted from what the renderer draws.
- Render outputs (`preview.png`, `pic/*.png`) and unused boilerplate images
  are no longer tracked.

## [v0.0.3] — 2026-07-19

Merged via [PR #1 — fix: address config, networking, and robustness issues](https://github.com/Saavuori/E-Display/pull/1)
(`e05abfe`).

### Added

- Hardware- and network-free pytest suite covering config round-tripping, HSL
  response parsing, and FMI weather parsing (`tests/`, `pytest.ini`,
  `requirements-dev.txt`). The e-ink driver falls back to a mock automatically,
  so `pytest` runs on any machine.
- `epd_driver` config key: the Waveshare driver module is now selectable instead
  of hardcoded to `epd7in5b_V2`, and is resolved dynamically at runtime with a
  mock fallback (`load_epd_driver()` in [display.py](display.py)).
- Testing section in the README.

### Fixed

- `docker-compose.yml` now injects `HSL_API_KEY` from `.env` into the `backend`
  and `display` services. The `.env` file was documented but never passed
  through to the containers.
- Invalid CORS configuration in [api.py](api.py): `allow_credentials=True`
  cannot be combined with a wildcard origin.
- Request timeouts added to the HSL departure fetch and the stop-search call, so
  a hung HTTP request can no longer freeze the display refresh loop
  (`HSLClient.REQUEST_TIMEOUT = 15`).

### Changed

- Removed duplicate imports, duplicate dict keys, and stale comments; aligned
  `LayoutConfig.from_dict` defaults with the dataclass field defaults so a
  partial `layout` block in `config.json` yields the same values as an absent one.

## [v0.0.2] — 2026-06-14

### Fixed

- Weather elements are now visible and editable in the web UI layout editor
  (`weather_x` / `weather_y` were missing from the element list).

### Added

- Disk caching for FMI weather responses, so a restart does not immediately
  re-hit the FMI endpoint.

## [v0.0.1] — 2026-06-14

First automatically tagged release. Covers all work from the initial commit
through the introduction of the versioning pipeline.

### Added

- **FMI weather overlay** ([weather.py](weather.py)): current temperature for a
  configurable Finnish location, fetched from the FMI open-data service, with an
  in-process cache (`weather.cache_minutes`) and a `weather.enabled` toggle.
- **Weather condition icon** drawn beside the clock — hand-rolled PIL vector
  glyphs (clear, partly cloudy, cloudy, rain, snow, sleet, thunder, fog) that
  stay legible in the display's 1-bit black/red palette.
- **Conventional-commit auto-versioning**: push to `main` → semver tag bump →
  multi-arch (`linux/arm64`) Docker build → push to GHCR → Watchtower pulls on
  the Pi within ~5 minutes.
- **Version surfacing**: `VERSION`, `BUILD_DATE` and `GIT_SHA` build-args become
  `APP_*` env vars, are served by `GET /api/version`, and are rendered in the
  web UI footer with links to the release tag and commit.
- Real-time HSL departure board for the Waveshare 7.5" B/W/R e-paper display,
  with stop search, per-stop route filtering, disruption alerts and a clock.
- Next.js web UI: dashboard, stop search, configuration form, drag/slider layout
  editor and a live display preview.
- Force Refresh button in the web UI, backed by a trigger file the display loop
  polls once a second (`triggers/refresh`).
- Docker Compose deployment (`backend`, `frontend`, `display`, `watchtower`)
  with host timezone mounted into the containers.

### Fixed

- Late buses (delay > 60 s) are highlighted in red on the display.
- Config hot-reloading in the display loop — layout, fonts, stops and API
  credentials are re-read on every cycle without a restart.
- Removed the infinite connection-retry loop that could wedge the display.
- Next.js rewrites proxy `/api/*` to the `backend` container, removing the
  hardcoded LAN IP from the frontend.
- `triggers` is a directory rather than a file, so the Docker volume mount no
  longer raises `IsADirectoryError`.
- Python output unbuffered and flushed, so container logs appear in real time.
- Backend starts without GPIO/SPI privileges: a `RuntimeError` from the hardware
  driver import falls through to the mock driver.
- `config.json` is read as `utf-8-sig` so a BOM-prefixed file loads.

[Unreleased]: https://github.com/Saavuori/E-Display/compare/v0.0.3...HEAD
[v0.0.3]: https://github.com/Saavuori/E-Display/compare/v0.0.2...v0.0.3
[v0.0.2]: https://github.com/Saavuori/E-Display/compare/v0.0.1...v0.0.2
[v0.0.1]: https://github.com/Saavuori/E-Display/releases/tag/v0.0.1
