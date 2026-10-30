#!/bin/sh
# Deployment entrypoint, used by .agentforge/app.yaml only (docker compose sets its own environment).
# settings.py refuses to start without a secret key and without S3 credentials. No secret lives in the repository,
# so fill the gaps here and run the command. The real S3 credentials arrive from the `forge-object-storage` Secret
# (AWS_* names, read by settings.py); the migrations hook may not get that Secret and does not talk to S3, so a
# placeholder is enough there.
set -eu

# The api, the workers and beat share one key, so whatever one process signs another can check, and it survives a
# restart (logins outlive a redeploy). Derived from the namespace's S3 secret, which every one of them gets and nothing else
# shares; random only where that Secret is absent (the migrations hook, which signs nothing).
# Set DJANGO_SECRET_KEY as an app variable to choose it instead.
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  if [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    DJANGO_SECRET_KEY="$(python -c 'import hashlib, os; print(hashlib.sha256(b"openprism-django:" + os.environ["AWS_SECRET_ACCESS_KEY"].encode()).hexdigest())')"
  else
    DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
  fi
  export DJANGO_SECRET_KEY
fi

if [ -z "${S3_ACCESS_KEY_ID:-}${AWS_ACCESS_KEY_ID:-}" ]; then export S3_ACCESS_KEY_ID=unset; fi
if [ -z "${S3_SECRET_ACCESS_KEY:-}${AWS_SECRET_ACCESS_KEY:-}" ]; then export S3_SECRET_ACCESS_KEY=unset; fi

exec "$@"
