# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OpenPrism is a local-first LaTeX + AI workspace for academic writing: a three-panel web app (file tree / CodeMirror LaTeX editor / PDF preview) with an LLM assistant (chat/agent/tools modes), LaTeX compilation, template management, LLM-powered template transfer (migrating a paper between conference templates), real-time multi-user collaboration (Yjs CRDT), and peer-review tooling.

## Migration status (read this first)

The app is mid-migration from a single Node/Fastify process (no database, state on disk and in memory) to a cloud/Kubernetes-ready set of components: **Django REST Framework + Celery + Postgres + Redis + Garage (S3)**, keeping the React frontend. **Two backends currently coexist:**

| | Node backend (`apps/backend`, port 8787) | Django API (`apps/api`, port 8000) |
|---|---|---|
| Status | **Live** — the only backend the frontend can use today | Phases 1–3 done: models, JWT auth, S3-backed file service, projects/files/templates REST, legacy importer |
| State | Directories under `OPENPRISM_DATA_DIR` | Postgres (text files, metadata) + Garage (binaries, PDFs, templates) |
| Auth | Localhost trust + HMAC collab token | Real users, workspaces, roles, JWT |

The frontend has **no login UI yet**, so it cannot talk to the Django API end to end; Vite proxies `/api` to `OPENPRISM_API_URL` (default `http://localhost:8787`). Remaining work, in order: **4** Celery workers + LaTeX compile as an async job (and the polling change in `EditorPage.tsx`), **5** AI features (llm/vision/plot/agent/arXiv/MinerU/template transfer) rewritten in Python with a Postgres LangGraph checkpointer, **6** real-time collab on Django Channels (pycrdt-websocket, same y-websocket wire protocol), **7** cutover (nginx `web` image, delete `apps/backend`, frontend login), **8** k8s manifests in `deploy/k8s`. Phases 4–8 are not started; do not assume their endpoints exist (`/api/compile`, `/api/llm`, `/api/transfer/*`, `/api/collab` are Node-only for now).

## Running the project

Develop inside the devcontainer (it has Node 20, TeX Live, and docker-in-docker so `docker compose` works inside it). Ports 5173, 8000, 8787, 5432, 6379, 3900 are forwarded.

**Legacy app (what you see in the browser today):**
```bash
cp .env.sample .env          # once; add OPENROUTER_API_KEY / OPENPRISM_LLM_* if you want the AI features
npm install
npm run dev                  # Vite (5173) + Node backend (8787)
```

**Data services + Django API (compose.yaml at the repo root):**
```bash
docker compose up -d --wait  # postgres, redis, garage, api (api runs `migrate`, then uvicorn --reload on :8000)
deploy/garage-init.sh        # one-time & idempotent: Garage layout, bucket, access key (reads S3_* from .env)
docker compose exec api python manage.py import_legacy --owner you@example.com   # optional: load templates/ and data/ (register that user first via POST /api/auth/register)
docker compose run --rm api python manage.py test   # 38 tests against the real Postgres + Garage (needs garage-init done)
docker compose logs -f api   # tail logs
docker compose down          # stop; volumes kept (add -v to wipe all data)
```
Quick checks: `curl localhost:8000/healthz` (liveness) and `curl localhost:8000/readyz` (Postgres + Redis + S3 reachable; 503 otherwise). The api container mounts `apps/api` live (code edits reload) and mounts `templates/` and `data/` read-only at `/legacy/` for the importer. Use plain `docker compose`, not npm wrappers.

**Other commands:**
```bash
npm run dev:backend | dev:frontend | build | preview   # Node backend only / Vite only / production build / preview
npm run tunnel | tunnel:cf | tunnel:ngrok              # expose the Node server publicly (dev collaboration only; Node backend)
docker compose run --rm api python manage.py makemigrations <app>   # after model changes; commit the migration
```
To point the dev frontend at the Django API: `OPENPRISM_API_URL=http://localhost:8000 npm run dev:frontend` (requires the login UI, not built yet).

There is no JS test suite and no lint/format config (no ESLint/Prettier/Jest/Vitest). Only the Django API has tests (`manage.py test`). `tsc --noEmit` in `apps/frontend` reports 7 pre-existing type errors (CodeMirror/Blob/listener typings); none come from the redesign.

LaTeX compile needs a TeX engine (`texlive-full` or Tectonic); the devcontainer installs `latexmk` plus a subset of `texlive-*`. In the target architecture only the `worker-tex` image carries TeX Live.

