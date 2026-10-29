"""Run blocking Django DB work from async collab code without a single-thread bottleneck.

channels.db.database_sync_to_async is thread-sensitive: every call in a process shares one thread, so one slow
flush would delay every other room. These run in the shared thread pool instead, closing stale connections
around each call (as Django does per request).
"""
import functools

from asgiref.sync import sync_to_async
from django.db import close_old_connections


def db_async(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()
    return sync_to_async(run, thread_sensitive=False)
