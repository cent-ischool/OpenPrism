from celery import shared_task
from django.utils import timezone

from .models import CollabInvite


@shared_task(name='collab.tasks.cleanup_expired_invites')
def cleanup_expired_invites():
    deleted, _ = CollabInvite.objects.filter(expires_at__lt=timezone.now()).delete()
    return deleted
