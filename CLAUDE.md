# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OpenPrism is a local-first LaTeX + AI workspace for academic writing: a three-panel web app (file tree / CodeMirror LaTeX editor / PDF preview) with an LLM assistant (chat/agent/tools modes), LaTeX compilation, template management, LLM-powered template transfer (migrating a paper between conference templates), real-time multi-user collaboration (Yjs CRDT), and peer-review tooling.

## Migration status (read this first)

The app is mid-migration from a single Node/Fastify process (no database, state on disk and in memory) to a cloud/Kubernetes-ready set of components: **Django REST Framework + Celery + Postgres + Redis + Garage (S3)**, keeping the React frontend. **Two backends currently coexist:**

| | Node backend (`apps/backend`, port 8787) | Django API (`apps/api`, port 8000) |
|---|---|---|
| Status | **Live** — the only backend the frontend can use today | Phases 1–6 done: models, JWT auth, S3-backed file service, projects/files/templates REST, legacy importer, Celery + async LaTeX compile, AI endpoints (llm, agent chat/direct/tools, vision, plot, arXiv search/bibtex), template transfer (legacy + MinerU), arXiv import, real-time collaboration (Channels websocket + invites) |
| State | Directories under `OPENPRISM_DATA_DIR` | Postgres (text files, metadata) + Garage (binaries, PDFs, templates) |
| Auth | Localhost trust + HMAC collab token | Real users, workspaces, roles, JWT |

