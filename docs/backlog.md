# Backlog

## Run the Kubernetes manifests on a real cluster

`deploy/k8s` has been rendered with `kubectl kustomize` and checked for internal consistency, but never applied to a
cluster. Do a full run on a local `kind` cluster, then fix whatever breaks.

**How**
1. `deploy/k8s/build-images.sh dev`
2. `deploy/k8s/kind/kind-up.sh` (creates the cluster with Calico, metrics-server and ingress-nginx, and loads the images)
3. `deploy/k8s/deploy.sh local`, then use the app at http://localhost:8088 and re-run the browser scenario (sign in,
   compile, invite link, two browsers editing live).

**Check, in rough order of risk** (the same list as "Unverified" in `deploy/k8s/README.md`)
- [ ] The Garage init Job (`overlays/local/garage-init-job.yaml`): it uses Garage's admin API (`/v1/layout`,
      `/v1/bucket`, `/v1/key/import`, ...) written from memory of the v1.0 API. Confirm each call, or switch to the CLI.
- [ ] Read-only root filesystem for the TeX worker: compile with `pdflatex`, `xelatex`, `lualatex` and `latexmk` inside
      a pod, and confirm the caches under `/tmp` work and the compile hardening still holds.
- [ ] NetworkPolicies on a real CNI: the default-deny policy must not break kubelet probes; `worker-compile` must have
      no internet; the workers that call LLM providers must reach only public HTTPS.
- [ ] HorizontalPodAutoscalers read CPU (needs metrics-server).
- [ ] `components/keda`: install KEDA and apply the component.
- [ ] Rolling update: change an image tag mid-job and confirm a running compile/transfer finishes rather than being killed.
- [ ] The `migrate` Job and the init containers that wait for it, including a second `deploy.sh` run (Job recreation).
- [ ] Production overlay placeholders (CIDRs, hostname, ingress-controller namespace label) against a real cluster.

**Decisions to make along the way**
- Whether `worker-compile` and `worker-ai` should run under a sandboxed runtime (`runtimeClassName: gvisor` or Kata).
- Whether to add PgBouncer in front of Postgres (connection count grows with API replicas).
