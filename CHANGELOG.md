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
- `CORS_ALLOW_ORIGINS` environment variable for pointing a browser at the API
  from an origin other than the packaged web UI.

### Security

- The HSL API key is no longer sent to the browser. `GET /api/config` returns an
  empty key plus whether one is configured and where it came from; the settings
  form leaves the stored key alone unless a new one is typed. Previously any page
  a machine on the network visited could read the key straight out of the API.
- A key supplied through `HSL_API_KEY` is no longer copied into `config.json` the
  first time settings are saved. It stays in `.env` where it was put, and still
  wins over the file at runtime.
- The API no longer accepts requests from any origin. Cross-origin access is
  limited to `localhost:3000` unless `CORS_ALLOW_ORIGINS` says otherwise; the
  packaged setup is unaffected because the web UI proxies `/api/*` internally.
- Addresses, weather place names, stop ids, and search radii are passed as
  request parameters and GraphQL variables rather than pasted into URLs and
  query documents, so a name containing a space or `&` can no longer break — or
  alter — the outgoing request.

### Fixed

- A stop with no realtime feed is shown from the timetable instead of vanishing
  from the screen.
- Departures after midnight show as `00:25` rather than `24:25`.
- A manual refresh whose trigger file cannot be deleted is now ignored for the
  rest of the interval. It used to re-fire every second, driving the panel
  through a continuous full refresh.
- One unreachable stop no longer blanks the whole timetable; the remaining stops
  render, and the connection error screen still appears when every stop fails.
- Weather readings fall back to the most recent past forecast entry when FMI
  returns nothing in the future, instead of the oldest one available.
- A `display` block in `config.json` that is missing a key — or carries an extra
  one — loads with defaults instead of taking down the display loop and every
  API endpoint. An unreadable `config.json` falls back to defaults too.
- Switching `epd_driver` or the weather cache duration in the web UI now takes
  effect on the next refresh cycle, like every other setting, instead of waiting
  for a restart.
- Stop search works from any machine. It was addressing `localhost:8000` from the
  browser, so it only ever worked in a browser running on the Pi itself.
- Clearing a number field in the settings form no longer makes saving fail.
- The error screen is drawn in black only, instead of into the black and red
  planes at once.
- A route alert affecting several departures is listed once rather than repeated
  per departure.
- The weather cache is written atomically, so an interrupted save cannot leave a
  file that fails to load.

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
