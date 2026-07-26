# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

E-Display drives a Waveshare 7.5" three-colour (black/white/red) e-paper display
on a Raspberry Pi, showing live HSL (Helsinki Regional Transport) departures plus
an FMI weather overlay. It ships as three containers built from two images.

| Component | Entry point | Image | Port |
| --- | --- | --- | --- |
| REST API + preview renderer | `api.py` (FastAPI) | `ghcr.io/saavuori/e-display/backend` | 8000 |
| Display loop (drives the panel) | `display.py` | same backend image, `command: python display.py` | — |
| Web UI | `web-ui/` (Next.js 16, React 19, Tailwind 4) | `ghcr.io/saavuori/e-display/web-ui` | 3000 |

`watchtower` is the fourth compose service; it polls GHCR every 5 minutes and
restarts containers labelled `com.centurylinklabs.watchtower.scope=e-display`.

## Architecture notes that are easy to get wrong

- **`config.json` is the single source of truth**, and it is a bind-mounted file
  shared by the API and display containers. The API writes it; the display loop
  re-reads it on *every* refresh cycle (`BusScheduleDisplay.run()`), so config
  changes take effect without a restart. Do not add in-memory config state that
  survives a cycle.
- **`config.py` owns the schema.** Adding a config field means touching four
  places: the dataclass, `to_dict()`, `from_dict()`, and `config.example.json` —
  plus `LayoutModel`/`ConfigModel` in `api.py` and the web UI form. Keep the
  `from_dict()` defaults identical to the dataclass field defaults; they drifted
  once already and were realigned in v0.0.3.
- **`HSL_API_KEY` from the environment wins** over the value in `config.json`
  (`Config.from_dict`). The key is passed into the containers from `.env` via
  `docker-compose.yml`.
- **Manual refresh is a trigger file**, not an IPC call. `POST /api/refresh`
  touches `triggers/refresh`; the display loop polls for it once a second while
  sleeping and deletes it. `triggers/` must stay a *directory* — mounting a
  single file into Docker caused `IsADirectoryError`.
- **The e-ink driver is resolved dynamically.** `load_epd_driver()` imports
  `waveshare_epd.<config.epd_driver>` and falls back to `epd_mock` on
  `ImportError`/`OSError`/`RuntimeError`. That fallback is what makes the code
  runnable and testable off-Pi — never let an import of a hardware driver happen
  at module top level outside this helper.
- **Preview mode renders once and exits.** When the mock driver is in use,
  `display.py` renders a single frame to `pic/` and returns instead of looping.
- **The web UI never talks to the backend by IP.** `next.config.ts` rewrites
  `/api/:path*` to `http://backend:8000`. Do not reintroduce a
  `NEXT_PUBLIC_API_URL` hardcoded host.
- **`lib/waveshare_epd/` is vendored Waveshare code.** Treat it as third-party;
  don't refactor or reformat it.

## Common commands

Run the API server:

```bash
python api.py
```

Render one frame off-Pi (mock driver, writes a preview image):

```bash
python display.py
```

Run the test suite — no hardware and no network required:

```bash
pytest
```

Install dev dependencies:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Frontend dev server (from `web-ui/`):

```bash
npm run dev
```

Lint the frontend (from `web-ui/`):

```bash
npm run lint
```

## Testing

`tests/` holds the whole suite: `test_config.py` (config round-trip and
defaults), `test_display.py` (HSL response parsing, arrival formatting),
`test_weather.py` (FMI response parsing). Everything is offline — HTTP calls are
stubbed and the e-ink driver mocks itself out.

New backend logic should come with a test here. If the logic is only reachable
through real hardware or a live HSL/FMI response, extract the pure part
(parsing, formatting, layout maths) and test that.

## Committing and versioning

This repository auto-versions from commit messages. The full rules live in
[.agents/workflows/committing.md](.agents/workflows/committing.md) and
[.agents/workflows/versioning.md](.agents/workflows/versioning.md); the essentials:

- Use conventional-commit prefixes — they *are* the version bump.
  `fix:` → patch, `feat:` → minor, `feat!:` or `BREAKING CHANGE:` → major,
  anything else → patch.
- **Never create git tags by hand** and never hardcode a version string. CI tags
  the commit and injects `VERSION`/`BUILD_DATE`/`GIT_SHA` as Docker build-args,
  which become `APP_*` env vars surfaced by `GET /api/version` and the web UI
  footer.
- Pushing to `main` triggers the full pipeline: tag → build `linux/arm64` images
  → push to GHCR → Watchtower deploys to the Pi within ~5 minutes. Treat a push
  to `main` as a production deploy.
- The build workflow skips `**.md`, `docs/**` and `LICENSE`, so a docs-only push
  does not cut a release.
- This machine runs PowerShell: chain commands with `;`, not `&&`.

## Changelog

Update [CHANGELOG.md](CHANGELOG.md) as part of any user-visible change — add the
entry under `## [Unreleased]` in the appropriate Keep a Changelog section
(`Added` / `Changed` / `Fixed` / `Removed`). When CI cuts a tag, the
`[Unreleased]` block is renamed to that version with its release date and a fresh
empty `[Unreleased]` is opened above it. Also update the comparison links at the
bottom of the file.

Describe the effect on the user, not the diff: "request timeouts so a hung HSL
call can't freeze the display loop" beats "added `timeout=` to `requests.post`".

## Conventions

- Python: 4-space indent, type hints on public functions, dataclasses for data
  models, module-level docstring on every file. No formatter is enforced — match
  the surrounding style.
- Rendering code in `display.py` and `weather.py` draws with PIL primitives into
  black and red 1-bit layers. Anything that relies on greyscale or anti-aliasing
  will not survive the e-ink palette.
- Layout values are pixel coordinates against a fixed 800×480 canvas
  (`DISPLAY_WIDTH`/`DISPLAY_HEIGHT` in `config.py`) and are all user-editable
  through the layout editor — do not bake new positions into the drawing code.
- Frontend: TypeScript, function components, Tailwind utility classes; one
  component per file in `web-ui/components/`.
