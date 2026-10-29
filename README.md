<div align="center">

<img src="static/logo-rotating.gif" alt="OpenPrism Logo" width="200"/>

# OpenPrism

### OpenPrism — Vibe Writing for Academia

[![Node.js Version](https://img.shields.io/badge/node-%3E%3D18.0.0-brightgreen)](https://nodejs.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/OpenDCAI/OpenPrism?style=social)](https://github.com/OpenDCAI/OpenPrism/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/OpenDCAI/OpenPrism?style=social)](https://github.com/OpenDCAI/OpenPrism/network/members)
[![GitHub Issues](https://img.shields.io/github/issues/OpenDCAI/OpenPrism)](https://github.com/OpenDCAI/OpenPrism/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/OpenDCAI/OpenPrism)](https://github.com/OpenDCAI/OpenPrism/pulls)

[中文](README_ZH.md) | [English](README.md)

---

### ✨ Highlights

| 🤖 AI Assistant | ✍️ Compile & Preview | 📚 Templates |
|:---:|:---:|:---:|
| Chat / Agent history<br>Tools multi-step edits | TexLive / Tectonic / Auto<br>PDF preview & download | ACL / CVPR / NeurIPS / ICML<br>One-click conversion |

| 🔄 Template Transfer | | |
|:---:|:---:|:---:|
| Legacy (LaTeX→LaTeX) / MinerU (PDF→MD→LaTeX)<br>LLM-powered migration + auto compile fix + VLM layout check | | |

| 🔧 Advanced Editing | 🗂️ Project Management | ⚙️ Configuration |
|:---:|:---:|:---:|
| AI autocomplete / Diff / diagnose | Multi-project + file tree + upload | OpenAI-compatible endpoint<br>Local-first privacy |

| 🔍 Search | 📊 Charting | 🧠 Recognition |
|:---:|:---:|:---:|
| WebSearch / PaperSearch | Chart from tables | Formula/Chart recognition |

| 👥 Collaboration | 📝 Peer Review | |
|:---:|:---:|:---:|
| Multi-user real-time editing<br>Cursor sync & online management | AI Review Report / Consistency<br>Missing Citations / Compile Summary | |

---

<a href="#-quick-start" target="_self">
  <img alt="Quickstart" src="https://img.shields.io/badge/🚀-Quick_Start-2F80ED?style=for-the-badge" />
</a>
<a href="#-core-features" target="_self">
  <img alt="Features" src="https://img.shields.io/badge/✨-Features-orange?style=for-the-badge" />
</a>
<a href="#-contributing" target="_self">
  <img alt="Contributing" src="https://img.shields.io/badge/🤝-Contributing-purple?style=for-the-badge" />
</a>
<a href="#wechat-group" target="_self">
  <img alt="WeChat" src="https://img.shields.io/badge/💬-WeChat_Group-07C160?style=for-the-badge" />
</a>

</div>

## 📢 News

> [!WARNING]
> 🚧 <strong>Template Transfer is under testing</strong><br>
> The Template Transfer feature is currently in beta and may contain known or unknown bugs. If you encounter any issues, please report them via [Issues](https://github.com/OpenDCAI/OpenPrism/issues).

> [!TIP]
> 🆕 <strong>2025-02 · Template Transfer (Dual Mode)</strong><br>
> Two transfer modes are now available: Legacy mode (LaTeX→LaTeX direct migration) and MinerU mode (PDF→Markdown→LaTeX via MinerU API). Both modes feature LLM-powered content migration, automatic compile error fixing, and optional VLM-based layout checking.

> [!TIP]
> 🆕 <strong>2025-02 · Real-time Collaboration</strong><br>
> Multi-user simultaneous editing is now available, powered by CRDT with automatic conflict resolution and cursor sync. Current version requires a server with a public IP; invite remote collaborators via token-based links.

---

<div align="center">
<br>
<img src="static/首页.gif" alt="OpenPrism Home" width="90%"/>
<br>
<sub>✨ Home preview: three-panel workspace + editor + preview</sub>
<br><br>
</div>

---

## ✨ Core Features

OpenPrism is a local-first LaTeX + AI workspace for academic writing, optimized for fast editing, controlled changes, and privacy.

### 🤖 AI Assistant

- **Chat mode**: read-only Q&A
- **Agent mode**: generate diffs for confirmation
- **Tools mode**: multi-step tools + multi-file edits
- **Tasks**: polish, rewrite, restructure, translate, custom
- **Autocomplete**: Option/Alt + / or Cmd/Ctrl + Space, Tab to accept

### ✍️ Compile & Preview

- **Engines**: TexLive / Tectonic / Auto fallback
- **Preview toolbar**: zoom, fit width, 100%, download PDF
- **Compile log**: error parsing + one-click diagnose + jump to error
- **Views**: PDF / Figures / Diff

### 📚 Template System

- **Built-ins**: ACL / CVPR / NeurIPS / ICML
- **Conversion**: one-click template switch with content preserved

### 🔄 Template Transfer

- **Dual mode**: Legacy (LaTeX→LaTeX) and MinerU (PDF→Markdown→LaTeX)
- **MinerU integration**: parse PDF via MinerU API, extract Markdown + images, then fill into target template
- **LLM-powered migration**: AI analyzes source/target structure, drafts transfer plan, and applies content mapping
- **Auto compile fix**: automatically detect and fix LaTeX compilation errors with retry loop
- **VLM layout check**: optional visual layout validation using VLM to detect overflow, overlap, and spacing issues
- **Asset handling**: automatic copy of images, bib files, and style files from source to target

### 🗂️ Project Management

- **Projects panel**: manage multiple projects
- **File tree**: create/rename/delete/upload/drag
- **BibTeX**: quick create `references.bib`

### ⚙️ Configuration

Everything is configured with environment variables in `.env` (see `.env.sample`; Docker Compose reads it). The most useful ones:

```bash
# AI features — used when the UI has no LLM settings of its own (users can also enter their own key in the app;
# per-request keys are never stored by the server)
OPENPRISM_LLM_ENDPOINT=https://api.openai.com/v1/chat/completions
OPENPRISM_LLM_API_KEY=your-api-key
OPENPRISM_LLM_MODEL=gpt-4o-mini
LLM_ALLOW_PRIVATE_ENDPOINTS=0          # 1 only to use a local model (Ollama, vLLM) on a private address

# Template transfer from PDFs (MinerU)
OPENPRISM_MINERU_TOKEN=your-mineru-token

# Required for any shared deployment (the API refuses to start without a secret key)
DJANGO_SECRET_KEY=<long random string>
POSTGRES_PASSWORD=<password>
GARAGE_RPC_SECRET=<64 hex characters>
S3_ACCESS_KEY_ID=<GK + 24 hex characters>
S3_SECRET_ACCESS_KEY=<64 hex characters>
```

LLM and MinerU settings can also be entered in the app (they are kept in your browser and sent with each request). Collaboration invite links last `OPENPRISM_COLLAB_TOKEN_TTL` seconds (default 24 hours, at most 7 days).

---

## 👥 Collaboration Guide

OpenPrism has built-in real-time collaboration (CRDT / Yjs over WebSockets): several people can edit the same file at once and see each other's cursors. The server can run as multiple replicas — they stay in sync through Redis, and every save is merged with the stored document.

**Accounts and workspaces.** Each account has a personal workspace and can create team workspaces. Invite people from a workspace's **Members** page by email, with a role of Admin, Editor, Commenter or Viewer. If the address has no account yet, the invitation is applied automatically when that person registers (no email is sent — share the site address with them). Projects belong to a workspace and can be moved between workspaces you can edit.

**Inviting someone to a single project.** Open a project, choose **Collaboration** in the right-hand panel, and **generate an invite link**. Whoever opens it joins that one project as a guest — no account needed — and can edit (or only read, for viewer links) until the link expires. Guests can edit, compile and see live changes, but cannot see your other projects or use the AI features.

**Remote collaboration.** Collaborators just need to reach your server's address — put OpenPrism behind your usual HTTPS reverse proxy or host it where your team can reach it.

---

## 🎯 Usage Guide (Quick)

1. **Create Project**: Create new project in Projects panel and select template
2. **Write Paper**: Edit LaTeX in Files tree
3. **AI Edits**: Switch to Agent / Tools, generate diff and confirm
4. **Compile & Preview**: Click "Compile PDF", preview on right side
5. **Export PDF**: Click "Download PDF" in preview toolbar

---

## 📁 Project Structure

```
OpenPrism/
├── apps/
│   ├── frontend/           # React + TypeScript + Vite app (+ Dockerfile and nginx.conf for the web image)
│   │   └── src/
│   │       ├── app/          # pages: landing, projects, editor, template transfer, sign-in
│   │       ├── auth/         # sessions, guest (invite-link) mode, API-backed workspaces
│   │       ├── api/          # client.ts (all API calls) and auth.ts (tokens, refresh)
│   │       └── collab/       # real-time collaboration provider
│   └── api/                # Django API, Celery tasks and the collaboration websocket
│       ├── accounts/  projects/  templates_app/   # users, workspaces, files, templates
│       ├── jobs/             # async LaTeX compilation
│       ├── ai/  transfer/    # LLM features and template transfer
│       └── collab/           # live editing, invites
├── design/                 # shared design system (tokens, components, icons)
├── deploy/                 # storage setup scripts
├── templates/              # built-in LaTeX templates (ACL/CVPR/NeurIPS/ICML, …)
├── compose.yaml            # the whole stack for local use
└── CLAUDE.md               # contributor / agent guide with architecture details
```

---

## 🗺️ Roadmap

<table>
<tr>
<th width="35%">Feature</th>
<th width="15%">Status</th>
<th width="50%">Description</th>
</tr>
<tr>
<td><strong>👥 Real-time Collaboration</strong></td>
<td><img src="https://img.shields.io/badge/✅-Done-success?style=flat-square" alt="Done"/></td>
<td>Multi-user real-time editing with cursor sync and online user management (currently requires a server with public IP)</td>
</tr>
<tr>
<td><strong>🌐 Serverless Collaboration</strong></td>
<td><img src="https://img.shields.io/badge/⏳-Planned-yellow?style=flat-square" alt="Planned"/></td>
<td>Collaboration without a public server: WebRTC-based P2P direct connection without a third-party relay</td>
</tr>
<tr>
<td><strong>🔍 Enhanced WebSearch</strong></td>
<td><img src="https://img.shields.io/badge/⏳-Planned-yellow?style=flat-square" alt="Planned"/></td>
<td>Integrate third-party Search APIs (e.g. Google / Baidu / SerpAPI) for improved search quality and coverage</td>
</tr>
<tr>
<td><strong>📚 Template Transfer (Dual Mode)</strong></td>
<td><img src="https://img.shields.io/badge/✅-Done-success?style=flat-square" alt="Done"/></td>
<td>Legacy (LaTeX→LaTeX) and MinerU (PDF→MD→LaTeX) dual-mode template transfer with LLM-powered migration, auto compile fix, and VLM layout check</td>
</tr>
<tr>
<td><strong>📸 Version Snapshots &amp; Rollback</strong></td>
<td><img src="https://img.shields.io/badge/⏳-Planned-yellow?style=flat-square" alt="Planned"/></td>
<td>Project version management with snapshot saving and one-click rollback</td>
</tr>
<tr>
<td><strong>📖 Citation Search Assistant</strong></td>
<td><img src="https://img.shields.io/badge/⏳-Planned-yellow?style=flat-square" alt="Planned"/></td>
<td>Auto-search related papers and generate BibTeX citations</td>
</tr>
</table>

---

## 🤝 Contributing

Welcome to submit Issues or PRs:
1. Fork the repository
2. Create a new branch
3. Commit your changes
4. Submit a PR

Development commands:
```bash
npm run dev
npm run dev:frontend
npm run dev:backend
npm run build
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE).

---

## 🙏 Acknowledgments

- Tectonic
- CodeMirror
- PDF.js
- React / Django / Celery
- Yjs / pycrdt

---

<div align="center">

**If this project helps you, please give us a ⭐️ Star!**

[![GitHub stars](https://img.shields.io/github/stars/OpenDCAI/OpenPrism?style=social)](https://github.com/OpenDCAI/OpenPrism/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/OpenDCAI/OpenPrism?style=social)](https://github.com/OpenDCAI/OpenPrism/network/members)

<br>

<a name="wechat-group"></a>
<img src="static/wechat.png" alt="OpenPrism WeChat Community" width="300"/>
<br>
<sub>Scan to join the community WeChat group</sub>

<p align="center">
  <em>Made with ❤️ by OpenPrism Team</em>
</p>

</div>