## Configuration

Everything is environment variables; `.env` at the repo root (copied from `.env.sample`, gitignored, passed into the devcontainer via `runArgs --env-file`, and read by compose for `${VAR}` interpolation). Compose supplies container-side URLs (`postgres`, `redis`, `garage` hostnames) itself, so `.env` values like `DATABASE_URL=...@localhost` are for tools running in the devcontainer, not inside compose services.

- **Node backend:** `apps/backend/src/config/constants.js` — `OPENPRISM_LLM_*`, `OPENPRISM_DATA_DIR`, `OPENPRISM_COLLAB_*`, `OPENPRISM_MINERU_*`, `PORT`.
- **Django API:** `apps/api/config/settings.py` — `DJANGO_SECRET_KEY` (**required, no default; startup fails without it**), `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL`, `REDIS_URL` / `CELERY_BROKER_URL`, `S3_ENDPOINT_URL` (internal), `S3_PUBLIC_ENDPOINT_URL` (browser-reachable; used in presigned links), `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`. The values in `.env.sample` (all-zero Garage secrets, `dev-insecure-change-me`) are dev placeholders — never reuse them on a shared deployment.
- Frontend LLM/MinerU settings live in browser `localStorage` (`openprism-settings-v1`), not in files.

## Architecture

npm workspaces monorepo: `apps/frontend` (React 18 + TypeScript + Vite), `apps/backend` (legacy Node.js ESM + Fastify), plus `apps/api` (Django, Python — not an npm workspace; built from `apps/api/Dockerfile`). `design/` is the shared UI package. No shared `packages/` exists despite the workspaces glob.

### Target component split (for k8s; one image/Deployment each)

| Component | Tech | Role |
|---|---|---|
| `web` | nginx + built frontend | static SPA, proxies `/api` and WebSocket upgrades *(Phase 7)* |
| `api` | Django + DRF, uvicorn (ASGI) | stateless REST (and later Channels collab); `/healthz`, `/readyz` — **exists** |
| `worker-tex` | Celery, queue `compile` | image with TeX Live; CPU/mem limits, time limits *(Phase 4)* |
| `worker-ai` | Celery, queues `ai`/`transfer`/`import` | LLM, vision, plot (runs LLM-generated Python → must be sandboxed), agent, transfer graph, MinerU, arXiv *(Phase 5)* |
| `beat` | Celery beat | cleanup of expired invites / stale jobs |
| `postgres`, `redis`, `garage` | | **exist** in `compose.yaml`; managed services/operators in k8s |

Rules for this design: services are stateless and 12-factor (env-only config, no shared volumes — workers materialise project files into a temp dir), long operations become `Job` rows + Celery tasks the frontend polls, and nothing user-visible depends on local disk.

### Django API (`apps/api`)

Apps: `accounts` (email-login `User`, register/login/refresh/me), `projects` (`Workspace`, `Membership`, `Project`, `ProjectFile`, file service, REST views), `templates_app` (`Template` + S3 template files), `jobs` (`Job` model for async work), `collab` (`CollabInvite`), `common` (health, `{ok,error}` exception handler, path-preserving multipart parser, safe zip reader). `config/` has settings, urls, asgi, and the Celery app.

**Data model.** `Project` mirrors the old `project.json` (name, tags, archived, trashed/trashed_at, `file_order` JSON) and belongs to a `Workspace`; users reach projects through `Membership` roles (`owner`/`admin`/`editor` can write, `viewer` read-only). Registering creates a personal workspace. A user who is not a member gets **404, not 403**, to avoid revealing project existence.

**File storage — go through `projects/files.py`, never touch `ProjectFile` rows or S3 directly.** Text files (by extension, see `projects/paths.py`) live in Postgres (`ProjectFile.content`); binaries live in Garage under random keys `projects/<projectId>/<uuid>`, so renames are DB-only; templates live under `templates/<id>/`. Directories are implicit from path prefixes (explicit `dir` rows exist only for folders created empty). Always validate user paths with `safe_path()` (rejects absolute paths, `..`, NUL) or `sanitize_upload_path()` (lenient, for uploads/zips); the service refuses to put a file under a file or replace a directory.

