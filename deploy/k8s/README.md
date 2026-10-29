# Kubernetes deployment

Kustomize manifests for running OpenPrism on Kubernetes.

> **Status: written and statically checked, never applied to a cluster.** `kubectl kustomize` renders every
> overlay and a script checked the output for internal consistency (selectors, secret/config references, labels used
> by the network policies, security settings). Nothing here has been run against a real API server, so expect to fix
> small things on first contact. The parts most likely to need it are called out under *Unverified* below.

## Layout

| Path | What it is |
|---|---|
| `base/` | The application: Deployments for `api`, `web`, `worker-compile`, `worker-transfer`, `worker-ai` and `beat`, the migration Job, Services, PodDisruptionBudgets, HorizontalPodAutoscalers, the Ingress and the NetworkPolicies. No namespace, no Secrets. |
| `overlays/local/` | A self-contained environment for a local cluster: base + in-cluster Postgres, Redis and Garage (S3), a one-shot Garage setup Job, dev-only Secrets, a `restricted` namespace. |
| `overlays/production/` | A starting point for a real cluster: managed Postgres/Redis/S3, pinned registry images, a TLS host, egress rules for the managed services. Every value you must change is marked `CHANGE ME`. |
| `components/keda/` | Optional: scale the workers on queue depth instead of CPU (needs KEDA). |
| `base/secrets.example.yaml` | The two Secrets every environment must provide (not applied by kustomize). |
| `build-images.sh`, `deploy.sh`, `kind/` | Helpers: build the four images, apply an overlay and wait for it, and create a local kind cluster. |

## Components

| Deployment | Image | Queues / role | Notes |
|---|---|---|---|
| `api` | `openprism/api` | REST + the collaboration websocket | 2–10 replicas on CPU. `/readyz` (Postgres, Redis, S3) gates traffic; `/healthz` gates restarts. Replicas sync live documents through Redis, so no sticky sessions are needed. |
| `web` | `openprism/web` | nginx: the SPA, and `/api` proxied to `api` | 2–6 replicas. |
| `worker-compile` | `openprism/worker-tex` | `compile` | **Runs untrusted LaTeX.** No internet egress, no LLM credentials. |
| `worker-transfer` | `openprism/worker-tex` | `transfer` | Template transfer: TeX plus LLM/MinerU calls. Tasks run up to 31 minutes. |
| `worker-ai` | `openprism/worker-ai` | `ai`, `import` | LLM, vision, plot (runs LLM-written Python), arXiv import. |
| `beat` | `openprism/api` | scheduler | Exactly one replica, strategy `Recreate`. |

Workers get a shutdown grace period longer than their task time limits (360 s / 1900 s / 1000 s), so a rolling update lets a running job finish instead of killing it.

## Using it

```bash
deploy/k8s/build-images.sh 1.0.0 registry.example.com/acme/   # build; then docker push the four images
kubectl apply -f my-secrets.yaml                                # openprism-core and openprism-ai (see secrets.example.yaml)
deploy/k8s/deploy.sh production                                 # apply, run migrations, wait for the rollouts
```

Locally (kind): `deploy/k8s/kind/kind-up.sh` creates a cluster with Calico, metrics-server and ingress-nginx and loads
the images; `deploy/k8s/deploy.sh local` deploys; the app is then on http://localhost:8088.

### Prerequisites

* A CNI that **enforces NetworkPolicy** (Calico, Cilium, ...). Without one the policies are silently ignored and the
  isolation described below does not exist. (kind's default CNI does not enforce them, hence Calico in `kind-up.sh`.)
* An ingress controller. The Ingress is written for ingress-nginx; its annotations raise the default 1 MB body limit
  and 60 s timeouts, which would otherwise break uploads, long AI requests and the collaboration websocket.
* metrics-server (the HorizontalPodAutoscalers read CPU).
* For production: managed Postgres, Redis and S3-compatible storage; cert-manager for TLS (optional).

## Security model

The compile worker executes documents written by whoever can edit a project, including invited guests. The layers:

1. **In the process** (`apps/api/jobs/compile.py`, `config/hardening.py`): TeX runs with an allow-listed environment (no
   credentials), no shell escape, paranoid file access (except LuaTeX, which cannot run that way), `latexmk` without
   its rc files, `biber` without config, and the worker marks itself non-dumpable so children cannot read its
   `/proc/<pid>/environ`. LuaTeX's Lua `io.open` can still read any *file* the worker's user can read, so keep
   credentials out of files in the image and out of mounted volumes.
2. **In the pod**: non-root, read-only root filesystem, all capabilities dropped, no service-account token, CPU/memory/
   ephemeral-storage limits, `restricted` Pod Security profile on the namespace.
3. **On the network** (`base/networkpolicies.yaml`): default deny; `worker-compile` can reach only DNS and the data
   services. The workers that call LLM providers get HTTPS to the public internet only, with private ranges and
   metadata endpoints excluded (a second line behind the application's own SSRF check).
4. **Stronger, optional**: run `worker-compile` (and `worker-ai`) under a sandboxed runtime — add
   `runtimeClassName: gvisor` (or Kata) to their pod specs. This is the right fix for the residual risk that
   LLM-written plot code and LaTeX share a user with the worker process.

Secrets are split by need: only `worker-transfer` and `worker-ai` receive `openprism-ai` (LLM and MinerU keys).
User-supplied API keys never reach Kubernetes Secrets or Postgres; they live in Redis for the length of a job.

## Operating notes

* **Database connections.** Each API pod holds up to ~`ASGI_THREADS` (16) request threads plus a pool for the
  collaboration rooms, each with its own connection, and each worker pod a few more. At 10 API replicas this can pass
  Postgres's default `max_connections` of 100: put PgBouncer in front of Postgres, or raise the limit.
* **Pod PID limits.** The plot sandbox relies on the kubelet's `podPidsLimit` (a per-pod `pids` cgroup limit) to stop
  fork bombs; set it cluster-wide.
* **Migrations.** `deploy.sh` runs the `migrate` Job and waits for it; the API, workers and beat also wait in an init
  container until `manage.py migrate --check` passes. Migrations must stay backwards compatible with the previous
  release for the duration of a rolling update.
* **Local data stores** (`overlays/local`) are single instances without backups. Do not use them for anything you
  would miss.

## Unverified

Things that were reasoned about but not run, in rough order of risk:

* `overlays/local/garage-init-job.yaml` drives Garage's admin API (`/v1/layout`, `/v1/bucket`, `/v1/key/import`, ...)
  from memory of the v1.0 API. The compose equivalent (`deploy/garage-init.sh`, which uses the CLI) is tested.
* Read-only root filesystems for the TeX worker (`HOME` and caches are redirected to `/tmp`; `xelatex`/`lualatex` font
  caches under a read-only root have not been exercised in a pod).
* `components/keda` (only rendered).
* NetworkPolicy behaviour on a real CNI, and that kubelet probes are unaffected by the default-deny policy.
* The production overlay's CIDR/hostname placeholders and the ingress-controller namespace label.