The frontend has **no login UI yet**, so it cannot talk to the Django API end to end; Vite proxies `/api` to `OPENPRISM_API_URL` (default `http://localhost:8787`). Remaining work, in order: **7** cutover (nginx `web` image, delete `apps/backend`, **frontend login UI** — including passing the user's JWT as the `token` of the collab websocket, since owners no longer get the old localhost bypass), **8** k8s manifests in `deploy/k8s`. Phases 7–8 are not started.

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
docker compose up -d --wait  # postgres, redis, garage, api (runs `migrate`, then uvicorn --reload on :8000), worker-tex (Celery compile worker), worker-ai (Celery ai + import queues), beat
deploy/garage-init.sh        # one-time & idempotent: Garage layout, bucket, access key (reads S3_* from .env)
docker compose exec api python manage.py import_legacy --owner you@example.com   # optional: load templates/ and data/ (register that user first via POST /api/auth/register)
docker compose run --rm api python manage.py test        # API tests against the real Postgres + Garage (needs garage-init done); LaTeX tests skip here
docker compose run --rm worker-tex python manage.py test jobs transfer   # same, plus real pdflatex/bibtex compile + transfer tests (slow image, run when touching jobs/compile.py or transfer/)
docker compose run --rm worker-ai python manage.py test ai      # same, plus real matplotlib plot + sandbox tests (run when touching ai/plot*.py)
docker compose logs -f api worker-tex   # tail logs
docker compose restart worker-tex worker-ai beat   # Celery does not auto-reload: run after editing Python used by tasks
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
| `api` | Django + DRF + Channels, uvicorn (ASGI) | stateless REST **and the collab websocket** (`/api/collab`); `/healthz`, `/readyz` — **exists**. Scale horizontally: replicas sync through Redis, no sticky routing needed |
| `worker-tex` | Celery, queues `compile` + `transfer` | image with TeX Live (template transfer compiles LaTeX, so it runs here and also makes LLM/MinerU calls); per-command timeout, CPU/file-size rlimits, shell-escape off — **exists** (set container CPU/mem limits in k8s) |
| `worker-ai` | Celery, queues `ai` + `import` | LLM, vision, plot (runs LLM-generated Python), agent, arXiv import — **exist**. Image adds matplotlib/pandas/seaborn (`requirements-ai.txt`) |
| `beat` | Celery beat | reaps jobs whose worker died, deletes finished jobs after 24 h — **exists** (expired collab invites: later) |
| `postgres`, `redis`, `garage` | | **exist** in `compose.yaml`; managed services/operators in k8s |

Rules for this design: services are stateless and 12-factor (env-only config, no shared volumes — workers materialise project files into a temp dir), long operations become `Job` rows + Celery tasks the frontend polls, and nothing user-visible depends on local disk.

### Django API (`apps/api`)

Apps: `accounts` (email-login `User`, register/login/refresh/me), `projects` (`Workspace`, `Membership`, `Project`, `ProjectFile`, file service, REST views), `templates_app` (`Template` + S3 template files), `jobs` (`Job` model, compile service + Celery tasks, job API), `ai` (LLM client, agent, plot sandbox, arXiv, AI task + endpoints), `transfer` (template-transfer engine, nodes, MinerU client, endpoints), `collab` (invites, guest auth, Yjs rooms, websocket consumer), `common` (health, `{ok,error}` exception handler, path-preserving multipart parser, safe zip reader). `config/` has settings, urls, asgi, and the Celery app.

**Data model.** `Project` mirrors the old `project.json` (name, tags, archived, trashed/trashed_at, `file_order` JSON) and belongs to a `Workspace`; users reach projects through `Membership` roles (`owner`/`admin`/`editor` can write, `viewer` read-only). Registering creates a personal workspace. A user who is not a member gets **404, not 403**, to avoid revealing project existence.

**File storage — go through `projects/files.py`, never touch `ProjectFile` rows or S3 directly.** Text files (by extension, see `projects/paths.py`) live in Postgres (`ProjectFile.content`); binaries live in Garage under random keys `projects/<projectId>/<uuid>`, so renames are DB-only; templates live under `templates/<id>/`. Directories are implicit from path prefixes (explicit `dir` rows exist only for folders created empty). Always validate user paths with `safe_path()` (rejects absolute paths, `..`, NUL) or `sanitize_upload_path()` (lenient, for uploads/zips); the service refuses to put a file under a file or replace a directory.

**API conventions** (match `apps/frontend/src/api/client.ts`; change client and server together):
- Errors are `{ok: false, error: "<message>"}`. Where the Node backend returned that with HTTP 200 for business errors (missing name, tags not an array, delete of a missing file), Django does too; auth/permission/not-found/bad-path use real status codes.
- Project meta is camelCase (`createdAt`, `updatedAt`, `trashedAt`, `fileOrder`, plus `workspaceId`), ISO timestamps ending in `Z`.
- Auth is `Authorization: Bearer <JWT>`. Only `GET /api/projects/:id/blob` also accepts `?token=` (for `<img>`/`<object>`, which cannot set headers); it responds with `Content-Security-Policy: sandbox` so uploaded SVG can't run script.
- Folder uploads send relative paths in the multipart *filename* (`form.append('files', file, 'figs/a.png')`). Django normally strips this to a basename; `common/uploads.py` preserves the sanitised path as `file.full_path` — read it with `upload_path()`. In tests build such bodies by hand (the Django test client strips paths too; see `multipart()` in `projects/test_api.py`).
- Settings parse `DATABASE_URL` themselves (no django-environ); keep new config in `settings.py` via `env()` / `env_bool()`.

**Async jobs (compile).** Long work is a `Job` row plus a Celery task; the API never blocks on it. `POST /api/compile {projectId, mainFile, engine}` validates, then returns `{ok, jobId}` (max 3 active compiles per user → 429). `GET /api/jobs/:id` returns `{status: queued|running|success|failed, progressLog, error, result}` (`result` = `{log, status, engine, mainFile, pdfUrl}` once finished); `GET /api/jobs/:id/pdf` streams the PDF from Garage through the API (authenticated, also accepts `?token=`), so browsers never need direct access to Garage or CORS. The `compile_project` task (`jobs/tasks.py`) runs in the `compile` queue with `acks_late`: if a worker dies the message is redelivered, so tasks must be safe to re-run (the task skips jobs already finished). `updated_at` is the heartbeat; `reap_stale_jobs` fails jobs idle >10 min running / >30 min queued. `jobs/compile.py` is a port of the Node `compileService.js`: it materialises the project (text from Postgres, binaries from S3) into a temp dir, runs engine → bibtex/biber (biber if `.aux` has `\abx@aux@` or the source uses biblatex) → 2 more passes, treats "a PDF exists" as success even if the engine exited non-zero, and always deletes the temp dir. Output is capped at 200 KB of log. `tectonic` is accepted by the API but not installed in the worker image (reports "tectonic not available"). New async features should follow this pattern: model in `jobs`, task in `jobs/tasks.py`, route to a named queue in `CELERY_TASK_ROUTES`, status via `/api/jobs/:id`.

**AI endpoints (`apps/api/ai`).** `/api/llm`, `/api/agent/run`, `/api/vision/latex`, `/api/plot/from-table` create a `Job`, enqueue `ai.tasks.run_ai_job` on the `ai` queue and **block up to `AI_WAIT_SECONDS` (300) polling the DB**, so the Node-era response bodies are unchanged (the body is stored in `job.result['body']`). If the wait runs out the reply is `{ok: false, error, jobId}` and the job keeps running; `GET /api/jobs/:id` returns the body as `result` when finished. `arxiv/search` and `arxiv/bibtex` are quick and run inline in the api. Things to keep true when changing this code:
- **API keys never touch Postgres or the Celery result backend.** The view splits `llmConfig` into public fields (`model`, `endpoint`; stored in `Job.params`) and `{apiKey}`, which travels only as a task argument (briefly in the Redis broker; the task is `ignore_result`). Falls back to `OPENPRISM_LLM_*` env vars on the worker. `AiApiTests.assert_key_not_persisted` guards this.
- **SSRF guard** (`ai/ssrf.py`): user-supplied LLM endpoints that resolve to private/loopback/link-local addresses are refused unless `LLM_ALLOW_PRIVATE_ENDPOINTS=1` (set it only in dev for local models; compose passes it to `worker-ai`). DNS rebinding between check and request is a known gap — use NetworkPolicies in k8s.
- **The agent** (`ai/agent.py`) talks to the OpenAI tools API directly (no LangChain): up to 15 tool steps; tool failures are returned to the model as `Error: …` text instead of aborting; patches are only *proposed* (`{path, original, content, diff}`) and never written. Unified diffs are built/applied by `ai/patches.py` (tolerates shifted hunks and stripped blank context lines).
- **Plot** (`ai/plot.py` + `plot_runner.py`) runs LLM-written Python in a subprocess: AST check (no imports/dunders/introspection) → whitelisted builtins → scrubbed environment (no worker secrets) → rlimits + timeout → temp dir deleted. This is defence in depth, **not a real sandbox** (e.g. `plt.sys.modules` is reachable). Real isolation must come from the deployment: run `worker-ai` with no extra secrets, a pids limit, and a NetworkPolicy denying egress except LLM providers.
- Tests fake the LLM with a local HTTP server (`FakeLLM` in `ai/tests.py`) and run the task inline; real-Celery routing was verified manually with `docker compose up worker-ai`.
- A request holds a web thread while it waits; scale `api` accordingly or move clients to polling `/api/jobs/:id`.

**Template transfer (`apps/api/transfer`).** Port of the LangGraph pipeline (`graph.js`/`graphMineru.js`), same endpoints and `{status, progressLog, error}` shape as Node (`pending|running|waiting_images|success|failed`), but nothing blocks: `/start` creates the target project from the template and a `Job`; the **first `/step` claims the job and enqueues segment 1; later `/step` calls are read-only status polls**; `/status/:id` is the same read. Design points:
- **Hand-written state machine, not LangGraph** (`transfer/engine.py`). It runs nodes (`transfer/nodes.py`, one function per Node file) in *segments*: a segment ends at the pause before `checkLayout` (status `waiting_images`) or at `finalize`. `POST /submit-images` stores the screenshots in S3, bumps the segment number and enqueues the next segment. Only small state is persisted between segments (`engine.PERSISTED`: counters, compile/layout results, S3 keys); large intermediates (source text, Markdown, plan) live in memory for one segment, so **a segment must be restartable from its entry point** (`start` or `checkLayout`). A stale or duplicate segment is ignored (segment number) and a Postgres advisory lock stops two workers running the same job. LangGraph was rejected mainly because its checkpointer would write the API key into Postgres.
- **Secrets** (LLM key, MinerU token) are kept in Redis under `openprism:job-secrets:<jobId>` with a TTL (`JOB_SECRET_TTL_SECONDS`, 6 h, refreshed on use) via `common/secrets.py`, and deleted when the job ends, fails or is reaped. Never in `Job.params`/`result`/`progress_log`; `TransferApiTests.assert_no_secrets_in_db` guards this.
- Snapshots of files the pipeline overwrites go to S3 (`jobs/<id>/snapshots/…`), not into the project tree (Node leaked `.agent_runs/` into the file list). The final PDF is `jobs/<id>/output.pdf`, served by `GET /api/jobs/:id/pdf`.
- A worker crash fails the job (the reaper marks it after 10 idle minutes); there is no auto-resume because the key was never persisted. Compile "success" means a PDF exists even if the engine exited non-zero (as in Node), so `fixCompile` only fires when no PDF is produced.
- MinerU (`transfer/mineru.py`): the user-supplied `apiBase`, the upload URL and every redirect hop of the result download pass the SSRF guard; result-zip paths are validated strictly (unsafe path = error).
- **Known frontend gap (pre-existing, not fixed):** `TransferPanel` stops at `waiting_images` and nothing renders PDF pages or calls `transferSubmitImages`, so `layoutCheck` cannot complete from the UI (same on the Node backend). The backend side is fully implemented and tested.

**arXiv import.** `GET /api/projects/import-arxiv-sse?arxivIdOrUrl=&projectName=&token=` creates an `import` Job (queue `import`, worker-ai) and relays its progress as SSE `progress`/`done`/`error` events (auth via `?token=` since EventSource can't set headers). The task streams the download to a temp file, unpacks it with path/link/size checks (tar, or a single gzipped `.tex` saved as `main.tex`), and deletes the project if anything fails.

**Real-time collaboration (`apps/api/collab`).** Wire-compatible replacement for the Node `docStore.js`: the browser's `CollabProvider` (`apps/frontend/src/collab/provider.ts`, standard y-websocket framing: type 0 = sync, 1 = awareness, one `Y.Text` named `content`) works unchanged against `ws(s)://…/api/collab?projectId=&file=&token=`. Built on **`pycrdt`** (Yrs bindings) + a Channels `AsyncWebsocketConsumer`; `pycrdt-websocket` was *not* used because we need our own auth, read-only enforcement and cross-replica fan-out. Gotcha: every `pycrdt` message helper (`create_sync_message`, `create_update_message`, `handle_sync_message`'s reply, …) already includes the outer message-type byte — don't prefix it again.
- **Rooms** (`rooms.py`): one `Room` per open file per process (`RoomManager`), holding a `pycrdt.Doc`, awareness, and the local connections (each with an outbox queue, so Yjs callbacks never block). A room is evicted `COLLAB_ROOM_EVICT_SECONDS` (60) after its last client leaves, after a final flush.
- **Durable state** (`models.CollabDoc`, `store.py`): the Yjs *state*, not the file text, is what rooms load, so every replica starts from the same CRDT history. Seeding from file text happens once, under a Postgres advisory lock (two replicas seeding independently would duplicate the content on merge). On load, text that changed outside collaboration (REST edit, template apply…) is diffed into the doc as a normal edit — **the file wins when a room starts**. A flush merges (never overwrites) with the stored state and writes the text into `ProjectFile` in one transaction; it runs `OPENPRISM_COLLAB_FLUSH_DEBOUNCE_MS` (800) after edits and every `COLLAB_SYNC_INTERVAL_SECONDS` (30) as anti-entropy.
- **Multiple replicas** (`coord.py`): updates, awareness and control messages go over Redis pub/sub (`collab:room:<sha1>`), tagged with the sender's instance id. Because pub/sub is fire-and-forget, a replica that opens a room publishes its state vector and the replicas already holding it answer with the missing update plus their cursors (otherwise a late replica misses edits that are still unflushed in another process's memory). Lost messages heal at the next flush/merge. Replica liveness is a Redis zset (`collab:holders:*`), so `POST …/collab/flush` publishes a flush request and waits (≤5 s) for an ack from every live holder — the editor's Save in collab mode and anything that reads the file right after use this. `GET …/collab/status` reports connections and last flush error across replicas.
- **Auth** (`consumers.authorize`, `auth.py`, `tokens.py`): the websocket accepts `?token=` as either an **invite token** or a signed-in user's **JWT access token** (membership required). There is no localhost bypass. Invite tokens are `op2.<random>`, only their SHA-256 is stored (`CollabInvite`), default 24 h (max 7 d), role `editor` or `viewer`. `POST /api/projects/:id/collab/invite {role?}` needs write access; `GET /api/collab/resolve?token=` is public. **Viewers are read-only server-side**: their sync step-2/update frames are dropped (they still receive content and show cursors). Rejections are real close codes sent after accept (1008 unauthorised/not found/invalid path, 1003 binary file).
- **Guests**: the same invite token is the REST credential for people without an account (`Authorization: Bearer op2…`, or `?token=` on blob/PDF URLs). `InviteAuthentication` yields a `GuestUser` confined to one project. The default permission is now `IsRealUser` (guests refused everywhere); project-scoped views opt in with `@permission_classes([IsUserOrGuest])` (tree/file/blob/upload/files/folder/rename/file-order, compile, job status/pdf, collab flush/status) and `get_project()`/`get_job()` enforce the project and write role. Guests cannot list/create projects, call AI endpoints, or administer the project. **Any new project-scoped view that guests should reach needs that opt-in; anything else is automatically refused.**
- DB access from async code goes through `collab/dbasync.py` (`thread_sensitive=False`, thread pool). `channels.db.database_sync_to_async` runs *all* calls of a process in one thread, so one slow flush would stall every room. Tests set `CONN_MAX_AGE=0` so those pool-thread connections don't block `DROP DATABASE` (a failed teardown leaves `test_openprism` behind and the next run blocks on an interactive prompt — use `--noinput`).
- **Known limitations:** REST writes to a file while someone has it open are overwritten by the next flush (same as Node; the editor writes through the Yjs doc in collab mode). Renaming/deleting a file drops its stored Yjs state, but a room that is still live for the old path can recreate the file at its next flush. Awareness entries of a crashed replica linger until clients reconnect. Rooms persist at most every 800 ms, so a hard crash can lose that window.
- **Verifying against the real client stack:** `node apps/api/collab/interop/yjs_client.mjs <baseUrl> <inviteToken> <projectId> main.tex [<secondReplicaBaseUrl>]` drives the genuine `yjs`/`y-protocols` libraries (message handling copied from `provider.ts`) against a running stack; with a second URL (e.g. `docker compose run -d --no-deps -p 8001:8000 api uvicorn config.asgi:application --host 0.0.0.0 --port 8000`) it exercises two processes over Redis. Unit tests: `docker compose run --rm api python manage.py test collab --noinput` (uses `channels.testing.WebsocketCommunicator`; `daphne` is installed only because `channels.testing` imports it).

**Frontend compile contract.** `compileProject()` in `api/client.ts` works against both backends: Node answers with the finished PDF, Django returns a `jobId` which the client polls (1 s, 10 min cap) and then downloads, resolving to the same `{ok, pdf(base64), log, status}` shape and reporting progress via an optional callback (the editor shows it in the status bar).

**Gotchas.** `garage-init.sh` must run once before tests or presigned/binary features fail. Presigned URLs (currently unused by the UI) are signed for `S3_PUBLIC_ENDPOINT_URL`, so tests fetch them through the internal endpoint with the public `Host` header. `docker compose up` runs `migrate` on every api start (fine for dev; in k8s make it a one-off Job). New dependencies go in `apps/api/requirements.txt` as exact pins, then rebuild with `docker compose build api`.

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