**API conventions** (match `apps/frontend/src/api/client.ts`; change client and server together):
- Errors are `{ok: false, error: "<message>"}`. Where the Node backend returned that with HTTP 200 for business errors (missing name, tags not an array, delete of a missing file), Django does too; auth/permission/not-found/bad-path use real status codes.
- Project meta is camelCase (`createdAt`, `updatedAt`, `trashedAt`, `fileOrder`, plus `workspaceId`), ISO timestamps ending in `Z`.
- Auth is `Authorization: Bearer <JWT>`. Only `GET /api/projects/:id/blob` also accepts `?token=` (for `<img>`/`<object>`, which cannot set headers); it responds with `Content-Security-Policy: sandbox` so uploaded SVG can't run script.
- Folder uploads send relative paths in the multipart *filename* (`form.append('files', file, 'figs/a.png')`). Django normally strips this to a basename; `common/uploads.py` preserves the sanitised path as `file.full_path` — read it with `upload_path()`. In tests build such bodies by hand (the Django test client strips paths too; see `multipart()` in `projects/test_api.py`).
- Settings parse `DATABASE_URL` themselves (no django-environ); keep new config in `settings.py` via `env()` / `env_bool()`.

**Gotchas.** `garage-init.sh` must run once before tests or presigned/binary features fail. Presigned URLs are signed for `S3_PUBLIC_ENDPOINT_URL`, so tests fetch them through the internal endpoint with the public `Host` header. `docker compose up` runs `migrate` on every api start (fine for dev; in k8s make it a one-off Job). New dependencies go in `apps/api/requirements.txt` as exact pins, then rebuild with `docker compose build api`.

### Legacy Node backend and frontend

The legacy backend lives in `apps/backend/src`. `index.js` is the Fastify entry point: registers CORS, multipart (200MB limit), WebSocket support, a global auth preHandler for `/api/*` (except `/api/health` and `/api/collab`), serves the built frontend in production, and optionally starts a tunnel if `OPENPRISM_TUNNEL` is set.

Routes live in `routes/*.js` (one file per resource: `projects`, `compile`, `llm`, `vision`, `plot`, `agent`, `collab`, `transfer`, `arxiv`, `health`) and delegate to `services/*.js`. Projects are stored as plain directories under `OPENPRISM_DATA_DIR` (default `./data/<projectId>/`), each with a `project.json` metadata file plus the actual LaTeX/asset files — there is no database.

**LLM agent (`services/agentService.js`)**: a LangChain tools-agent (`createOpenAIToolsAgent` + `AgentExecutor`) exposing `read_file`/`list_files`/`propose_patch`/`apply_patch`/`search_arxiv`/`fetch_bibtex` tools. Patches are proposed as diffs for the frontend to confirm before `apply_patch` is called — this is the "Agent mode" diff-confirmation UX described in the README.

