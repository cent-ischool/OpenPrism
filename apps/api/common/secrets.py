"""Short-lived per-job secrets (user API keys) kept in Redis, never in Postgres.

Multi-step jobs (template transfer) need the user's LLM key across several worker segments and possibly a long
pause. The key is stored under a TTL, refreshed whenever a segment uses it, and deleted when the job ends.
"""
import json
from functools import lru_cache

import redis
from django.conf import settings

PREFIX = 'openprism:job-secrets:'


@lru_cache(maxsize=1)
def _client():
    return redis.Redis.from_url(settings.REDIS_URL)


def put(job_id, secrets):
    _client().set(f'{PREFIX}{job_id}', json.dumps(secrets), ex=settings.JOB_SECRET_TTL_SECONDS)


def get(job_id):
    """Return the stored secrets (refreshing their TTL), or {} if none/expired."""
    key = f'{PREFIX}{job_id}'
    raw = _client().get(key)
    if raw is None:
        return {}
    _client().expire(key, settings.JOB_SECRET_TTL_SECONDS)
    return json.loads(raw)


def delete(job_id):
    _client().delete(f'{PREFIX}{job_id}')
