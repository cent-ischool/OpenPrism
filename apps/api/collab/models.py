import uuid

from django.conf import settings
from django.db import models


class CollabInvite(models.Model):
    """Scoped invite link. Only the SHA-256 of the token is stored."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='invites')
    token_hash = models.CharField(max_length=64, unique=True)
    role = models.CharField(max_length=10, default='editor')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class CollabDoc(models.Model):
    """The Yjs state of a file being edited collaboratively.

    This (not the file text) is what live rooms load, so every replica starts from the same CRDT history.
    The text is projected into ProjectFile.content on each flush, in the same transaction.
    """
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='collab_docs')
    path = models.CharField(max_length=1024)
    state = models.BinaryField(default=bytes)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'path'], name='uniq_collabdoc_path')]