**Template Transfer (`services/transferAgent/`)** is the most structurally complex part of the backend — a LangGraph state machine (checkpointed with `MemorySaver`, so runs are resumable/steppable via `POST /api/transfer/step`) with two entry graphs:
- `graph.js` (Legacy mode, LaTeX→LaTeX): `analyzeSource → analyzeTarget → draftPlan → applyTransfer → copyAssets → compile`, then conditionally loops `compile → fixCompile` on failure (LLM reads the compile log and proposes a fix), or proceeds to an optional VLM layout-check loop (`requestPageImages → checkLayout → fixLayout`) before `finalize`.
- `graphMineru.js` (MinerU mode, PDF→MD→LaTeX): prepends `compileSource → parsePdfWithMineru` (calls `services/mineruService.js`, which uploads the PDF to MinerU's API, polls for extraction, and downloads Markdown + images) before rejoining the same `analyzeTarget → ... → finalize` pipeline.
- Each node is a pure function in `nodes/` operating on the shared state schema defined in `state.js`. The graph interrupts before `checkLayout`, waiting on the frontend to render PDF pages and POST screenshots via `/api/transfer/submit-images`.
- When adding a transfer step, add a node file under `nodes/`, wire it into the relevant graph's node/edge definitions, and extend `state.js` if new fields are needed.

**Real-time collaboration (`services/collab/`)**: no backend framework for this — hand-rolled Yjs integration. `docStore.js` keeps one in-memory Yjs doc per `"<projectId>:<filePath>"`, speaks a 2-message binary protocol over the `/api/collab` WebSocket (sync updates + awareness/cursor presence via `lib0`/`y-protocols`), and debounce-flushes changes to disk (800ms). `tokenService.js` issues/verifies a custom signed token format (`op1.<body>.<sig>`, HMAC-SHA256) for invite links; connections from `127.0.0.1` bypass token auth (dev convenience), remote connections require a valid token.

**Compilation (`services/compileService.js`)** shells out to `pdflatex`/`xelatex`/`lualatex`/`latexmk`/`tectonic`, running multiple passes and auto-detecting bibtex vs biber from the `.aux` file.

**Frontend (`apps/frontend/src`).**
React Router app (`app/App.tsx`) with routes for landing, project list / workspace home (`app/ProjectPage.tsx`, sections via `?section=`), the main editor, and a collab-invite-join page. The editor (`app/EditorPage.tsx`, styles in `app/editor-shell.css`) is a shell of icon rails + collapsible/resizable side panels around an editor/PDF split: left panel = Files / Outline / project Search; right panel = Assistant / Review / arXiv / Websearch / Vision / Plot / Collaborate; centre has an Editor / Split / PDF mode switch. Layout state persists in `localStorage` under `openprism-editor-layout-v1`. `app/TransferPanel.tsx` drives the Template Transfer UI by polling the backend's LangGraph job via `transferStep()` and handling the `waiting_images` pause state. All backend communication goes through `api/client.ts`, which also defines the shared request/response types — there's no separate `types/` module. Vite proxies `/api` (incl. WebSocket upgrade) to the backend on 8787, and proxies `/texlive` to SwiftLaTeX's cloud TexLive resources for in-browser compilation assets.

### Design system (`design/`)

All UI is built from the shared design system at the repo root, imported by the frontend as `@design` (alias in `apps/frontend/vite.config.ts` + `paths` in `apps/frontend/tsconfig.json`). Read `design/README.md` before touching UI. Key pieces:
- `tokens.css` — colour (light + dark via `data-theme` on `<html>`), type, spacing, radius, motion tokens and `op-`-prefixed component classes. Loaded first in `src/main.tsx`, before `App.css` and page CSS.
- `Icon.tsx` / `iconPaths.ts` — the only icon source (`<Icon name="…" />`). Add new glyphs to `iconPaths.ts`; never use emoji, text glyphs (✕ ▾ ▸ −) or pasted inline SVGs.
- `ui.tsx` — `Button`, `IconButton` (label required), `Badge`, `Tag`, `Avatar`, `Menu`/`MenuButton`, `Select`, `SegmentedControl`, `Modal`, `PanelHeader`, `EmptyState`.
- `AppTopBar.tsx` (shared top bar on every screen), `Logo.tsx`, `theme.ts` (`useTheme`), `SignedOut.tsx`.
- `workspace.tsx` — **mock** users / workspaces / roles / project→workspace mapping, browser-only (`localStorage` key `openprism-mock-workspaces-v1`). No backend auth exists; replace the data source here when it does.

Rules when writing UI:
- Use tokens (`var(--surface)`, `var(--text-2)`, `var(--accent)`…), never hex/rgba literals.
- Use the `design/` components instead of new button/dropdown/menu styles. The old `btn` / `ios-btn` / `ios-select` / `ios-dropdown` / `toolbar-btn` / `icon-btn` families were removed.
- Allow one primary button per region.
- New strings go through `t('English text')`, with a matching entry added to `src/i18n/locales/zh-CN.json`. English falls back to the key.

`app/App.css` holds remaining legacy page styles (already mapped onto tokens). New page-level styles go in a page stylesheet such as `app/pages.css` or `app/editor-shell.css`.

The static reference for the target look (style guide `design-system.html` + clickable prototype `index.html`) lives in the Open Design project, outside this repo.

### Templates (`templates/`)

Built-in conference templates (ACL, CVPR, NeurIPS, ICML) registered in `templates/manifest.json` (id, label, mainFile, category, bilingual descriptions, tags). Users can upload custom templates as a ZIP via `POST /api/templates/upload`, which registers them into the same manifest. (In the Django API, templates are `Template` rows with files in Garage; `manage.py import_legacy` loads this directory into them, and `manifest.json` is no longer the source of truth there.)

### Devcontainer

`.devcontainer/` builds a Node 20 image with TexLive packages installed via apt, mounts `/home/node/.claude` as a named Docker volume for Claude Code config persistence, adds the docker-in-docker feature (so `docker compose` runs inside it), and forwards ports 5173 (Vite), 8787 (Node), 8000 (Django), 5432 (Postgres), 6379 (Redis), 3900 (Garage S3). `postCreateCommand` chowns that volume to the `node` user before `npm install` — a fresh volume is created root-owned by Docker on first mount, which breaks any tool needing to write there until it's chowned.
