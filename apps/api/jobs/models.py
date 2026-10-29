import uuid

from django.conf import settings
from django.db import models


class Job(models.Model):
    COMPILE, TRANSFER, IMPORT, PLOT, VISION, AGENT, LLM = 'compile', 'transfer', 'import', 'plot', 'vision', 'agent', 'llm'
    TYPES = [(t, t) for t in (COMPILE, TRANSFER, IMPORT, PLOT, VISION, AGENT, LLM)]
    QUEUED, RUNNING, WAITING_IMAGES, SUCCESS, FAILED = 'queued', 'running', 'waiting_images', 'success', 'failed'
    STATUSES = [(s, s) for s in (QUEUED, RUNNING, WAITING_IMAGES, SUCCESS, FAILED)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=TYPES)
    status = models.CharField(max_length=20, choices=STATUSES, default=QUEUED)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    project = models.ForeignKey('projects.Project', null=True, blank=True, on_delete=models.CASCADE, related_name='jobs')
    # Never put API keys in params/result: they are visible to anyone who can read the job row.
    params = models.JSONField(default=dict, blank=True)
    progress_log = models.JSONField(default=list, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
