# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OpenPrism is a local-first LaTeX + AI workspace for academic writing: a three-panel web app (file tree / CodeMirror LaTeX editor / PDF preview) with an LLM assistant (chat/agent/tools modes), LaTeX compilation, template management, LLM-powered template transfer (migrating a paper between conference templates), real-time multi-user collaboration (Yjs CRDT), and peer-review tooling.

## Commands

```bash
npm install               # install all workspaces (root + apps/*)
npm run dev                # frontend (5173) + backend (8787) concurrently
npm run dev:backend        # backend only — node apps/backend/src/index.js
npm run dev:frontend       # frontend only — vite dev server
npm run build               # vite build (frontend only; backend is plain Node, no build step)
npm run preview              # vite preview of the built frontend

# Tunnels (expose local server publicly for remote collaboration)
npm run tunnel        # localtunnel
npm run tunnel:cf     # Cloudflare Tunnel (requires cloudflared installed)
npm run tunnel:ngrok  # ngrok (requires NGROK_AUTHTOKEN)
```

There is no test suite and no lint/format config anywhere in the repo (no ESLint/Prettier config, no Jest/Vitest). Don't assume `npm test` or `npm run lint` exist.

Requires a LaTeX engine on the host/container to compile PDFs: TexLive (`texlive-full`) or Tectonic. The devcontainer installs `latexmk` + a subset of `texlive-*` packages via apt.

Config is entirely environment-variable driven (`.env` at repo root, loaded by the backend) — there are no backend config files to edit. See `apps/backend/src/config/constants.js` for the full list of env vars (`OPENPRISM_LLM_*`, `OPENPRISM_DATA_DIR`, `OPENPRISM_COLLAB_*`, `OPENPRISM_MINERU_*`, `PORT`). Frontend-side LLM/MinerU settings are stored in browser `localStorage` under `openprism-settings-v1`, not in files.

## Architecture

This is an npm workspaces monorepo: `apps/frontend` (React 18 + TypeScript + Vite) and `apps/backend` (Node.js ESM + Fastify). No shared `packages/` currently exists despite being declared in the root workspaces glob.

### Backend (`apps/backend/src`)

`index.js` is the Fastify entry point: registers CORS, multipart (200MB limit), WebSocket support, a global auth preHandler for `/api/*` (except `/api/health` and `/api/collab`), serves the built frontend in production, and optionally starts a tunnel if `OPENPRISM_TUNNEL` is set.

Routes live in `routes/*.js` (one file per resource: `projects`, `compile`, `llm`, `vision`, `plot`, `agent`, `collab`, `transfer`, `arxiv`, `health`) and delegate to `services/*.js`. Projects are stored as plain directories under `OPENPRISM_DATA_DIR` (default `./data/<projectId>/`), each with a `project.json` metadata file plus the actual LaTeX/asset files — there is no database.

**LLM agent (`services/agentService.js`)**: a LangChain tools-agent (`createOpenAIToolsAgent` + `AgentExecutor`) exposing `read_file`/`list_files`/`propose_patch`/`apply_patch`/`search_arxiv`/`fetch_bibtex` tools. Patches are proposed as diffs for the frontend to confirm before `apply_patch` is called — this is the "Agent mode" diff-confirmation UX described in the README.

**Template Transfer (`services/transferAgent/`)** is the most structurally complex part of the backend — a LangGraph state machine (checkpointed with `MemorySaver`, so runs are resumable/steppable via `POST /api/transfer/step`) with two entry graphs:
- `graph.js` (Legacy mode, LaTeX→LaTeX): `analyzeSource → analyzeTarget → draftPlan → applyTransfer → copyAssets → compile`, then conditionally loops `compile → fixCompile` on failure (LLM reads the compile log and proposes a fix), or proceeds to an optional VLM layout-check loop (`requestPageImages → checkLayout → fixLayout`) before `finalize`.
- `graphMineru.js` (MinerU mode, PDF→MD→LaTeX): prepends `compileSource → parsePdfWithMineru` (calls `services/mineruService.js`, which uploads the PDF to MinerU's API, polls for extraction, and downloads Markdown + images) before rejoining the same `analyzeTarget → ... → finalize` pipeline.
- Each node is a pure function in `nodes/` operating on the shared state schema defined in `state.js`. The graph interrupts before `checkLayout`, waiting on the frontend to render PDF pages and POST screenshots via `/api/transfer/submit-images`.
- When adding a transfer step, add a node file under `nodes/`, wire it into the relevant graph's node/edge definitions, and extend `state.js` if new fields are needed.

**Real-time collaboration (`services/collab/`)**: no backend framework for this — hand-rolled Yjs integration. `docStore.js` keeps one in-memory Yjs doc per `"<projectId>:<filePath>"`, speaks a 2-message binary protocol over the `/api/collab` WebSocket (sync updates + awareness/cursor presence via `lib0`/`y-protocols`), and debounce-flushes changes to disk (800ms). `tokenService.js` issues/verifies a custom signed token format (`op1.<body>.<sig>`, HMAC-SHA256) for invite links; connections from `127.0.0.1` bypass token auth (dev convenience), remote connections require a valid token.

**Compilation (`services/compileService.js`)** shells out to `pdflatex`/`xelatex`/`lualatex`/`latexmk`/`tectonic`, running multiple passes and auto-detecting bibtex vs biber from the `.aux` file.

### Frontend (`apps/frontend/src`)

React Router app (`app/App.tsx`) with routes for landing, project list, the main editor (3-panel: file tree / CodeMirror editor / PDF preview), and a collab-invite-join page. `app/TransferPanel.tsx` drives the Template Transfer UI by polling the backend's LangGraph job via `transferStep()` and handling the `waiting_images` pause state. All backend communication goes through `api/client.ts`, which also defines the shared request/response types — there's no separate `types/` module. Vite proxies `/api` (incl. WebSocket upgrade) to the backend on 8787, and proxies `/texlive` to SwiftLaTeX's cloud TexLive resources for in-browser compilation assets.

### Templates (`templates/`)

Built-in conference templates (ACL, CVPR, NeurIPS, ICML) registered in `templates/manifest.json` (id, label, mainFile, category, bilingual descriptions, tags). Users can upload custom templates as a ZIP via `POST /api/templates/upload`, which registers them into the same manifest.

### Devcontainer

`.devcontainer/` builds a Node 20 image with TexLive packages installed via apt, mounts `/home/node/.claude` as a named Docker volume for Claude Code config persistence, and forwards ports 5173/8787. `postCreateCommand` chowns that volume to the `node` user before `npm install` — a fresh volume is created root-owned by Docker on first mount, which breaks any tool needing to write there until it's chowned.
