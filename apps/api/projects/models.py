import uuid

from django.conf import settings
from django.db import models


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Membership', related_name='workspaces')

    def __str__(self):
        return self.name


class Membership(models.Model):
    OWNER, ADMIN, EDITOR, VIEWER = 'owner', 'admin', 'editor', 'viewer'
    ROLES = [(OWNER, 'Owner'), (ADMIN, 'Admin'), (EDITOR, 'Editor'), (VIEWER, 'Viewer')]
    WRITE_ROLES = (OWNER, ADMIN, EDITOR)

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=10, choices=ROLES, default=VIEWER)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'user'], name='uniq_workspace_user')]


class Project(models.Model):
    """Mirrors the Node backend's project.json."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='projects')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    name = models.CharField(max_length=200)
    tags = models.JSONField(default=list, blank=True)
    archived = models.BooleanField(default=False)
    trashed = models.BooleanField(default=False)
    trashed_at = models.DateTimeField(null=True, blank=True)
    file_order = models.JSONField(default=dict, blank=True)  # {folder: [names]}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class ProjectFile(models.Model):
    """One row per file or folder. Text lives in `content`; binaries live in S3 under `s3_key`."""
    TEXT, BINARY, DIR = 'text', 'binary', 'dir'
    KINDS = [(TEXT, 'Text'), (BINARY, 'Binary'), (DIR, 'Directory')]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    path = models.CharField(max_length=1024)
    kind = models.CharField(max_length=6, choices=KINDS)
    content = models.TextField(blank=True, default='')
    s3_key = models.CharField(max_length=1200, blank=True, default='')
    size = models.BigIntegerField(default=0)
    content_type = models.CharField(max_length=200, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'path'], name='uniq_project_path')]
        indexes = [models.Index(fields=['project', 'path'])]
