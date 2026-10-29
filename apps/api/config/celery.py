import os

from celery import Celery
from celery.signals import worker_init, worker_process_init

from .hardening import make_undumpable

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('openprism')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@worker_init.connect
def _hide_main_process(**kwargs):
    make_undumpable()  # the main worker process: holds the credentials every child inherits


@worker_process_init.connect
def _hide_pool_process(**kwargs):
    make_undumpable()  # each pool process: it is the direct parent of the TeX / plot subprocesses
